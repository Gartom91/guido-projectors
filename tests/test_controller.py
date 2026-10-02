import asyncio
import copy
import json
import os
from pathlib import Path
import pty
import select
import socket
import threading

import pytest

from guido_projectors.config import defaults, load, save, validate
from guido_projectors.controller import Controller
from guido_projectors.dell import Dell, PACKETS
import guido_projectors.dell as dell_module
from guido_projectors.server import Server


class Projector:
    """PTY emulator with real packet validation and fragmented serial replies."""
    def __init__(self, initial=1):
        self.master, self.slave = pty.openpty()
        self.path = os.ttyname(self.slave)
        self.state = initial
        self.commands = []
        self.error = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        buffer = bytearray()
        while not self.stop.is_set():
            if not select.select([self.master], [], [], 0.1)[0]:
                continue
            buffer.extend(os.read(self.master, 1024))
            while len(buffer) >= 12:
                packet = bytes(buffer[:12])
                del buffer[:12]
                action = next((key for key, value in PACKETS.items() if packet == value), None)
                if action is None:
                    self.error = f"Wrong packet {packet.hex()}"
                    os.write(self.master, b"\x02")
                    continue
                self.commands.append(action)
                if action == "status":
                    for value in (0, 0xff, self.state):
                        os.write(self.master, bytes([value]))
                else:
                    self.state = 3 if action == "on" else 1
                    os.write(self.master, b"\x00")

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        os.close(self.master)
        os.close(self.slave)


@pytest.fixture
def projector():
    device = Projector()
    yield device
    device.close()
    assert device.error is None


def driver(projector):
    config = defaults()["dell"][0]
    config.update(device=projector.path, enabled=True, response_timeout_s=0.15)
    return Dell(config)


def test_exact_manufacturer_packets():
    assert PACKETS["on"].hex() == "beef100500c6ff1111010001"
    assert PACKETS["off"].hex() == "beef1005000c3e1111010018"
    assert PACKETS["status"].hex() == "beef100500467e11110100ff"


def test_power_and_idempotence(projector, monkeypatch):
    monkeypatch.setattr(dell_module, "POWER_ON_GUARD_S", 0.02)
    device = driver(projector)
    try:
        assert device.execute("status")["state"] == "standby"
        assert device.execute("on") == {"ok": True, "status": "verified", "state": "on"}
        assert device.execute("on")["status"] == "already_set"
        assert projector.commands.count("on") == 1
        assert device.execute("off")["state"] == "standby"
    finally:
        device.close()


def test_device_busy_does_not_queue(projector):
    device = driver(projector)
    device.lock.acquire()
    try:
        assert device.execute("on")["status"] == "busy"
        assert projector.commands == []
    finally:
        device.lock.release()
        device.close()


def test_missing_device_reports_error():
    config = defaults()["dell"][0]
    config["device"] = "/dev/nonexistent-guido"
    assert Dell(config).execute("on")["ok"] is False


def test_serial_timeout_never_claims_success():
    master, slave = pty.openpty()
    device = Dell({**defaults()["dell"][0], "device": os.ttyname(slave), "response_timeout_s": 0.1})
    try:
        reply = device.execute("on")
        assert reply["ok"] is False and reply["state"] == "unknown"
        assert os.read(master, 12) == PACKETS["status"]
    finally:
        device.close()
        os.close(master)
        os.close(slave)


def test_reconnect_after_adapter_replacement(tmp_path):
    first, second = Projector(), Projector(initial=3)
    alias = tmp_path / "usb"
    alias.symlink_to(first.path)
    device = Dell({**defaults()["dell"][0], "device": str(alias)})
    try:
        assert device.execute("status")["state"] == "standby"
        alias.unlink()
        assert device.execute("status")["ok"] is False
        alias.symlink_to(second.path)
        assert device.execute("status")["state"] == "on"
    finally:
        device.close()
        first.close()
        second.close()


def test_casio_exact_udp_and_unknown_state(tmp_path):
    config = defaults()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(1)
        config["casio"].update(enabled=True, host="127.0.0.1", port=receiver.getsockname()[1], min_interval_s=0)
        controller = Controller(config, tmp_path)
        try:
            for action, packet in (("on", b'"(PWR1)"~4'), ("off", b'"(PWR0)"~4')):
                reply = controller.dispatch({"v": 1, "action": action})
                assert receiver.recv(1024) == packet
                assert reply["results"]["casio"]["status"] == "sent_unconfirmed"
                assert reply["results"]["casio"]["state"] == "unknown"
        finally:
            controller.close()


def test_configuration_validation_and_atomic_backup(tmp_path):
    config = defaults()
    path = tmp_path / "config.json"
    save(config, path, ownership=False)
    config["startup"] = "off"
    save(config, path, ownership=False)
    assert load(path)["startup"] == "off"
    assert load(next(tmp_path.glob("config-*.bak.json")))["startup"] == "preserve"
    assert path.stat().st_mode & 0o777 == 0o640
    assert not list(tmp_path.glob(".config-*"))


@pytest.mark.parametrize("change", [
    lambda c: c["server"].update(port=0),
    lambda c: c["server"].update(token="short"),
    lambda c: c["server"].update(allowed_clients=["invalid"]),
    lambda c: c["dell"][0].update(enabled=True),
    lambda c: c["dell"][0].update(response_timeout_s=float("nan")),
    lambda c: c["dell"][0].update(stop_bits=True),
    lambda c: c["casio"].update(enabled=True),
    lambda c: c["casio"].update(on_command="a\nb"),
])
def test_reject_invalid_configuration(change):
    config = defaults()
    change(config)
    with pytest.raises((ValueError, TypeError)):
        validate(config)


def test_duplicate_physical_port_rejected(projector):
    config = defaults()
    for item in config["dell"]:
        item.update(enabled=True, device=projector.path)
    with pytest.raises(ValueError, match="jednego portu"):
        validate(config)


def test_default_boot_never_switches_and_policy_once(tmp_path, monkeypatch):
    config = defaults()
    controller = Controller(config, tmp_path)
    calls = []
    monkeypatch.setattr(controller, "dispatch", lambda request: calls.append(request))
    monkeypatch.setattr(controller.stop, "wait", lambda interval: False)
    try:
        controller.startup("boot-1")
        assert calls == []
        config["startup"] = "on"
        controller.startup("boot-1")
        assert calls == []
        controller.startup("boot-2")
        controller.startup("boot-2")
        assert calls == [{"v": 1, "action": "on", "target": "all"}]
    finally:
        controller.close()


def test_two_dells_fail_independently(projector, tmp_path, monkeypatch):
    monkeypatch.setattr(dell_module, "POWER_ON_GUARD_S", 0.02)
    config = defaults()
    config["dell"][0].update(enabled=True, device=projector.path)
    config["dell"][1].update(enabled=True, device="/dev/nonexistent-guido")
    controller = Controller(config, tmp_path)
    try:
        reply = controller.dispatch({"v": 1, "action": "on"})
        assert not reply["ok"]
        assert reply["results"]["dell1"]["state"] == "on"
        assert reply["results"]["dell2"]["ok"] is False
    finally:
        controller.close()


def test_tcp_stream_fragmentation_auth_and_frame_limits(tmp_path):
    class FakeController:
        def __init__(self):
            self.calls = []

        def dispatch(self, request):
            self.calls.append(request)
            return {"v": 1, "ok": True, "results": {}}

    async def test():
        config = defaults()
        controller = FakeController()
        api = Server(config, controller)
        server = await asyncio.start_server(api.client, "127.0.0.1", 0, limit=2048)
        port = server.sockets[0].getsockname()[1]
        async with server:
            for request, expected in [
                ({"v": 1, "action": "on", "token": config["server"]["token"]}, True),
                ({"v": 1, "action": "on", "token": "bad"}, False),
                ({"v": 1, "action": "on", "token": "ą"}, False),
                ([], False),
            ]:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                frame = json.dumps(request).encode() + b"\n"
                writer.write(frame[:7])
                await writer.drain()
                await asyncio.sleep(0.01)
                writer.write(frame[7:])
                await writer.drain()
                response = json.loads(await reader.readline())
                assert response["ok"] is expected
                writer.close()
                await writer.wait_closed()
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"a" * 4096 + b"\n")
            await writer.drain()
            assert json.loads(await reader.readline())["ok"] is False
            writer.close()
            await writer.wait_closed()
        assert len(controller.calls) == 1
        assert api.clients == 0

    asyncio.run(test())
