"""Root-only terminal configuration and operating tools."""

import copy
import getpass
import grp
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import subprocess

from .config import CERT_PATH, CONFIG_PATH, KEY_PATH, SOCKET_PATH, defaults, load, public_config, save


def run(*command, check=True, **kwargs):
    return subprocess.run(command, check=check, **kwargs)


def require_root():
    if os.geteuid() != 0:
        raise ValueError("Uruchom przez sudo: sudo guido-config")


def ask(label, current, convert=str):
    value = input(f"{label} [{current}]: ").strip()
    return current if not value else convert(value)


def yes(label, current=False):
    answer = input(f"{label} [{'T' if current else 'N'}] (t/n): ").strip().lower()
    if not answer:
        return current
    if answer not in ("t", "n"):
        raise ValueError("Wpisz t lub n")
    return answer == "t"


def devices():
    paths = []
    for pattern in ("serial/by-id/*", "serial/by-path/*", "ttyUSB*", "ttyACM*"):
        paths.extend(sorted(Path("/dev").glob(pattern)))
    for index, path in enumerate(paths, 1):
        print(f" {index}. {path} -> {os.path.realpath(path)}")
    if not paths:
        print("Nie wykryto konwerterow USB-RS232. Mozna wpisac sciezke lub skonfigurowac pozniej.")
    return paths


def set_device(item, quick=False):
    print(f"\n{item['name']} - Dell S518WL; fabrycznie 19200, 8N1, bez kontroli przeplywu")
    paths = devices()
    answer = input(f"Numer portu lub sciezka [{item['device'] or 'brak'}], '-' usuwa: ").strip()
    if answer == "-":
        item["device"] = ""
    elif answer.isdecimal():
        number = int(answer)
        if not 1 <= number <= len(paths):
            raise ValueError("Nieprawidlowy numer portu")
        item["device"] = str(paths[number - 1])
    elif answer:
        item["device"] = answer
    item["enabled"] = yes("Obslugiwac ten projektor", bool(item["device"]))
    if not quick:
        item["name"] = ask("Nazwa", item["name"])
        for field, label, converter in (
            ("baud", "Baud", int), ("data_bits", "Bity danych 7/8", int),
            ("parity", "Parzystosc N/E/O", str), ("stop_bits", "Bity stopu 1/2", int),
            ("response_timeout_s", "Timeout odpowiedzi [s]", float),
            ("transition_timeout_s", "Timeout zmiany stanu [s]", float),
        ):
            item[field] = ask(label, item[field], converter)
        item["verify_response"] = yes("Weryfikowac odpowiedzi projektora", item["verify_response"])
        if not item["verify_response"]:
            print("Tryb bez RX: raportowane bedzie tylko wyslanie, bez potwierdzenia wykonania.")


def set_casio(item, quick=False):
    item["host"] = ask("Adres IP/nazwa CueServer ('-' usuwa)", item["host"])
    if item["host"] == "-":
        item["host"] = ""
    item["port"] = ask("Port UDP CueServer", item["port"], int)
    item["enabled"] = yes("Obslugiwac Casio", bool(item["host"]))
    if not quick:
        item["name"] = ask("Nazwa", item["name"])
        item["on_command"] = ask("CueScript ON", item["on_command"])
        item["off_command"] = ask("CueScript OFF", item["off_command"])
        item["min_interval_s"] = ask("Minimalny odstep komend [s]", item["min_interval_s"], float)
    print("CueServer: RS232 19200 / 8N1. Add CR+LF to Output Strings: wylaczone.")
    print("Odpowiedz UDP nie jest dostepna; stan Casio pozostaje nieznany.")


def ensure_certificate():
    if CERT_PATH.exists() and KEY_PATH.exists():
        return
    CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes",
        "-days", "3650", "-subj", "/CN=guido-projectors", "-keyout", str(KEY_PATH),
        "-out", str(CERT_PATH), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for path in (CERT_PATH, KEY_PATH):
        path.chmod(0o640)
        os.chown(path, 0, grp.getgrnam("dialout").gr_gid)


def fingerprint():
    if not CERT_PATH.exists():
        return "Brak certyfikatu"
    raw = ssl.PEM_cert_to_DER_cert(CERT_PATH.read_text())
    return hashlib.sha256(raw).hexdigest().upper()


def show_connection(config):
    print("\nUstawienia dla ShadokProjektory-RPi na PC:")
    run("hostname", "-I", check=False)
    print(f"Port TLS/TCP: {config['server']['port']}")
    print(f"Token: {config['server']['token']}")
    print(f"SHA256 certyfikatu: {fingerprint()}")


def local_request(action, target="all", timeout=150):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(SOCKET_PATH))
        sock.sendall(json.dumps({"v": 1, "action": action, "target": target}).encode() + b"\n")
        response = bytearray()
        while b"\n" not in response:
            chunk = sock.recv(4096)
            if not chunk or len(response) + len(chunk) > 16384:
                raise ValueError("Niepelna lub zbyt dluga odpowiedz odbiornika")
            response.extend(chunk)
        return json.loads(response.split(b"\n")[0])


def export_config(config, path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=2, ensure_ascii=False)
    Path(path).chmod(0o600)


def apply(config, activate=True):
    save(config)
    ensure_certificate()
    if activate:
        run("systemctl", "enable", "guido-projectors.service", stdout=subprocess.DEVNULL)
        run("systemctl", "restart", "guido-projectors.service")
    print("Zapisano konfiguracje. Poprzednia wersja zachowana w kopii (maks. 10).")


def setup(activate=True):
    config = load() if CONFIG_PATH.exists() else defaults()
    if yes("Otworzyc konfiguracje sieci Ethernet/Wi-Fi (nmtui)"):
        run("nmtui", check=False)
    for item in config["dell"]:
        set_device(item, quick=True)
    set_casio(config["casio"], quick=True)
    config["server"]["port"] = ask("Port odbiornika na RPi", config["server"]["port"], int)
    print("Start preserve = bez komend zasilania; on = wlacz; off = wylacz raz po starcie systemu.")
    config["startup"] = ask("Zachowanie po starcie preserve/on/off", config["startup"])
    apply(config, activate=activate)
    show_connection(config)
    return config


def menu():
    require_root()
    if not CONFIG_PATH.exists():
        setup()
    while True:
        print("\nGUIDO - konfiguracja i diagnostyka projektorow")
        print("1 Stan / 2 Dell 1 / 3 Dell 2 / 4 Casio-CueServer / 5 Odbiornik i autoryzacja")
        print("6 Start i logowanie / 7 Siec Ethernet-Wi-Fi / 8 System-SSH / 9 Dziennik")
        print("10 Test ON-OFF / 11 Dane dla PC / 12 Import-eksport / 13 Restart uslugi / 14 Instrukcja / 0 Koniec")
        choice = input("> ").strip()
        try:
            config = load()
            changed = copy.deepcopy(config)
            if choice == "0":
                return
            if choice == "1":
                print(json.dumps(local_request("status"), indent=2, ensure_ascii=False))
                run("systemctl", "status", "--no-pager", "guido-projectors.service", check=False)
                continue
            if choice in ("2", "3"):
                set_device(changed["dell"][int(choice) - 2])
            elif choice == "4":
                set_casio(changed["casio"])
            elif choice == "5":
                server = changed["server"]
                server["host"] = ask("Adres nasluchu IP; 0.0.0.0 = wszystkie IPv4", server["host"])
                server["port"] = ask("Port TLS/TCP", server["port"], int)
                value = ask("Dozwolone IP/CIDR rozdzielone przecinkiem; '-' = kazdy z tokenem",
                            ",".join(server["allowed_clients"]) or "-")
                server["allowed_clients"] = [] if value == "-" else [item.strip() for item in value.split(",")]
                if yes("Wygenerowac nowy token (wymaga zmiany ustawien PC)"):
                    server["token"] = secrets.token_hex(32)
            elif choice == "6":
                changed["startup"] = ask("Start preserve/on/off", changed["startup"])
                changed["log_level"] = ask("Logi DEBUG/INFO/WARNING/ERROR", changed["log_level"])
                changed["reconnect_interval_s"] = ask("Ponowne podlaczenie USB co [s]", changed["reconnect_interval_s"], float)
            elif choice == "7":
                print("Zmiana aktywnego adresu IP moze zerwac sesje SSH. Konfiguruj lokalnie.")
                run("nmtui", check=False)
                continue
            elif choice == "8":
                run("raspi-config", check=False)
                continue
            elif choice == "9":
                run("journalctl", "-u", "guido-projectors.service", "-n", "150", "--no-pager", check=False)
                continue
            elif choice == "10":
                target = ask("Cel all/dell1/dell2/casio", "all")
                action = ask("Akcja on/off/status", "status")
                if action == "status" or yes(f"Wykonac {action} dla {target}"):
                    print(json.dumps(local_request(action, target), indent=2, ensure_ascii=False))
                continue
            elif choice == "11":
                show_connection(config)
                continue
            elif choice == "12":
                mode = ask("eksport/import", "eksport")
                path = Path(input("Pelna sciezka pliku JSON: ").strip())
                if not path.is_absolute() or path == CONFIG_PATH:
                    raise ValueError("Podaj pelna sciezke inna niz plik aktywnej konfiguracji")
                if mode == "eksport":
                    if path.exists() and not yes("Plik istnieje. Nadpisac"):
                        continue
                    export_config(config, path)
                    print("Eksport zawiera token. Certyfikat i klucz pozostaja na tym RPi.")
                    continue
                if mode != "import":
                    raise ValueError("Wybierz eksport albo import")
                changed = load(path)
            elif choice == "13":
                run("systemctl", "restart", "guido-projectors.service")
                continue
            elif choice == "14":
                print(Path("/usr/local/share/doc/guido-projectors/administracja.md").read_text(encoding="utf-8"))
                continue
            else:
                print("Nieznana opcja")
                continue
            print(json.dumps(public_config(changed), indent=2, ensure_ascii=False))
            if yes("Zapisac i zastosowac zmiany"):
                apply(changed)
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            print(f"BLAD: {error}")
