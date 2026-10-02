import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

import pytest

from guido_projectors.config import defaults, load, save
from guido_projectors.tui import Field, decode_fields, status_lines
import guido_projectors.tui as tui_module


def test_forms_reject_non_numeric_timeout_and_invalid_toggle():
    with pytest.raises(ValueError):
        decode_fields([Field("timeout", "Timeout", "float")], ["abc"])
    with pytest.raises(ValueError):
        decode_fields([Field("enabled", "Obsługa", "bool")], ["yes"])
    assert decode_fields([Field("enabled", "Obsługa", "bool"), Field("baud", "Baud", "int")],
                         ["tak", "19200"]) == {"enabled": True, "baud": 19200}


def test_dashboard_keeps_casio_unknown_and_disabled_devices_distinct():
    config = defaults()
    config["casio"].update(enabled=True, host="127.0.0.1")
    lines = status_lines(config, {"results": {"casio": {"ok": True, "state": "unknown"}}})
    assert lines.count("  wyłączony w konfiguracji") == 2
    assert "  nieznany" in lines
    assert "  włączony" not in lines


def test_stale_console_cannot_overwrite_configuration_saved_by_other_session(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    original = defaults()
    newer = copy.deepcopy(original)
    newer["casio"]["name"] = "Casio — inna sesja"
    save(newer, path, ownership=False)
    ui = object.__new__(tui_module.TUI)
    ui.config, ui.wizard = original, False
    ui.confirm = lambda *args: True
    ui.wait = lambda title, operation: operation()
    monkeypatch.setattr(tui_module, "CONFIG_PATH", path)
    monkeypatch.setattr(tui_module, "load", lambda: load(path))
    monkeypatch.setattr(tui_module, "save", lambda value: pytest.fail("Stale write must be rejected"))
    changed = copy.deepcopy(original)
    changed["dell"][0]["name"] = "Stara edycja"
    with pytest.raises(ValueError, match="Plik konfiguracji zmienił się"):
        ui.persist(changed)
    assert ui.config == load(path) == newer


@pytest.mark.parametrize("interactive,ssh,admin,active,expected", [
    (True, True, True, False, True), (False, True, True, False, False),
    (True, False, True, False, False), (True, True, False, False, False),
    (True, True, True, True, False),
])
def test_ssh_autostart_only_for_interactive_administrator(interactive, ssh, admin, active, expected):
    hook = Path(__file__).resolve().parents[1] / "image/files/guido-welcome.sh"
    script = ("id() { printf '%s' " + shlex.quote("sudo dialout" if admin else "users") + "; }; "
              "sudo() { printf 'GUI:%s\\n' \"$*\"; }; . " + shlex.quote(str(hook)))
    environment = {**os.environ, "SSH_TTY": "/dev/pts/test" if ssh else "",
                   "GUIDO_TUI_ACTIVE": "1" if active else ""}
    master, slave = os.openpty()
    try:
        completed = subprocess.run(["bash", "--noprofile", "--norc", *( ["-i"] if interactive else []),
                                    "-c", script], stdin=slave, capture_output=True, text=True, env=environment, timeout=5)
    finally:
        os.close(master)
        os.close(slave)
    assert completed.returncode == 0
    assert ("GUI:-n -- /usr/local/bin/guido-config" in completed.stdout) == expected


class Terminal:
    def __init__(self, tmp_path, wizard=False):
        self.socket = str(tmp_path / "tmux.sock")
        self.config = tmp_path / "settings.json"
        self.report = tmp_path / "result.json"
        harness = Path(__file__).with_name("tui_harness.py")
        command = shlex.join(["env", "LANG=C.UTF-8", "TERM=xterm-256color", "python3", str(harness),
                              str(self.config), str(self.report), *( ["wizard"] if wizard else [])])
        self.call("new-session", "-d", "-x", "100", "-y", "30", "-s", "guido-test", command)

    def call(self, *args):
        return subprocess.run(["tmux", "-S", self.socket, *args], capture_output=True, text=True, check=True).stdout

    def screen(self):
        return self.call("capture-pane", "-p", "-t", "guido-test")

    def until(self, text):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            content = self.screen()
            if text in content:
                return content
            time.sleep(0.05)
        raise AssertionError(f"Expected {text!r}, screen:\n{content}")

    def send(self, *keys):
        self.call("send-keys", "-t", "guido-test", *keys)

    def finished(self):
        deadline = time.monotonic() + 6
        while not self.report.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        return json.loads(self.report.read_text())

    def close(self):
        subprocess.run(["tmux", "-S", self.socket, "kill-server"], capture_output=True)


@pytest.fixture
def terminal(tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("Interactive TUI test requires tmux")
    term = Terminal(tmp_path)
    try:
        yield term
    finally:
        term.close()


def test_real_terminal_resize_cancel_and_exit_without_power_commands(terminal):
    terminal.until("czuwanie")
    terminal.send("Down", "Enter")
    terminal.until("Szybkość RS232")
    terminal.send("Escape")
    terminal.until("Sterowanie projektorami")
    terminal.call("resize-window", "-t", "guido-test", "-x", "60", "-y", "18")
    terminal.until("wymagane minimum 80x24")
    terminal.call("resize-window", "-t", "guido-test", "-x", "100", "-y", "30")
    terminal.until("Sterowanie projektorami")
    terminal.send("q")
    result = terminal.finished()
    assert result["actions"] and set(result["actions"]) == {"status"}
    assert result["commands"] == []


def test_real_terminal_edits_unicode_name_and_saves_valid_configuration(terminal):
    terminal.until("czuwanie")
    terminal.send("Down", "Enter")
    terminal.until("Szybkość RS232")
    terminal.send("Tab", "Tab", "C-u")
    terminal.call("send-keys", "-t", "guido-test", "-l", "Sala prób")
    terminal.send("F2")
    terminal.until("Zapis konfiguracji")
    terminal.send("t")
    terminal.until("Zapisano i zastosowano")
    terminal.send("Enter")
    terminal.until("Sala prób")
    terminal.send("q")
    result = terminal.finished()
    assert result["config"]["dell"][0]["name"] == "Sala prób"
    assert result["config"]["startup"] == "preserve"
    assert json.loads(terminal.config.read_text()) == result["config"]
    assert result["commands"] == [["systemctl", "restart", "guido-projectors.service"]]
    assert set(result["actions"]) == {"status"}


def test_firstboot_tui_saves_disabled_defaults_without_starting_receiver(tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("Interactive TUI test requires tmux")
    terminal = Terminal(tmp_path, wizard=True)
    try:
        terminal.until("Pierwsza konfiguracja")
        terminal.send("F2")
        terminal.until("Zapis konfiguracji")
        terminal.send("t")
        result = terminal.finished()
        assert result["config"]["startup"] == "preserve"
        assert result["commands"] == result["actions"] == []
        assert not any(item["enabled"] for item in result["config"]["dell"])
        assert not result["config"]["casio"]["enabled"]
    finally:
        terminal.close()
