"""Drive the ready WSL lab through its real curses UI and real serial/UDP backend."""

import json
from pathlib import Path
import shlex
import subprocess
import time

REPO = Path(__file__).resolve().parents[1]
SOCKET = "/tmp/guido-emulator-test.sock"


def tmux(*args):
    return subprocess.run(["tmux", "-S", SOCKET, *args], check=True, capture_output=True, text=True).stdout


def until(text):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        content = tmux("capture-pane", "-p", "-t", "guido-live-lab")
        if text in content:
            return content
        time.sleep(0.1)
    raise AssertionError(f"Missing {text!r}:\n{content}")


def main():
    command = shlex.join(["env", "TERM=xterm-256color", "LANG=C.UTF-8", "python3", str(REPO / "emulation/guido_emulator.py")])
    try:
        tmux("new-session", "-d", "-x", "110", "-y", "30", "-s", "guido-live-lab", command)
        screen = until("czuwanie")
        (REPO / "tmp/emulator/tui-preview.txt").write_text(screen)
        tmux("send-keys", "-t", "guido-live-lab", *( ["Down"] * 9), "Enter")
        until("Cel testu")
        tmux("send-keys", "-t", "guido-live-lab", "Enter")
        until("Akcja testu")
        tmux("send-keys", "-t", "guido-live-lab", "Down", "Enter")
        until("rzeczywiste ON")
        tmux("send-keys", "-t", "guido-live-lab", "t")
        result_on = until("Wynik testu")
        assert '"state": "on"' in result_on
        tmux("send-keys", "-t", "guido-live-lab", "Enter")
        until("Sterowanie projektorami")
        tmux("send-keys", "-t", "guido-live-lab", "Enter")
        until("Cel testu")
        tmux("send-keys", "-t", "guido-live-lab", "Enter")
        until("Akcja testu")
        tmux("send-keys", "-t", "guido-live-lab", "Down", "Down", "Enter")
        until("rzeczywiste OFF")
        tmux("send-keys", "-t", "guido-live-lab", "t")
        result_off = until("Wynik testu")
        assert '"state": "standby"' in result_off
        tmux("send-keys", "-t", "guido-live-lab", "Enter")
        until("Sterowanie projektorami")
        tmux("send-keys", "-t", "guido-live-lab", "q")
        until("odbiornik i wirtualne projektory nadal działają")
        from emulation.guido_emulator import request
        assert request("status")["ok"]
        tmux("send-keys", "-t", "guido-live-lab", "x", "Enter")
        report = {"ok": True, "real_tui_on_off": True, "receiver_survives_ui_close": True}
        (REPO / "tmp/emulator/tui-verification.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
    finally:
        subprocess.run(["tmux", "-S", SOCKET, "kill-server"], capture_output=True)


if __name__ == "__main__":
    main()
