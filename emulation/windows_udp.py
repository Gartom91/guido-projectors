"""Loopback-only Windows simulators for the three original auxiliary UDP routes."""

import json
from pathlib import Path
import re
import select
import socket
import sys
import time


def main():
    directory = Path(sys.argv[1])
    sockets = {}
    states = {"fire_outputs": {}, "output_8": "unknown", "reconnect_count": 0}
    for name in ("fire", "aux", "playback"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sockets[sock] = name
        # Activate and verify this new loopback receive endpoint before user tests.
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.3)
        for _ in range(10):
            probe.sendto(b"guido-readiness-probe", sock.getsockname())
            try:
                if sock.recv(1024) == b"guido-readiness-probe":
                    break
            except TimeoutError:
                continue
        else:
            raise RuntimeError("Windows loopback UDP receiver unavailable")
        probe.close()
        sock.setblocking(False)
    ports = {name: sock.getsockname()[1] for sock, name in sockets.items()}
    (directory / "windows-outputs.json").write_text(json.dumps(states))
    path = directory / "windows-udp-ports.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(ports))
    temporary.replace(path)
    try:
        with (directory / "windows-udp.log").open("a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%H:%M:%S')} Windows UDP: nowa sesja symulatorów gotowa\n")
            log.flush()
            while not (directory / "STOP").exists():
                for sock in select.select(list(sockets), [], [], 0.2)[0]:
                    data = sock.recv(4096).decode("ascii", errors="replace")
                    route = sockets[sock]
                    if data == "guido-readiness-probe":
                        continue
                    if route == "playback" and data == "reconnect":
                        states["reconnect_count"] += 1
                    for channel, action in re.findall(r"Output ([1238]) (On|Off);", data):
                        if route == "fire" and channel != "8":
                            states["fire_outputs"][channel] = action.lower()
                        elif route == "aux" and channel == "8":
                            states["output_8"] = action.lower()
                    log.write(f"{time.strftime('%H:%M:%S')} Windows UDP {route}: {data}\n")
                    log.flush()
                    temporary = directory / "windows-outputs.tmp"
                    temporary.write_text(json.dumps(states))
                    temporary.replace(directory / "windows-outputs.json")
    finally:
        for sock in sockets:
            sock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        (Path(sys.argv[1]) / "windows-udp-error.txt").write_text(str(error), encoding="utf-8")
        raise
