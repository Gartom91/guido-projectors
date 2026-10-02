# Gotowe środowisko testowe na tym PC

Środowisko jest przygotowane w istniejącej maszynie WSL2 Ubuntu. Nie wymaga Raspberry Pi, konwerterów ani projektorów. Uruchamia rzeczywisty kod odbiornika i TUI, dwa wirtualne porty RS232 i lokalny symulator CueServer. Aplikacja PC łączy się przez rzeczywisty TCP/TLS; funkcje POŻAR/Zasilanie trafiają do symulatorów UDP na Windows.

## Uruchomienie

1. Otwórz `emulation/Uruchom-TUI.cmd`. Pojawi się TUI z dwoma skonfigurowanymi Dellami i Casio.
2. Otwórz `emulation/Uruchom-PC.cmd`. Otworzy aplikację Windows z gotowymi adresami, tokenem i certyfikatem emulatora.
3. W TUI wybierz „Test ON / OFF” albo użyj WDARCIE WODY w aplikacji PC. Delle przechodzą przez rozgrzewanie/chłodzenie i zwracają stan. Casio zachowuje brak potwierdzenia UDP; odbiór i stan symulatora są w dzienniku.
4. W menu „Dziennik zdarzeń” są logi rzeczywistego odbiornika, symulatorów projektorów i trzech tras UDP z Windows. Testuj także POŻAR i Zasilanie; wyjścia są symulowane, bez sterowania urządzeniami instalacji.

Strzałki / Enter: menu, Tab: pola, Spacja: wybór, F2: zatwierdzenie, Esc: anulowanie. Minimum 80×24 znaków.

Q zamyka panel, ale odbiornik nadal działa. Enter w tym samym oknie wraca do TUI. Wpisz X, aby wyłączyć całe środowisko i wszystkie jego procesy. Ctrl+C również zamyka środowisko. Nie uruchamiaj dwóch kopii równocześnie.

## Konfiguracja i izolacja

Ustawienia emulatora są w WSL: `~/.local/share/guido-emulator/config.json`. Nazwy, timeouty, obsługa urządzeń, logowanie, token i polityka startu są zapisywane i mogą być testowane. Przy ponownym starcie emulator przypisuje nowe wirtualne porty i włącza trzy symulowane urządzenia. Pozostałe ustawienia zachowuje. Ponowne otwarcie launchera traktowane jest jak nowy start urządzenia; restart odbiornika z TUI nie powtarza polityki ON/OFF.

Aplikacja Windows używa osobnego `tmp/emulator/pc-settings.json`, przez argument `--settings`. Jej zwykłe ustawienia w LOCALAPPDATA pozostają osobne. Po zmianie tokenu/portu w TUI zamknij i ponownie otwórz launcher PC, aby wczytać nowy plik.

Odbiornik emulatora i wszystkie symulatory UDP nasłuchują wyłącznie na localhost. Emulator odrzuca przypisanie prawdziwych portów szeregowych i zewnętrznego CueServer. Nie zmienia ustawień sieci, SSH ani konfiguracji Windows/WSL. Menu nmtui/raspi-config w emulatorze wyświetla informację o zakresie testu; te funkcje systemowe należy sprawdzić na RPi.

Symulowane stany: `tmp/emulator/simulation-state.json`; wyjścia POŻAR/Zasilanie i licznik reconnect: `tmp/emulator/windows-outputs.json`. Stan wyjścia 8 jest tylko stanem wirtualnego wyjścia CueServer; emulator nie zakłada sposobu podłączenia przekaźnika instalacji.

## Co ten test potwierdza

TUI, konfigurację aplikacji, komunikację TCP/TLS, dokładne pakiety Dell, odczyt stanu, komendy Casio i pakiety funkcji dodatkowych. Delle mają symulowane dwusekundowe przejścia, z zachowaniem rzeczywistego pięciosekundowego ograniczenia odbiornika po ON.

To środowisko uruchamia aplikację na Pythonie WSL2; dodatkowo sprawdzono TUI na Pythonie ARM z obrazu pod QEMU. Nie jest to pełny rozruch obrazu Raspberry Pi. Pierwszy kreator konta, autostart PID 1 na tty1, SSH, sieć RPi i sprzęt wymagają testu na RPi 4.

Launcher korzysta z zainstalowanego WSL2 Ubuntu i lokalnego Python Windows dostarczonego z Codex. Symulatory UDP sprawdzają gotowość swoich portów pakietem kontrolnym. Nie zmieniono protokołu UDP aplikacji ani reguł zapory. Opisane wcześniej ograniczenie UDP na tym hoście wymaga nadal testu z docelowymi urządzeniami.
