"""Validated configuration and durable, atomic writes."""

import copy
import grp
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile
import time

CONFIG_PATH = Path("/etc/guido-projectors/config.json")
SOCKET_PATH = Path("/run/guido-projectors/control.sock")
STATE_PATH = Path("/var/lib/guido-projectors")
CERT_PATH = Path("/etc/guido-projectors/server.crt")
KEY_PATH = Path("/etc/guido-projectors/server.key")


def defaults():
    return {
        "version": 1,
        "server": {"host": "0.0.0.0", "port": 41794,
                   "token": secrets.token_hex(32), "allowed_clients": []},
        "startup": "preserve",
        "log_level": "INFO",
        "reconnect_interval_s": 5,
        "dell": [
            {"id": "dell1", "name": "Dell 1", "enabled": False, "device": "",
             "baud": 19200, "data_bits": 8, "parity": "N", "stop_bits": 1,
             "response_timeout_s": 2, "transition_timeout_s": 30,
             "verify_response": True},
            {"id": "dell2", "name": "Dell 2", "enabled": False, "device": "",
             "baud": 19200, "data_bits": 8, "parity": "N", "stop_bits": 1,
             "response_timeout_s": 2, "transition_timeout_s": 30,
             "verify_response": True},
        ],
        "casio": {"id": "casio", "name": "Casio XJ-A252", "enabled": False,
                  "host": "", "port": 52737,
                  "on_command": '"(PWR1)"~4', "off_command": '"(PWR0)"~4',
                  "min_interval_s": 5},
    }


def _number(value, low, high, name, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: wymagana liczba")
    if not math.isfinite(value) or not low <= value <= high or (integer and type(value) is not int):
        raise ValueError(f"{name}: zakres {low}..{high}")


def valid_host(host, allow_empty=False):
    if not isinstance(host, str) or len(host) > 253:
        raise ValueError("Nieprawidlowy adres hosta")
    if allow_empty and not host:
        return
    try:
        ipaddress.ip_address(host)
        return
    except ValueError:
        pass
    if not host or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                       for label in host.rstrip(".").split(".")):
        raise ValueError("Wymagany adres IP lub nazwa DNS")


def validate(config):
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValueError("Nieobslugiwana wersja konfiguracji")
    template = defaults()
    if set(config) != set(template):
        raise ValueError("Niepelne lub nieznane pola konfiguracji")
    server = config["server"]
    if not isinstance(server, dict) or set(server) != set(template["server"]):
        raise ValueError("Nieprawidlowa konfiguracja serwera")
    # Bind to an explicit local IP; DNS is only permitted for remote hosts.
    ipaddress.ip_address(server["host"])
    _number(server["port"], 1024, 65535, "Port TCP", True)
    if not isinstance(server["token"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", server["token"]):
        raise ValueError("Token: 32..128 znakow A-Z, a-z, 0-9, _ lub -")
    if not isinstance(server["allowed_clients"], list):
        raise ValueError("Lista dozwolonych klientow musi byc lista sieci CIDR")
    for network in server["allowed_clients"]:
        ipaddress.ip_network(network, strict=False)
    if config["startup"] not in ("preserve", "on", "off"):
        raise ValueError("Tryb startu: preserve/on/off")
    if config["log_level"] not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ValueError("Nieprawidlowy poziom logowania")
    _number(config["reconnect_interval_s"], 1, 60, "Odstęp ponownego podlaczenia")
    if not isinstance(config["dell"], list) or len(config["dell"]) != 2:
        raise ValueError("Wymagana konfiguracja dwoch projektorow Dell")
    used = []
    for i, device in enumerate(config["dell"]):
        if not isinstance(device, dict) or set(device) != set(template["dell"][i]):
            raise ValueError("Nieprawidlowe pola Dell")
        if device["id"] != f"dell{i + 1}" or type(device["enabled"]) is not bool:
            raise ValueError("Nieprawidlowy identyfikator lub wlaczenie Dell")
        if not isinstance(device["name"], str) or not 1 <= len(device["name"]) <= 80:
            raise ValueError("Nazwa Dell: 1..80 znakow")
        path = device["device"]
        if not isinstance(path, str) or (path and not (path.startswith("/dev/") and ".." not in Path(path).parts)):
            raise ValueError("Port szeregowy musi znajdowac sie pod /dev/")
        if device["enabled"]:
            if not path:
                raise ValueError("Wlaczony Dell musi miec przypisany port")
            resolved = os.path.realpath(path)
            if resolved in used:
                raise ValueError("Dwa Delle nie moga korzystac z jednego portu")
            used.append(resolved)
        if type(device["baud"]) is not int or device["baud"] not in (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200):
            raise ValueError("Nieobslugiwana szybkosc RS232")
        if type(device["data_bits"]) is not int or type(device["stop_bits"]) is not int or device["data_bits"] not in (7, 8) or device["parity"] not in ("N", "E", "O") or device["stop_bits"] not in (1, 2):
            raise ValueError("Nieobslugiwany format RS232")
        _number(device["response_timeout_s"], 0.1, 10, "Timeout odpowiedzi")
        _number(device["transition_timeout_s"], 5, 60, "Timeout zmiany stanu")
        if type(device["verify_response"]) is not bool:
            raise ValueError("verify_response musi byc wartoscia logiczna")
    casio = config["casio"]
    if not isinstance(casio, dict) or set(casio) != set(template["casio"]):
        raise ValueError("Nieprawidlowe pola Casio")
    if casio["id"] != "casio" or type(casio["enabled"]) is not bool:
        raise ValueError("Nieprawidlowy identyfikator lub wlaczenie Casio")
    if not isinstance(casio["name"], str) or not 1 <= len(casio["name"]) <= 80:
        raise ValueError("Nieprawidlowa nazwa Casio")
    valid_host(casio["host"], allow_empty=not casio["enabled"])
    _number(casio["port"], 1, 65535, "Port CueServer", True)
    for name in ("on_command", "off_command"):
        cmd = casio[name]
        if not isinstance(cmd, str) or not 1 <= len(cmd) <= 512 or any(ord(c) < 32 or ord(c) > 126 for c in cmd):
            raise ValueError("Komenda CueServer: 1..512 drukowalnych znakow ASCII")
    _number(casio["min_interval_s"], 0, 60, "Odstęp komend Casio")
    return config


def load(path=CONFIG_PATH):
    with Path(path).open(encoding="utf-8") as file:
        return validate(json.load(file))


def save(config, path=CONFIG_PATH, ownership=True):
    validate(config)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if ownership:
        os.chown(path.parent, 0, grp.getgrnam("dialout").gr_gid)
        path.parent.chmod(0o750)
    if path.exists():
        backup = path.with_name(f"config-{time.time_ns()}.bak.json")
        backup.write_bytes(path.read_bytes())
        backup.chmod(0o600)
        backups = sorted(path.parent.glob("config-*.bak.json"))
        for old in backups[:-10]:
            old.unlink()
    fd, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o640)
        if ownership:
            os.chown(temporary, 0, grp.getgrnam("dialout").gr_gid)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def public_config(config):
    sanitized = copy.deepcopy(config)
    sanitized["server"]["token"] = "<hidden>"
    return sanitized
