from pathlib import Path
from types import SimpleNamespace

import pytest

from guido_projectors.config import defaults, save
import guido_projectors.firstboot as firstboot_module


def resumed_boot(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    marker = tmp_path / "onboarded"
    config = defaults()
    save(config, config_path, ownership=False)
    shadow = tmp_path / "shadow"
    shadow.write_text("operator:$6$testhash:1:0:99999:7:::\n")
    monkeypatch.setattr(firstboot_module, "CONFIG_PATH", config_path)
    monkeypatch.setattr(firstboot_module, "MARKER", marker)
    monkeypatch.setattr(firstboot_module, "load", lambda: config)
    monkeypatch.setattr(firstboot_module, "Path", lambda value: {
        "/etc/shadow": shadow, "/run/sshd": tmp_path / "sshd",
    }.get(value, Path(value)))
    monkeypatch.setattr(firstboot_module.pwd, "getpwall", lambda: [
        SimpleNamespace(pw_uid=1000, pw_shell="/bin/bash", pw_name="operator")
    ])
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(firstboot_module.os, "umask", lambda value: 0)
    monkeypatch.setattr(firstboot_module, "setup", lambda **kwargs: pytest.fail("Settings must survive"))
    calls = []
    monkeypatch.setattr(firstboot_module, "run", lambda *args, **kwargs: calls.append(args))
    return config, marker, calls


def test_interrupted_onboarding_restores_keys_and_connection_details(tmp_path, monkeypatch):
    config, marker, calls = resumed_boot(tmp_path, monkeypatch)
    recovered = []
    monkeypatch.setattr(firstboot_module, "ensure_certificate", lambda: recovered.append("certificate"))
    monkeypatch.setattr(firstboot_module, "show_connection", lambda value: recovered.append(value))
    firstboot_module.firstboot()
    assert recovered == ["certificate", config]
    assert config["startup"] == "preserve"
    assert marker.read_text() == "configured\n"
    assert calls[-1] == ("systemctl", "start", "--no-block", "guido-projectors.service")
    assert not any(command[0] in ("useradd", "usermod", "chpasswd") for command in calls)


def test_failed_key_recovery_does_not_complete_onboarding(tmp_path, monkeypatch):
    _, marker, calls = resumed_boot(tmp_path, monkeypatch)

    def unavailable():
        raise OSError("Simulated key creation failure")

    monkeypatch.setattr(firstboot_module, "ensure_certificate", unavailable)
    monkeypatch.setattr(firstboot_module, "show_connection", lambda value: pytest.fail("No keys yet"))
    with pytest.raises(OSError, match="key creation failure"):
        firstboot_module.firstboot()
    assert not marker.exists()
    assert ("systemctl", "start", "--no-block", "guido-projectors.service") not in calls
