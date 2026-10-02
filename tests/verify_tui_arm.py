"""Verify image-installed ARM TUI and unit/sudoers files under QEMU, without hardware."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path("/tmp/guido-image-build/rootfs")
REPO = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def arm(*args):
    return run("chroot", str(ROOT), "/usr/bin/qemu-arm-static", *args, capture_output=True, text=True).stdout


def main():
    if os.geteuid() != 0 or not (ROOT / "usr/bin/qemu-arm-static").exists():
        raise RuntimeError("Requires root and the existing isolated QEMU rootfs")
    manifest = json.loads((REPO / "output/image-manifest.json").read_text())
    if manifest["version"] != "1.1.0":
        raise ValueError("Build image 1.1.0 first")
    for destination, metadata in manifest["files"].items():
        path = ROOT / destination.lstrip("/")
        if not path.parent.resolve().is_relative_to(ROOT):
            raise ValueError("Unsafe extraction path")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            path.unlink()
        run("debugfs", "-R", f'dump {destination} "{path}"', "/tmp/guido-image-build/root.img", capture_output=True)
        path.chmod(int(metadata["mode"], 8))
    for unit in ("userconfig.service", "getty@tty1.service"):
        mask = ROOT / "etc/systemd/system" / unit
        mask.unlink(missing_ok=True)
        mask.symlink_to("/dev/null")
    verification = arm("/usr/bin/systemd-analyze", "verify", "/etc/systemd/system/guido-console.service",
                       "/etc/systemd/system/guido-firstboot.service", "/etc/systemd/system/guido-projectors.service")
    sudoers = arm("/usr/sbin/visudo", "-c")
    temporary = ROOT / "tmp/guido-tui-test"
    temporary.mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__).with_name("tui_harness.py"), temporary / "harness.py")
    socket = str(temporary / "tmux.sock")
    report = temporary / "result.json"
    report.unlink(missing_ok=True)
    configuration = temporary / "settings.json"

    def tmux(*args):
        return run("tmux", "-S", socket, *args, capture_output=True, text=True).stdout

    def until(text):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            screen = tmux("capture-pane", "-p", "-t", "guido-arm-test")
            if text in screen:
                return screen
            time.sleep(0.05)
        raise AssertionError(f"Expected {text!r}, screen:\n{screen}")

    command = shlex.join(["env", "LANG=C.UTF-8", "TERM=linux", "PYTHONPATH=/opt/guido-projectors",
                          "chroot", str(ROOT), "/usr/bin/qemu-arm-static", "/usr/bin/python3",
                          "/tmp/guido-tui-test/harness.py", "/tmp/guido-tui-test/settings.json",
                          "/tmp/guido-tui-test/result.json"])
    output = REPO / "tmp"
    try:
        tmux("new-session", "-d", "-x", "100", "-y", "30", "-s", "guido-arm-test", command)
        dashboard = until("czuwanie")
        (output / "tui-arm-dashboard.txt").write_text(dashboard)
        tmux("send-keys", "-t", "guido-arm-test", "Down", "Enter")
        form = until("Szybkość RS232")
        (output / "tui-arm-dell-form.txt").write_text(form)
        tmux("send-keys", "-t", "guido-arm-test", "Tab", "Tab", "C-u")
        tmux("send-keys", "-t", "guido-arm-test", "-l", "Sala ARM")
        # Actual Linux console F2 sequence, matching the TERM=linux image console.
        tmux("send-keys", "-t", "guido-arm-test", "-l", "\x1b[[B")
        until("Zapis konfiguracji")
        tmux("send-keys", "-t", "guido-arm-test", "t")
        until("Zapisano i zastosowano")
        tmux("send-keys", "-t", "guido-arm-test", "Enter")
        until("Sala ARM")
        tmux("send-keys", "-t", "guido-arm-test", "q")
        deadline = time.monotonic() + 12
        while not report.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        result = json.loads(report.read_text())
        assert result["config"]["dell"][0]["name"] == "Sala ARM"
        assert result["config"]["startup"] == "preserve"
        assert set(result["actions"]) == {"status"}
        result = {"ok": True, "arm_curses_terminal": True, "linux_f2": True,
                  "unicode_ui": True, "unit_verification": verification.strip() or "passed",
                  "sudoers_verification": sudoers.strip()}
        (output / "tui-arm-verification.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    finally:
        subprocess.run(["tmux", "-S", socket, "kill-server"], capture_output=True)


if __name__ == "__main__":
    main()
