"""Verify the published Windows EXE against an active local UDP receiver."""

import json
import os
from pathlib import Path
import socket
import subprocess
import threading


def main():
    if os.name != "nt":
        raise RuntimeError("Run this test using Python on Windows")
    repo = Path(__file__).resolve().parents[1]
    expected = ["Output 1 On; Output 2 On; Output 3 On;",
                "Output 1 Off; Output 2 Off; Output 3 Off;",
                "reconnect", "Output 8 On;", "Output 8 Off;"]
    received = []
    ready = threading.Event()
    output = repo / "tmp" / "windows-udp-active-receiver.json"
    output.parent.mkdir(exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(5)

        def receive():
            ready.set()
            try:
                for _ in expected:
                    received.append(receiver.recv(4096).decode("ascii"))
            except TimeoutError:
                return

        thread = threading.Thread(target=receive)
        thread.start()
        ready.wait(timeout=5)
        try:
            process = subprocess.run([
                str(repo / "output/pc/ShadokProjektory-RPi.exe"), "--udp-test",
                str(repo / "tmp/windows-udp-send.json"), "127.0.0.1",
                str(receiver.getsockname()[1]),
            ], timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        finally:
            thread.join(timeout=6)
        result = {"ok": process.returncode == 0 and received == expected,
                  "received": received, "expected": expected}
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
        if not result["ok"]:
            raise AssertionError("UDP payload reception failed; inspect report")


if __name__ == "__main__":
    main()
