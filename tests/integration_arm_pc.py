#!/usr/bin/env python3
"""Run the published Windows EXE against the image's ARM Python and simulated devices.

Requires root in WSL, an image rootfs extracted with debugfs, and qemu-arm-static.
Temporary bind mounts are confined to the named extracted rootfs and removed in finally.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "rpi"))
sys.path.insert(0, str(REPO / "tests"))

from guido_projectors.config import defaults, save
from test_controller import Projector


def winpath(path):
    return subprocess.check_output(["wslpath", "-w", str(Path(path).resolve())], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rootfs", type=Path, default=Path("/tmp/guido-image-build/rootfs"))
    parser.add_argument("--pc-dir", type=Path, default=REPO / "output/pc")
    parser.add_argument("--pc-udp", action="store_true", help="Also test Windows-to-WSL UDP delivery")
    args = parser.parse_args()
    rootfs = args.rootfs.resolve()
    if os.geteuid() != 0 or rootfs != Path("/tmp/guido-image-build/rootfs") or not (rootfs / "usr/bin/python3").exists():
        raise ValueError("Test wymaga root i zweryfikowanego /tmp/guido-image-build/rootfs")
    temporary = REPO / "tmp" / "integration"
    temporary.mkdir(parents=True, exist_ok=True)
    temporary.chmod(0o700)
    root_config = rootfs / "etc/guido-projectors"
    root_config.mkdir(exist_ok=True)
    cert, key = root_config / "server.crt", root_config / "server.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "2",
                    "-subj", "/CN=guido-test", "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True)
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    config = defaults()
    projectors = [Projector(), Projector()]
    casio_rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    casio_rx.bind(("127.0.0.1", 0))
    casio_rx.settimeout(3)
    for item, device in zip(config["dell"], projectors):
        item.update(enabled=True, device=device.path)
    config["casio"].update(enabled=True, host="127.0.0.1", port=casio_rx.getsockname()[1], min_interval_s=0)
    with socket.socket() as reserve:
        reserve.bind(("0.0.0.0", 0))
        config["server"]["port"] = reserve.getsockname()[1]
    save(config, root_config / "config.json", ownership=False)
    pc_settings = temporary / "settings.json"
    pc_settings.write_text(json.dumps({"RpiHost": "127.0.0.1", "RpiPort": config["server"]["port"],
                                      "Token": config["server"]["token"], "CertificateSha256": hashlib.sha256(der).hexdigest()}))
    pc_settings.chmod(0o600)
    for source in (REPO / "rpi").rglob("*.py"):
        destination = rootfs / "opt/guido-projectors" / source.relative_to(REPO / "rpi")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    exe = args.pc_dir.resolve() / "ShadokProjektory-RPi.exe"
    process = None
    mounts = []
    service_log = (temporary / "arm-service.log").open("w")
    result = {"ok": False}
    try:
        for source in ("/dev/pts", "/proc"):
            destination = rootfs / source.lstrip("/")
            destination.mkdir(parents=True, exist_ok=True)
            subprocess.run(["mount", "--bind", source, str(destination)], check=True)
            mounts.append(destination)
        process = subprocess.Popen(["chroot", str(rootfs), "/usr/bin/qemu-arm-static", "/usr/bin/python3",
                                    "/opt/guido-projectors/guido.py", "serve"], stdout=service_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 15
        while True:
            if process.poll() is not None:
                raise RuntimeError("ARM service exited; inspect arm-service.log")
            try:
                with socket.create_connection(("127.0.0.1", config["server"]["port"]), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        # Real production five-second guard is used by the ARM service.
        result_path = temporary / "pc-arm-results.json"
        subprocess.run([str(exe), "--integration-test", winpath(result_path), winpath(pc_settings)], check=True, timeout=120)
        replies = json.loads(result_path.read_text())
        if not replies["ok"]:
            raise AssertionError(replies)
        assert casio_rx.recv(1024) == b'"(PWR1)"~4'
        assert casio_rx.recv(1024) == b'"(PWR0)"~4'
        for projector in projectors:
            assert projector.state == 1 and projector.error is None
            assert projector.commands.count("on") == projector.commands.count("off") == 1
        result["arm_pc_tls"] = True
        result["dell_commands"] = [device.commands for device in projectors]
        result["casio_udp_exact"] = True
        if args.pc_udp:
            # Windows loopback UDP may be filtered. Use the WSL virtual Ethernet endpoint.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
                receiver.bind(("0.0.0.0", 0))
                receiver.settimeout(3)
                local_ip = subprocess.check_output(["hostname", "-I"], text=True).split()[0]
                udp_result = temporary / "pc-udp-results.json"
                subprocess.run([str(exe), "--udp-test", winpath(udp_result), local_ip,
                                str(receiver.getsockname()[1])], check=True, timeout=20)
                expected = [b"Output 1 On; Output 2 On; Output 3 On;", b"Output 1 Off; Output 2 Off; Output 3 Off;",
                            b"reconnect", b"Output 8 On;", b"Output 8 Off;"]
                received = [receiver.recv(1024) for _ in expected]
                assert received == expected
                result["pc_original_udp_received"] = True
        else:
            result["pc_original_udp_received"] = "not tested in this run; use --pc-udp"
        result["ok"] = True
    finally:
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        service_log.close()
        for destination in reversed(mounts):
            subprocess.run(["umount", str(destination)], check=True)
        for projector in projectors:
            projector.close()
        casio_rx.close()
        pc_settings.unlink(missing_ok=True)
        (temporary / "integration-summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
