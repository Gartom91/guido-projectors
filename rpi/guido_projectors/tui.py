"""Full-screen console UI. All curses calls stay on the main thread."""

import copy
import curses
from dataclasses import dataclass
import fcntl
import json
import locale
import os
from pathlib import Path
import secrets
import subprocess
import sys
import textwrap
import threading
import time

from . import __version__
from . import cli
from .config import CONFIG_PATH, defaults, load, save, validate

MENU = (
    "Stan projektorów", "Dell 1 / port USB", "Dell 2 / port USB",
    "Casio / CueServer", "Odbiornik / dostęp", "Start / logowanie",
    "Sieć Ethernet / Wi-Fi", "System / SSH", "Dziennik zdarzeń",
    "Test ON / OFF", "Dane połączenia PC", "Import / eksport",
    "Restart odbiornika", "Instrukcja", "Wyjście",
)
ENTER = ("\n", "\r", curses.KEY_ENTER)
STATES = {"on": "włączony", "standby": "czuwanie", "warming_up": "rozgrzewanie",
          "cooling": "chłodzenie", "power_saving": "oszczędzanie energii",
          "unknown": "nieznany", "busy": "zajęty", "disconnected": "brak połączenia"}


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str = "text"
    choices: tuple = ()


def decode_fields(fields, values):
    result = {}
    for field, value in zip(fields, values, strict=True):
        if field.kind == "bool":
            if value not in ("tak", "nie"):
                raise ValueError(f"{field.label}: wybierz tak lub nie")
            result[field.key] = value == "tak"
        elif field.kind == "int":
            result[field.key] = int(value)
        elif field.kind == "float":
            result[field.key] = float(value)
        else:
            result[field.key] = value.strip()
    return result


def status_lines(config, response):
    results = response.get("results", {})
    lines = []
    for device in [*config["dell"], config["casio"]]:
        if not device["enabled"]:
            state = "wyłączony w konfiguracji"
        else:
            result = results.get(device["id"], {})
            if not result:
                state = "oczekiwanie na odczyt"
            elif result.get("status") == "busy":
                state = "trwa operacja"
            elif not result.get("ok"):
                state = result.get("detail", "brak odpowiedzi")
            else:
                state = STATES.get(result.get("state", "unknown"), result.get("state", "nieznany"))
        lines.extend([device["name"], "  " + state,
                      "  " + (device.get("device", "") or
                               (f"{device['host']}:{device['port']}" if "host" in device and device["host"] else "brak portu/adresu")), ""])
    return lines


class Job:
    def __init__(self, operation):
        self.done = threading.Event()
        self.value = None
        self.error = None

        def work():
            try:
                self.value = operation()
            except Exception as error:
                self.error = error
            finally:
                self.done.set()

        threading.Thread(target=work, daemon=True).start()

    def result(self):
        if self.error is not None:
            raise self.error
        return self.value


class TUI:
    def __init__(self, screen, config, wizard=False):
        self.screen = screen
        self.config = config
        self.wizard = wizard
        self.saved = False
        self.response = {}
        self.status_error = ""
        self.status_job = None
        self.next_status = 0
        self.selected = 0
        self.screen.keypad(True)
        self.screen.timeout(200)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.accent = curses.A_BOLD
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
            self.accent = curses.color_pair(1) | curses.A_BOLD

    def put(self, row, column, value, attr=0, width=None):
        height, columns = self.screen.getmaxyx()
        if not 0 <= row < height or not 0 <= column < columns:
            return
        room = max(0, min(columns - column - 1, width or columns))
        # Device names and log entries must not inject control sequences.
        value = "".join(char if char.isprintable() else " " for char in str(value))
        try:
            self.screen.addnstr(row, column, value, room, attr)
        except curses.error:
            pass  # A resize can occur between getmaxyx and addnstr.

    def frame(self, title, footer):
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        self.put(0, 0, f" GUIDO {__version__}  |  {title}".ljust(width - 1), self.accent)
        self.put(height - 1, 0, " " + footer, curses.A_REVERSE)
        return height, width

    def key(self):
        try:
            return self.screen.get_wch()
        except curses.error:
            return None

    def enough_room(self):
        height, width = self.screen.getmaxyx()
        if height >= 24 and width >= 80:
            return True
        self.frame("Rozmiar terminala", "Powiększ okno do 80x24; Esc wraca")
        self.put(3, 1, f"Obecnie {width}x{height}; wymagane minimum 80x24.")
        self.screen.refresh()
        return False

    def view(self, title, content):
        offset = 0
        while True:
            height, width = self.frame(title, "↑↓ / PgUp PgDn: przewijanie   Esc / Enter: powrót")
            lines = []
            for line in str(content).splitlines():
                lines.extend(textwrap.wrap(line, max(10, width - 4), replace_whitespace=False) or [""])
            visible = max(1, height - 4)
            offset = min(max(0, offset), max(0, len(lines) - visible))
            for row, line in enumerate(lines[offset:offset + visible], 2):
                self.put(row, 2, line)
            self.screen.refresh()
            key = self.key()
            if key in ("\x1b", "q", *ENTER):
                return
            if key in (curses.KEY_DOWN, "j"):
                offset += 1
            elif key in (curses.KEY_UP, "k"):
                offset -= 1
            elif key == curses.KEY_NPAGE:
                offset += visible
            elif key == curses.KEY_PPAGE:
                offset -= visible

    def confirm(self, title, detail):
        while True:
            self.frame(title, "T: potwierdź   N / Esc: anuluj")
            for row, line in enumerate(textwrap.wrap(detail, max(10, self.screen.getmaxyx()[1] - 4)), 3):
                self.put(row, 2, line)
            self.screen.refresh()
            key = self.key()
            if key in ("t", "T"):
                return True
            if key in ("n", "N", "\x1b"):
                return False

    def wait(self, title, operation):
        job = Job(operation)
        while not job.done.is_set():
            self.frame(title, "Operacja w toku; oczekiwanie na wynik")
            self.put(4, 2, "Proszę czekać…")
            self.screen.refresh()
            self.key()
        return job.result()

    def command(self, *args):
        result = subprocess.run(args, capture_output=True, text=True, timeout=180 if args[0] == "systemctl" else 30)
        if result.returncode:
            raise ValueError(result.stderr.strip() or result.stdout.strip() or f"Błąd polecenia {args[0]}")
        return result.stdout

    def external(self, *args):
        curses.def_prog_mode()
        curses.endwin()
        try:
            cli.run(*args, check=False)
        finally:
            curses.reset_prog_mode()
            self.screen.clear()
            self.screen.timeout(200)
            self.screen.keypad(True)

    def form(self, title, fields, initial, help_text="", ports=False):
        values = ["tak" if initial.get(field.key) is True else "nie" if initial.get(field.key) is False
                  else str(initial.get(field.key, "")) for field in fields]
        selected, cursor = 0, len(values[0])
        error = ""
        while True:
            if not self.enough_room():
                if self.key() == "\x1b":
                    return None
                continue
            height, width = self.frame(title, "Tab / ↑↓: pole  Enter: następne  F2: zatwierdź  Esc: anuluj" + ("  F3: porty" if ports else ""))
            visible = height - 8
            start = max(0, selected - visible + 1)
            label_width = min(33, width // 2)
            value_width = width - label_width - 7
            for index in range(start, min(len(fields), start + visible)):
                row = 2 + index - start
                attr = curses.A_REVERSE if index == selected else 0
                self.put(row, 2, fields[index].label, attr, label_width)
                value = values[index]
                position = max(0, cursor - value_width + 1) if index == selected else 0
                self.put(row, label_width + 4, (value[position:] or " ").ljust(value_width), attr, value_width)
                if index == selected and not fields[index].choices:
                    self.put(row, label_width + 4 + min(cursor - position, value_width - 1),
                             value[cursor:cursor + 1] or " ", attr | curses.A_UNDERLINE, 1)
            self.put(height - 5, 2, help_text)
            self.put(height - 3, 2, error)
            self.screen.refresh()
            key = self.key()
            field = fields[selected]
            if key == "\x1b":
                return None
            if key == curses.KEY_F2:
                try:
                    return decode_fields(fields, values)
                except (ValueError, OverflowError) as failure:
                    error = str(failure)
            elif key == curses.KEY_F3 and ports:
                devices = []
                for pattern in ("serial/by-id/*", "serial/by-path/*", "ttyUSB*", "ttyACM*"):
                    devices.extend(str(path) for path in sorted(Path("/dev").glob(pattern)))
                chosen = self.choose("Porty USB — wybierz stabilną ścieżkę", devices) if devices else None
                if chosen is not None:
                    device_index = next(i for i, item in enumerate(fields) if item.key == "device")
                    values[device_index] = chosen
                    selected, cursor = device_index, len(chosen)
                elif not devices:
                    self.view("Porty USB", "Nie wykryto konwerterów. Możesz wpisać ścieżkę lub skonfigurować je później.")
            elif key in ("\t", curses.KEY_DOWN, *ENTER):
                selected = (selected + 1) % len(fields)
                cursor = len(values[selected])
            elif key in (curses.KEY_BTAB, curses.KEY_UP):
                selected = (selected - 1) % len(fields)
                cursor = len(values[selected])
            elif field.choices and key in (" ", curses.KEY_LEFT, curses.KEY_RIGHT):
                choices = tuple(str(value) for value in field.choices)
                index = choices.index(values[selected]) if values[selected] in choices else 0
                values[selected] = choices[(index + (-1 if key == curses.KEY_LEFT else 1)) % len(choices)]
                cursor = len(values[selected])
            elif not field.choices:
                value = values[selected]
                if key == curses.KEY_LEFT:
                    cursor = max(0, cursor - 1)
                elif key == curses.KEY_RIGHT:
                    cursor = min(len(value), cursor + 1)
                elif key == curses.KEY_HOME:
                    cursor = 0
                elif key == curses.KEY_END:
                    cursor = len(value)
                elif key in (curses.KEY_BACKSPACE, "\x7f", "\b") and cursor:
                    values[selected] = value[:cursor - 1] + value[cursor:]
                    cursor -= 1
                elif key == curses.KEY_DC:
                    values[selected] = value[:cursor] + value[cursor + 1:]
                elif key == "\x15":
                    values[selected], cursor = "", 0
                elif isinstance(key, str) and key.isprintable() and len(value) < 4096:
                    values[selected] = value[:cursor] + key + value[cursor:]
                    cursor += len(key)

    def choose(self, title, options):
        if not options:
            return None
        selected = 0
        while True:
            height, _ = self.frame(title, "↑↓: wybór   Enter: zatwierdź   Esc: anuluj")
            visible = max(1, height - 4)
            start = max(0, selected - visible + 1)
            for index in range(start, min(len(options), start + visible)):
                self.put(2 + index - start, 2, options[index], curses.A_REVERSE if index == selected else 0)
            self.screen.refresh()
            key = self.key()
            if key == "\x1b":
                return None
            if key in ENTER:
                return options[selected]
            if key in (curses.KEY_DOWN, "j"):
                selected = (selected + 1) % len(options)
            elif key in (curses.KEY_UP, "k"):
                selected = (selected - 1) % len(options)

    def persist(self, changed):
        validate(changed)
        if not self.confirm("Zapis konfiguracji", "Zapisać konfigurację i zastosować zmiany? Poprzednia wersja pozostanie w kopii."):
            return False

        def write():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with (CONFIG_PATH.parent / ".tui.lock").open("a") as lock:
                os.chmod(lock.name, 0o600)
                fcntl.flock(lock, fcntl.LOCK_EX)
                if CONFIG_PATH.exists() and load() != self.config:
                    self.config = load()
                    raise ValueError("Plik konfiguracji zmienił się. Odczytano nowe ustawienia; otwórz formularz ponownie.")
                save(changed)
                cli.ensure_certificate()
            if not self.wizard:
                self.command("systemctl", "restart", "guido-projectors.service")

        self.wait("Zapisywanie konfiguracji", write)
        self.config = changed
        self.response = {}
        self.saved = True
        self.next_status = 0
        if not self.wizard:
            self.view("Konfiguracja", "Zapisano i zastosowano konfigurację.")
        return True

    def edit_device(self, index):
        fields = [Field("device", "Port USB / ścieżka"), Field("enabled", "Obsługa projektora", "bool", ("tak", "nie")),
                  Field("name", "Nazwa"), Field("baud", "Szybkość RS232", "int", (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)),
                  Field("data_bits", "Bity danych", "int", (7, 8)), Field("parity", "Parzystość", choices=("N", "E", "O")),
                  Field("stop_bits", "Bity stopu", "int", (1, 2)), Field("response_timeout_s", "Timeout odpowiedzi [s]", "float"),
                  Field("transition_timeout_s", "Timeout zmiany stanu [s]", "float"),
                  Field("verify_response", "Weryfikacja RX", "bool", ("tak", "nie"))]
        values = self.form(MENU[index + 1], fields, self.config["dell"][index],
                           "Dell: 19200 / 8N1; Spacja zmienia wybór. Ctrl+U czyści tekst.", ports=True)
        if values is not None:
            changed = copy.deepcopy(self.config)
            changed["dell"][index].update(values)
            self.persist(changed)

    def dispatch(self, index):
        changed = copy.deepcopy(self.config)
        if index == 0:
            if self.wizard:
                self.view("Pierwsza konfiguracja", "Odbiornik zostanie uruchomiony po zakończeniu kreatora.")
            else:
                result = self.wait("Odczyt stanu", lambda: cli.local_request("status", timeout=12))
                self.response = result
                self.view("Stan projektorów", json.dumps(result, indent=2, ensure_ascii=False))
        elif index in (1, 2):
            self.edit_device(index - 1)
        elif index == 3:
            fields = [Field("host", "IP / nazwa CueServer"), Field("port", "Port UDP", "int"),
                      Field("enabled", "Obsługa Casio", "bool", ("tak", "nie")), Field("name", "Nazwa"),
                      Field("on_command", "CueScript ON"), Field("off_command", "CueScript OFF"),
                      Field("min_interval_s", "Odstęp komend [s]", "float")]
            values = self.form(MENU[index], fields, changed["casio"], "CueServer RS232: 19200 / 8N1, bez CR+LF. UDP bez potwierdzenia.")
            if values is not None:
                changed["casio"].update(values)
                self.persist(changed)
        elif index == 4:
            initial = {**changed["server"], "allowed_clients": ",".join(changed["server"]["allowed_clients"]), "new_token": False}
            fields = [Field("host", "Adres nasłuchu"), Field("port", "Port TLS/TCP", "int"),
                      Field("allowed_clients", "IP / CIDR po przecinku"), Field("new_token", "Wygeneruj nowy token", "bool", ("nie", "tak"))]
            values = self.form(MENU[index], fields, initial, "Pusta lista IP: każdy klient z tokenem. Nowy token wymaga zmiany PC.")
            if values is not None:
                renew = values.pop("new_token")
                values["allowed_clients"] = [item.strip() for item in values["allowed_clients"].split(",") if item.strip()]
                changed["server"].update(values)
                if renew:
                    changed["server"]["token"] = secrets.token_hex(32)
                self.persist(changed)
        elif index == 5:
            fields = [Field("startup", "Start projektorów", choices=("preserve", "on", "off")),
                      Field("log_level", "Poziom logów", choices=("DEBUG", "INFO", "WARNING", "ERROR")),
                      Field("reconnect_interval_s", "Reconnect USB co [s]", "float")]
            values = self.form(MENU[index], fields, changed, "preserve: bez ON/OFF. on/off: jednorazowa próba przy starcie systemu.")
            if values is not None:
                changed.update(values)
                self.persist(changed)
        elif index == 6:
            if self.confirm("Konfiguracja sieci", "Zmiana aktywnego IP może zerwać sesję SSH. Otworzyć nmtui?"):
                self.external("nmtui")
        elif index == 7:
            self.external("raspi-config")
        elif index == 8:
            self.view("Dziennik odbiornika", self.command("journalctl", "-u", "guido-projectors.service", "-n", "150", "--no-pager"))
        elif index == 9:
            if self.wizard:
                self.view("Pierwsza konfiguracja", "Testy ON/OFF są dostępne po zakończeniu kreatora.")
                return
            target = self.choose("Cel testu", ["all", "dell1", "dell2", "casio"])
            if target is None:
                return
            action = self.choose("Akcja testu", ["status", "on", "off"])
            if action is not None and (action == "status" or self.confirm("Test projektora", f"Wykonać rzeczywiste {action.upper()} dla {target}?")):
                result = self.wait("Test projektora", lambda: cli.local_request(action, target))
                self.view("Wynik testu", json.dumps(result, indent=2, ensure_ascii=False))
        elif index == 10:
            self.view("Dane dla aplikacji PC", f"Adresy IP: {self.command('hostname', '-I').strip()}\n\n"
                      f"Port TLS/TCP: {self.config['server']['port']}\n\nToken: {self.config['server']['token']}\n\n"
                      f"SHA256 certyfikatu: {cli.fingerprint()}")
        elif index == 11:
            mode = self.choose("Konfiguracja JSON", ["Eksport", "Import"])
            if mode is None:
                return
            values = self.form(mode, [Field("path", "Pełna ścieżka JSON")], {"path": ""}, "Eksport zawiera token. Nie zawiera prywatnego klucza TLS.")
            if values is None:
                return
            path = Path(values["path"])
            if not path.is_absolute() or path.resolve() == CONFIG_PATH.resolve():
                raise ValueError("Podaj pełną ścieżkę inną niż aktywna konfiguracja")
            if mode == "Import":
                self.persist(load(path))
            elif not path.exists() or self.confirm("Eksport", "Plik istnieje. Nadpisać?"):
                cli.export_config(self.config, path)
                self.view("Eksport", "Zapisano plik z uprawnieniami 0600.")
        elif index == 12:
            if self.wizard:
                self.view("Pierwsza konfiguracja", "Odbiornik zostanie uruchomiony po zakończeniu kreatora.")
            elif self.confirm("Restart usługi", "Uruchomić ponownie odbiornik? Polityka ON/OFF nie jest ponawiana przy restarcie usługi."):
                self.wait("Restart odbiornika", lambda: self.command("systemctl", "restart", "guido-projectors.service"))
                self.next_status = 0
        elif index == 13:
            self.view("Instrukcja", Path("/usr/local/share/doc/guido-projectors/administracja.md").read_text(encoding="utf-8"))

    def poll(self):
        if self.wizard:
            return
        if self.status_job is not None and self.status_job.done.is_set():
            try:
                self.response = self.status_job.result()
                self.status_error = self.response.get("error", "")
            except (OSError, ValueError) as error:
                self.response, self.status_error = {}, str(error)
            self.status_job = None
            self.next_status = time.monotonic() + 5
        if self.status_job is None and time.monotonic() >= self.next_status:
            self.status_job = Job(lambda: cli.local_request("status", timeout=12))

    def run(self):
        while True:
            if not self.enough_room():
                if self.key() == "\x1b" and not self.wizard:
                    return self.config
                continue
            self.poll()
            height, width = self.frame("Pierwsza konfiguracja" if self.wizard else "Sterowanie projektorami",
                                       "↑↓: menu  Enter: otwórz  F5: odśwież  " + ("F2: zakończ kreator" if self.wizard else "Q: wyjście"))
            for index, item in enumerate(MENU):
                self.put(2 + index, 2, f"{index + 1:2}. {item}", curses.A_REVERSE if index == self.selected else 0, 31)
            column = 36
            self.put(2, column, "URZĄDZENIA", curses.A_BOLD)
            for row, line in enumerate(status_lines(self.config, self.response), 4):
                self.put(row, column, line)
            self.put(17, column, f"TLS: {self.config['server']['host']}:{self.config['server']['port']}")
            self.put(18, column, f"Start: {self.config['startup']}   USB: co {self.config['reconnect_interval_s']} s")
            self.put(20, 2, "Konfiguracja lokalna bez logowania; SSH wymaga konta i hasła.")
            self.put(height - 3, 2, self.status_error)
            self.screen.refresh()
            key = self.key()
            if key in (curses.KEY_DOWN, "j"):
                self.selected = (self.selected + 1) % len(MENU)
            elif key in (curses.KEY_UP, "k"):
                self.selected = (self.selected - 1) % len(MENU)
            elif key == curses.KEY_F5:
                self.next_status = 0
            elif key == curses.KEY_F2 and self.wizard:
                try:
                    if self.persist(copy.deepcopy(self.config)):
                        return self.config
                except (ValueError, OSError, subprocess.SubprocessError) as error:
                    self.view("Błąd", str(error))
            elif key in ("q", "Q", "\x1b") or (key in ENTER and self.selected == 14):
                if not self.wizard:
                    return self.config
                try:
                    if self.persist(copy.deepcopy(self.config)):
                        return self.config
                except (ValueError, OSError, subprocess.SubprocessError) as error:
                    self.view("Błąd", str(error))
            elif key in ENTER:
                try:
                    self.dispatch(self.selected)
                except (ValueError, OSError, subprocess.SubprocessError) as error:
                    self.view("Błąd", str(error))
                if self.wizard and self.saved:
                    # Keep editing after individual field saves. F2 completes onboarding.
                    self.saved = False


def open_tui(wizard=False):
    cli.require_root()
    if not sys.stdin.isatty() or not sys.stdout.isatty() or os.environ.get("TERM") in (None, "", "dumb"):
        raise ValueError("TUI wymaga terminala; przez SSH użyj ssh -t. Menu tekstowe: sudo guido-config config-text")
    locale.setlocale(locale.LC_ALL, "")
    config = load() if CONFIG_PATH.exists() else defaults()
    return curses.wrapper(lambda screen: TUI(screen, config, wizard).run())


def menu():
    open_tui()


def setup(activate=False):
    if activate:
        raise ValueError("Kreator TUI jest przeznaczony do pierwszego uruchomienia")
    return open_tui(wizard=True)
