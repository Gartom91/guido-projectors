from types import SimpleNamespace
import socket

import pytest

import emulation.guido_emulator as emulator
from guido_projectors.config import defaults, load


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    config = defaults()
    for device, path in zip(config["dell"], ("/dev/pts/200", "/dev/pts/201")):
        device.update(enabled=True, device=path)
    config["server"]["host"] = "127.0.0.1"
    lab = object.__new__(emulator.Lab)
    lab.projectors = [SimpleNamespace(path=item["device"]) for item in config["dell"]]
    lab.casio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lab.casio.bind(("127.0.0.1", 0))
    config["casio"].update(enabled=True, host="127.0.0.1", port=lab.casio.getsockname()[1])
    path = tmp_path / "config.json"
    monkeypatch.setattr(emulator, "CONFIG", path)
    yield lab, config, path
    lab.casio.close()


def test_emulator_accepts_its_local_virtual_devices(sandbox):
    lab, config, path = sandbox
    lab.save(config)
    assert load(path) == config


@pytest.mark.parametrize("case", ["serial", "cue", "listen"])
def test_emulator_blocks_real_devices_and_nonlocal_listener(sandbox, case):
    lab, config, path = sandbox
    if case == "serial":
        config["dell"][0]["device"] = "/dev/ttyUSB0"
    elif case == "cue":
        config["casio"]["host"] = "192.0.2.10"
    else:
        config["server"]["host"] = "0.0.0.0"
    with pytest.raises(ValueError):
        lab.save(config)
    assert not path.exists()


def test_lab_owns_and_closes_resources_and_rejects_second_instance(tmp_path, monkeypatch):
    state, exported = tmp_path / "state", tmp_path / "exported"
    monkeypatch.setattr(emulator, "STATE", state)
    monkeypatch.setattr(emulator, "CONFIG", state / "config.json")
    monkeypatch.setattr(emulator, "EXPORT", exported)
    config = defaults()
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        config["server"]["port"] = reserve.getsockname()[1]
    monkeypatch.setattr(emulator, "defaults", lambda: config)
    monkeypatch.setattr(emulator.Lab, "start_receiver", lambda self: None)
    lab = emulator.Lab(windows=False)
    try:
        assert all(device.thread.is_alive() for device in lab.projectors)
        with pytest.raises(ValueError, match="Emulator już działa"):
            emulator.Lab(windows=False)
        assert not lab.instance_lock.closed
    finally:
        lab.close()
    assert lab.instance_lock.closed
    assert lab.stop.is_set()
    assert not any(device.thread.is_alive() for device in lab.projectors)
