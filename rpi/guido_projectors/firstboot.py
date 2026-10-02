"""Interactive local onboarding; no password or private key in the image."""

import getpass
import os
from pathlib import Path
import pwd
import re
import subprocess

from .cli import ensure_certificate, run, show_connection
from .config import CONFIG_PATH, load
from .tui import setup

MARKER = Path("/etc/guido-projectors/onboarded")


def firstboot():
    os.umask(0o077)
    print("\nGUIDO - pierwsze uruchomienie (monitor HDMI + klawiatura USB)\n")
    # An Imager/cloud-init account can already exist. Never replace its password.
    shadow = {line.split(":")[0]: line.split(":")[1]
              for line in Path("/etc/shadow").read_text().splitlines()}
    users = [user for user in pwd.getpwall() if 1000 <= user.pw_uid < 60000
             and user.pw_shell in ("/bin/bash", "/bin/sh", "/bin/zsh")
             and shadow.get(user.pw_name, "!")[:1] not in ("!", "*", "")]
    if users:
        print("Istniejace konto administratora: " + ", ".join(user.pw_name for user in users))
    else:
        while True:
            username = input("Nazwa nowego konta administratora [guido]: ").strip() or "guido"
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", username):
                print("Wymagane: mala litera, nastepnie male litery, cyfry, '_' lub '-'.")
                continue
            try:
                existing = pwd.getpwnam(username)
            except KeyError:
                break
            if 1000 <= existing.pw_uid < 60000 and shadow.get(username, "!")[:1] in ("!", "*", ""):
                break
            print("Ta nazwa jest juz uzywana; wybierz inna.")
        while True:
            password = getpass.getpass("Haslo konta i SSH (min. 12 znakow): ")
            confirmation = getpass.getpass("Powtorz haslo: ")
            if len(password) >= 12 and password == confirmation and "\n" not in password and "\x00" not in password:
                break
            print("Hasla musza byc identyczne i miec co najmniej 12 znakow.")
        try:
            pwd.getpwnam(username)
        except KeyError:
            run("useradd", "--create-home", "--shell", "/bin/bash", "--groups", "sudo,adm,dialout,netdev", username)
        else:
            run("usermod", "--shell", "/bin/bash", "--append", "--groups", "sudo,adm,dialout,netdev", username)
        run("chpasswd", input=f"{username}:{password}\n", text=True)
        del password, confirmation
        print(f"Utworzono konto: {username}")
    # SSH host keys and API certificates are generated on this particular card.
    run("ssh-keygen", "-A", stdout=subprocess.DEVNULL)
    Path("/run/sshd").mkdir(mode=0o755, exist_ok=True)
    run("sshd", "-t")
    run("systemctl", "enable", "--now", "ssh.service", stdout=subprocess.DEVNULL)
    if not CONFIG_PATH.exists():
        setup(activate=False)
    else:
        # Resume safely if power failed between saving settings and creating keys.
        config = load()
        ensure_certificate()
        show_connection(config)
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    with MARKER.open("w") as file:
        file.write("configured\n")
        file.flush()
        os.fsync(file.fileno())
    run("systemctl", "start", "--no-block", "guido-projectors.service")
    print("\nKonfiguracja zakonczona. TUI uruchomi sie automatycznie.")
    input("Dane dla PC znajdziesz w TUI. Enter otwiera lokalny panel: ")
