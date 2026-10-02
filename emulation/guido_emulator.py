"""Ready-to-run WSL2 lab: real receiver/TUI and emulated serial/CueServer devices."""

import argparse
import asyncio
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import pty
import re
import select
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "rpi"))
from guido_projectors import tui
from guido_projectors.config import defaults, load, save, validate
from guido_projectors.dell import PACKETS
from guido_projectors.server import serve

STATE = Path.home() / ".local/share/guido-emulator"
CONFIG = STATE / "config.json"
EXPORT = REPO / "tmp/emulator"


class Projector:
    def __init__(self, name, log):
        self.name, self.log = name, log
        self.master, self.slave = pty.openpty()
        self.path = os.ttyname(self.slave)
        self.state, self.deadline = 1, 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.receive, daemon=True)
        self.thread.start()

    def receive(self):
        buffer = bytearray()
        while not self.stop.is_set():
            if self.state in (2, 4) and time.monotonic() >= self.deadline:
                self.state = 3 if self.state == 2 else 1
                self.log(f"{self.name}: stan {self.state}")
            if not select.select([self.master], [], [], 0.1)[0]:
                continue
            buffer.extend(os.read(self.master, 1024))
            while len(buffer) >= 12:
                packet, buffer = bytes(buffer[:12]), buffer[12:]
                action = next((name for name, value in PACKETS.items() if packet == value), None)
                if self.state in (2, 4) and time.monotonic() >= self.deadline:
                    self.state = 3 if self.state == 2 else 1
                if action == "status":
                    os.write(self.master, bytes([0, 0xff, self.state]))
                elif action in ("on", "off"):
                    self.state = 2 if action == "on" else 4
                    self.deadline = time.monotonic() + 2
                    os.write(self.master, b"\x00")
                    self.log(f"{self.name}: {action.upper()} — stan przejściowy {self.state}")
                else:
                    os.write(self.master, b"\x02")
                    self.log(f"{self.name}: odrzucony pakiet {packet.hex()}")

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        os.close(self.master)
        os.close(self.slave)


class Lab:
    def __init__(self, windows=True):
        self.server = self.windows = self.casio = self.casio_thread = None
        self.projectors = []
        self.casio_state = "standby"
        self.stop = threading.Event()
        self.operation_lock = threading.RLock()
        self.instance_lock = None
        try:
            self.initialize(windows)
        except BaseException:
            self.close()
            raise

    def initialize(self, windows):
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.instance_lock = (STATE / "instance.lock").open("a")
        try:
            fcntl.flock(self.instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Emulator już działa. Użyj otwartego okna lub zakończ poprzednią sesję.")
        EXPORT.mkdir(parents=True, exist_ok=True)
        self.log_lock = threading.Lock()
        self.server = None
        self.windows = None
        self.projectors = []
        self.casio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.casio.bind(("127.0.0.1", 0))
        self.casio.settimeout(0.2)
        self.stop = threading.Event()
        self.sim_log = STATE / "simulation.log"
        self.projectors = [Projector("Dell 1", self.log), Projector("Dell 2", self.log)]
        self.casio_thread = threading.Thread(target=self.casio_receive, daemon=True)
        self.casio_thread.start()
        self.config = load(CONFIG) if CONFIG.exists() else defaults()
        self.config["server"]["host"] = "127.0.0.1"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", self.config["server"]["port"]))
        for device, emulator in zip(self.config["dell"], self.projectors):
            device.update(enabled=True, device=emulator.path)
        self.config["casio"].update(enabled=True, host="127.0.0.1", port=self.casio.getsockname()[1])
        save(self.config, CONFIG, ownership=False)
        self.ensure_certificate()
        self.ports = {"fire": 0, "aux": 0, "playback": 0}
        if windows:
            self.start_windows()
        (STATE / "receiver-state").mkdir(exist_ok=True)
        (STATE / "receiver-state/startup-boot-id").unlink(missing_ok=True)
        self.start_receiver()
        self.write_pc()

    def log(self, text):
        with self.log_lock, self.sim_log.open("a", encoding="utf-8") as file:
            file.write(f"{time.strftime('%H:%M:%S')} {text}\n")
            snapshot = {device.name: {"state": device.state, "port": device.path} for device in self.projectors}
            snapshot["Casio"] = {"state": self.casio_state}
            temporary = EXPORT / "simulation-state.tmp"
            temporary.write_text(json.dumps(snapshot))
            temporary.replace(EXPORT / "simulation-state.json")

    def casio_receive(self):
        while not self.stop.is_set():
            try:
                packet = self.casio.recv(4096).decode("ascii", errors="replace")
            except TimeoutError:
                continue
            powers = re.findall(r'"\(PWR([01])\)"~4', packet)
            if powers:
                self.casio_state = "on" if powers[-1] == "1" else "standby"
            self.log("Casio UDP: " + packet + (" — wirtualny projektor " + ("ON" if powers[-1] == "1" else "OFF") if powers else " — nieznana komenda"))

    def ensure_certificate(self):
        if (STATE / "server.crt").exists() and (STATE / "server.key").exists():
            return
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "3650",
                        "-subj", "/CN=guido-emulator", "-keyout", str(STATE / "server.key"), "-out", str(STATE / "server.crt")],
                       check=True, capture_output=True)
        (STATE / "server.key").chmod(0o600)

    def start_windows(self):
        (EXPORT / "STOP").unlink(missing_ok=True)
        ports = EXPORT / "windows-udp-ports.json"
        ports.unlink(missing_ok=True)
        windows_home = subprocess.check_output(["cmd.exe", "/c", "echo", "%USERPROFILE%"], text=True).strip()
        pythonw = windows_home + r"\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
        python_linux = subprocess.check_output(["wslpath", "-u", pythonw], text=True).strip()
        script = subprocess.check_output(["wslpath", "-w", str(Path(__file__).with_name("windows_udp.py"))], text=True).strip()
        export_win = subprocess.check_output(["wslpath", "-w", str(EXPORT)], text=True).strip()
        if not Path(python_linux).exists():
            raise RuntimeError("Brak lokalnego Python Windows do symulatorów UDP")
        self.windows = subprocess.Popen([python_linux, script, export_win], stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while not ports.exists() and time.monotonic() < deadline:
            if self.windows.poll() is not None:
                raise RuntimeError("Symulator Windows UDP zakończył pracę")
            time.sleep(0.05)
        if not ports.exists():
            raise TimeoutError("Symulator Windows UDP nie zgłosił gotowości")
        self.ports = json.loads(ports.read_text())

    def start_receiver(self):
        if self.stop.is_set():
            raise ValueError("Emulator jest zatrzymywany")
        log = (STATE / "receiver.log").open("a")
        self.server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--server"],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        log.close()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                raise RuntimeError("Odbiornik zakończył pracę; sprawdź receiver.log")
            if (STATE / "control.sock").exists():
                try:
                    request("status", timeout=3)
                    return
                except (OSError, ValueError):
                    pass
            time.sleep(0.05)
        raise TimeoutError("Odbiornik nie zgłosił gotowości")

    def stop_receiver(self):
        if self.server is not None and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=150)
            except subprocess.TimeoutExpired:
                self.server.kill()
                self.server.wait()

    def restart(self):
        with self.operation_lock:
            self.stop_receiver()
            self.config = load(CONFIG)
            self.start_receiver()
            self.write_pc()

    def write_pc(self):
        der = ssl.PEM_cert_to_DER_cert((STATE / "server.crt").read_text())
        result = {"RpiHost": "127.0.0.1", "RpiPort": self.config["server"]["port"],
                  "Token": self.config["server"]["token"], "CertificateSha256": hashlib.sha256(der).hexdigest(),
                  "FireHost": "127.0.0.1", "FirePort": self.ports["fire"],
                  "AuxiliaryCueHost": "127.0.0.1", "AuxiliaryCuePort": self.ports["aux"],
                  "PlaybackHost": "127.0.0.1", "PlaybackPort": self.ports["playback"]}
        temporary = EXPORT / "pc-settings.tmp"
        temporary.write_text(json.dumps(result, indent=2))
        temporary.replace(EXPORT / "pc-settings.json")

    def save(self, value):
        validate(value)
        if value["server"]["host"] != "127.0.0.1":
            raise ValueError("W emulatorze odbiornik jest ograniczony do 127.0.0.1")
        allowed = {device.path for device in self.projectors}
        if any(device["enabled"] and device["device"] not in allowed for device in value["dell"]):
            raise ValueError("W emulatorze dozwolone są wyłącznie jego dwa wirtualne porty RS232")
        if value["casio"]["enabled"] and (value["casio"]["host"] != "127.0.0.1" or value["casio"]["port"] != self.casio.getsockname()[1]):
            raise ValueError("W emulatorze Casio używa lokalnego symulatora CueServer")
        save(value, CONFIG, ownership=False)

    def close(self):
        self.stop.set()
        with self.operation_lock:
            self.stop_receiver()
        if self.casio_thread is not None:
            self.casio_thread.join(timeout=2)
        if self.casio is not None:
            self.casio.close()
        for device in self.projectors:
            device.close()
        if self.windows is not None:
            (EXPORT / "STOP").touch()
            try:
                self.windows.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.log("Symulator Windows UDP nie potwierdził zakończenia; sygnał STOP pozostaje zapisany")
        if self.instance_lock is not None:
            self.instance_lock.close()


def request(action, target="all", timeout=150):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(STATE / "control.sock"))
        sock.sendall(json.dumps({"v": 1, "action": action, "target": target}).encode() + b"\n")
        data = bytearray()
        while b"\n" not in data:
            chunk = sock.recv(4096)
            if not chunk or len(data) > 16384:
                raise ValueError("Nieprawidłowa odpowiedź odbiornika")
            data.extend(chunk)
        return json.loads(data.split(b"\n")[0])


def frontend(lab):
    tui.CONFIG_PATH = CONFIG
    tui.load = lambda: load(CONFIG)
    tui.save = lab.save
    tui.cli.require_root = lambda: None
    tui.cli.local_request = request
    tui.cli.ensure_certificate = lab.ensure_certificate
    tui.cli.CERT_PATH = STATE / "server.crt"

    def command(ui, *args):
        if args[:2] == ("systemctl", "restart"):
            lab.restart()
            return ""
        if args[0] == "hostname":
            return "127.0.0.1 — emulator na Windows/WSL2"
        if args[0] == "journalctl":
            return "\n\n".join(path.read_text(errors="replace")[-14000:] for path in
                                  (STATE / "receiver.log", STATE / "simulation.log", EXPORT / "windows-udp.log") if path.exists())
        raise ValueError("Polecenie nie jest dostępne w izolowanym emulatorze")

    def external(ui, *args):
        ui.view("Środowisko testowe", "Emulator testuje aplikację i protokoły. Ustawienia sieci systemu, SSH i raspi-config "
                "należy sprawdzić na Raspberry Pi. Tutaj używany jest tylko localhost i wirtualne urządzenia; ustawienia Windows/WSL pozostają bez zmian.")

    tui.TUI.command, tui.TUI.external = command, external
    while True:
        tui.open_tui()
        print("\nPanel zamknięty; odbiornik i wirtualne projektory nadal działają.")
        if input("Enter otwiera ponownie TUI; X kończy całe środowisko testowe: ").strip().lower() == "x":
            break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--without-windows", action="store_true")
    args = parser.parse_args()
    if args.server:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        asyncio.run(serve(load(CONFIG), socket_path=STATE / "control.sock", state_path=STATE / "receiver-state",
                          cert_path=STATE / "server.crt", key_path=STATE / "server.key"))
        return
    def stop_signal(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGHUP, stop_signal)
    os.umask(0o077)
    lab = Lab(windows=not args.without_windows)
    try:
        if args.headless:
            print("GUIDO emulator ready", flush=True)
            while True:
                time.sleep(0.2)
        else:
            lab.log("Emulator gotowy — TUI i aplikacja Windows mogą wykonywać testy")
            frontend(lab)
    finally:
        lab.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
