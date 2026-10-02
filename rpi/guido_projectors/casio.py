"""CueServer 1 UDP CueScript transport; no delivery acknowledgement."""

import socket
import threading
import time


class Casio:
    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.next_command = 0.0

    def execute(self, action):
        if action == "status":
            return {"ok": True, "status": "unavailable", "state": "unknown",
                    "detail": "UDP CueServer nie potwierdza stanu projektora"}
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "status": "busy", "detail": "Trwa inne polecenie Casio"}
        try:
            wait = self.next_command - time.monotonic()
            if wait > 0:
                # Do not queue a conflicting command for execution later.
                return {"ok": False, "status": "busy", "detail": f"Odczekaj {wait:.1f} s przed kolejna komenda"}
            payload = self.config[f"{action}_command"].encode("ascii")
            addresses = socket.getaddrinfo(self.config["host"], self.config["port"],
                                          type=socket.SOCK_DGRAM)
            family, kind, protocol, _, address = addresses[0]
            with socket.socket(family, kind, protocol) as sock:
                sock.settimeout(2)
                sent = sock.sendto(payload, address)
                if sent != len(payload):
                    raise OSError("Niepelny zapis datagramu")
            self.next_command = time.monotonic() + self.config["min_interval_s"]
            return {"ok": True, "status": "sent_unconfirmed", "state": "unknown",
                    "detail": "Wyslano UDP do CueServer; brak potwierdzenia wykonania"}
        except OSError as error:
            return {"ok": False, "status": "error", "state": "unknown", "detail": str(error)}
        finally:
            self.lock.release()
