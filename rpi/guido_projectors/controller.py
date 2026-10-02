"""Independent device operations and once-per-boot startup policy."""

from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
import threading

from .casio import Casio
from .dell import Dell

LOG = logging.getLogger(__name__)


class Controller:
    def __init__(self, config, state_path):
        self.config = config
        self.state_path = Path(state_path)
        self.devices = {item["id"]: Dell(item) for item in config["dell"] if item["enabled"]}
        if config["casio"]["enabled"]:
            self.devices["casio"] = Casio(config["casio"])
        self.stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=12, thread_name_prefix="projector")
        self.monitor = threading.Thread(target=self._monitor, daemon=True, name="usb-reconnect")

    def start(self):
        self.monitor.start()

    def _monitor(self):
        while not self.stop.is_set():
            for device in self.devices.values():
                if isinstance(device, Dell):
                    device.reconnect()
            self.stop.wait(self.config["reconnect_interval_s"])

    def close(self):
        self.stop.set()
        if self.monitor.is_alive():
            self.monitor.join(timeout=2)
        self.pool.shutdown(wait=True)
        for device in self.devices.values():
            if isinstance(device, Dell):
                device.close()

    def dispatch(self, request):
        if not isinstance(request, dict) or type(request.get("v")) is not int or request.get("v") != 1:
            raise ValueError("Wymagany protokol v=1")
        action = request.get("action")
        target = request.get("target", "all")
        if action not in ("on", "off", "status") or target not in ("all", "dell1", "dell2", "casio"):
            raise ValueError("Nieprawidlowa akcja lub cel")
        chosen = list(self.devices) if target == "all" else [target]
        if not chosen:
            return {"v": 1, "ok": False, "error": "Brak skonfigurowanych projektorow", "results": {}}
        results = {}
        pending = {}
        for key in chosen:
            if key not in self.devices:
                results[key] = {"ok": False, "status": "disabled", "detail": "Projektor nie jest wlaczony w konfiguracji"}
            else:
                pending[key] = self.pool.submit(self.devices[key].execute, action)
        for key, future in pending.items():
            try:
                results[key] = future.result()
            except Exception:
                LOG.exception("%s: nieoczekiwany blad sterownika", key)
                results[key] = {"ok": False, "status": "error", "detail": "Blad sterownika; sprawdz dziennik"}
        LOG.info("action=%s target=%s results=%s", action, target,
                 {key: value["status"] for key, value in results.items()})
        return {"v": 1, "ok": all(item["ok"] for item in results.values()), "results": results}

    def startup(self, boot_id=None):
        boot_id = boot_id or Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        self.state_path.mkdir(parents=True, exist_ok=True)
        marker = self.state_path / "startup-boot-id"
        if marker.exists() and marker.read_text().strip() == boot_id:
            return
        # Record BEFORE side effects: restart after a crash must not repeat ON.
        with marker.open("w") as file:
            file.write(boot_id + "\n")
            file.flush()
            os.fsync(file.fileno())
        policy = self.config["startup"]
        if policy == "preserve":
            LOG.info("Start: bez zmiany zasilania projektorow")
            return
        LOG.warning("Start: skonfigurowano automatyczne %s", policy)
        if self.stop.wait(10):
            return
        self.dispatch({"v": 1, "action": policy, "target": "all"})
