"""Dell S518WL packets verified against Dell's RS232 Protocol Document."""

import fcntl
import logging
import os
import select
import stat
import termios
import threading
import time

PACKETS = {
    "on": bytes.fromhex("be ef 10 05 00 c6 ff 11 11 01 00 01"),
    "off": bytes.fromhex("be ef 10 05 00 0c 3e 11 11 01 00 18"),
    "status": bytes.fromhex("be ef 10 05 00 46 7e 11 11 01 00 ff"),
}
STATES = {1: "standby", 2: "warming_up", 3: "on", 4: "cooling", 5: "power_saving"}
POWER_ON_GUARD_S = 5.0
LOG = logging.getLogger(__name__)


class DeviceError(Exception):
    pass


class Dell:
    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.fd = None
        self.identity = None
        self.next_command = 0.0

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
        self.fd = None
        self.identity = None

    def _connect(self):
        path = self.config["device"]
        try:
            info = os.stat(path)
        except OSError:
            self.close()
            raise DeviceError(f"Brak portu {path}") from None
        if not stat.S_ISCHR(info.st_mode):
            raise DeviceError("Port nie jest urzadzeniem znakowym")
        identity = (info.st_dev, info.st_ino, info.st_rdev)
        if self.fd is not None and self.identity == identity:
            return
        self.close()
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            attributes = termios.tcgetattr(fd)
            attributes[0] = termios.INPCK if self.config["parity"] != "N" else 0
            attributes[1] = 0
            attributes[2] = termios.CLOCAL | termios.CREAD
            attributes[2] |= termios.CS8 if self.config["data_bits"] == 8 else termios.CS7
            if self.config["parity"] != "N":
                attributes[2] |= termios.PARENB
                if self.config["parity"] == "O":
                    attributes[2] |= termios.PARODD
            if self.config["stop_bits"] == 2:
                attributes[2] |= termios.CSTOPB
            attributes[3] = 0
            speed = getattr(termios, f"B{self.config['baud']}")
            attributes[4] = attributes[5] = speed
            attributes[6][termios.VMIN] = 0
            attributes[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, attributes)
            termios.tcflush(fd, termios.TCIOFLUSH)
        except Exception:
            os.close(fd)
            raise
        self.fd = fd
        self.identity = identity
        LOG.info("%s: podlaczono %s", self.config["id"], path)

    def reconnect(self):
        if not self.lock.acquire(blocking=False):
            return
        try:
            self._connect()
        except (OSError, DeviceError) as error:
            LOG.debug("%s: %s", self.config["id"], error)
        finally:
            self.lock.release()

    def _exchange(self, action):
        self._connect()
        wait = self.next_command - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        termios.tcflush(self.fd, termios.TCIFLUSH)
        packet = PACKETS[action]
        deadline = time.monotonic() + self.config["response_timeout_s"]
        pending = memoryview(packet)
        while pending:
            if not select.select([], [self.fd], [], max(0, deadline - time.monotonic()))[1]:
                raise DeviceError("Timeout zapisu RS232; wynik nieznany")
            count = os.write(self.fd, pending)
            if count <= 0:
                raise DeviceError("Nieudany zapis RS232")
            pending = pending[count:]
        if action == "on":
            self.next_command = time.monotonic() + POWER_ON_GUARD_S
        if not self.config["verify_response"] and action != "status":
            return None
        # Status is three bytes; command acknowledgement is one byte.
        response = bytearray()
        expected = 3 if action == "status" else 1
        while len(response) < expected:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.fd], [], [], max(0, left))[0]:
                raise DeviceError("Brak odpowiedzi RS232; wykonanie polecenia niepotwierdzone")
            chunk = os.read(self.fd, expected - len(response))
            if not chunk:
                raise DeviceError("Port RS232 odlaczony")
            response.extend(chunk)
            if response[0] != 0:
                reason = {1: "niedostepna komenda", 2: "blad komendy lub CRC"}.get(response[0], "nieznana odpowiedz")
                raise DeviceError(f"Projektor odrzucil polecenie: {reason}")
        if action == "status":
            if response[1] != 0xff or response[2] not in STATES:
                raise DeviceError("Nieprawidlowa odpowiedz System Status")
            return STATES[response[2]]
        return "acknowledged"

    def _status(self):
        return self._exchange("status")

    def execute(self, action):
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "status": "busy", "detail": "Projektor wykonuje inne polecenie"}
        try:
            if action == "status":
                return {"ok": True, "status": "verified", "state": self._status()}
            if not self.config["verify_response"]:
                self._exchange(action)
                return {"ok": True, "status": "sent_unconfirmed", "state": "unknown"}
            wanted = "on" if action == "on" else "standby"
            deadline = time.monotonic() + self.config["transition_timeout_s"]
            current = self._status()
            if current == wanted or (action == "off" and current == "power_saving"):
                return {"ok": True, "status": "already_set", "state": current}
            # Finish a transition before sending the opposite operation.
            while current in ("warming_up", "cooling"):
                if time.monotonic() >= deadline:
                    raise DeviceError("Trwa rozgrzewanie/chlodzenie; polecenie nie zostalo wyslane")
                time.sleep(0.5)
                current = self._status()
                if current == wanted:
                    return {"ok": True, "status": "already_set", "state": current}
            self._exchange(action)
            # Acknowledgement is separate from a confirmed final power state.
            while time.monotonic() < deadline:
                current = self._status()
                if current == wanted or (action == "off" and current == "power_saving"):
                    return {"ok": True, "status": "verified", "state": current}
                time.sleep(0.5)
            return {"ok": True, "status": "acknowledged", "state": current,
                    "detail": "Projektor przyjal komende; stan docelowy jeszcze niepotwierdzony"}
        except (OSError, DeviceError) as error:
            self.close()
            return {"ok": False, "status": "error", "state": "unknown", "detail": str(error)}
        finally:
            self.lock.release()
