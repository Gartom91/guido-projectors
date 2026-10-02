# Instalacja — RPi 3B / RPi 4B / RPi 5

## Pliki

- `guido-projectory-rpi3-rpi4-rpi5-1.2.0.img.xz`: wspólny obraz dla wszystkich trzech modeli, z pełnym TUI, bez środowiska graficznego.
- `pc/ShadokProjektory-RPi.exe`: aplikacja Windows 10/11 x64; nie wymaga instalacji .NET.
- `SHA256SUMS.txt` i `image-manifest.json`: kontrola integralności wydania.

## Wgranie karty

Najprościej na Windows: pobierz sam [Install-Guido.cmd](https://github.com/Gartom91/guido-projectors/releases/latest/download/Install-Guido.cmd) i uruchom go. Obraz i aplikacja PC zostaną pobrane automatycznie. Po sprawdzeniu sum skrypt otworzy Imager z katalogiem Guido. Jeśli brakuje Imager 2.x, pobierze oficjalny instalator. [Opis, wymagania i tryb samego pobierania](instalator-windows.md).

W Raspberry Pi Imager wybierz model używany do testu, następnie system z własnego pliku (`Use custom` / „Użyj własnego”). Wskaż `.img.xz`; nie trzeba go rozpakowywać. Wybierz właściwą kartę 32 GB, zapisz i wykonaj weryfikację zapisu w Imager. Zapis nadpisuje zawartość wskazanej karty.

Obraz jest przeznaczony do pierwszej konfiguracji na lokalnym monitorze. Lokalny obraz w Imager może nie udostępniać personalizacji konta; własny kreator obrazu tworzy je podczas pierwszego startu. Nie ma wspólnego fabrycznego loginu i hasła.

## Pierwszy start

1. Podłącz HDMI, klawiaturę, Ethernet oraz oba konwertery USB–RS232. Pierwsze uruchomienie może potrwać kilka minut, w tym powiększenie partycji systemowej.
2. Kreator GUIDO wyświetli się na konsoli. Wybierz nazwę administratora i hasło, co najmniej 12 znaków. Jeśli poprawne konto zostało utworzone wcześniej przez personalizację obrazu, jego hasło pozostaje zachowane.
3. Po ustawieniu konta otworzy się TUI. Wybierz konfigurację sieci, jeżeli jest potrzebna: `nmtui` pozwala ustawić Ethernet, Wi-Fi, DHCP lub stały adres. Bez zmiany konfiguracji Ethernet korzysta z ustawień bazy Raspberry Pi OS, z DHCP.
4. Przypisz Dell 1 i Dell 2. Preferuj `/dev/serial/by-id/...`; jeśli konwertery nie mają różnych numerów seryjnych, wybierz `/dev/serial/by-path/...`. Sprawdź przypisanie przez odłączenie i ponowne podłączenie jednego konwertera. Samo otwarcie portu nie dowodzi poprawnego okablowania do projektora.
5. Wpisz aktualny adres CueServer oraz port UDP. Domyślnie `52737`. Nieznane urządzenie można pozostawić wyłączone w konfiguracji i ustawić później.
6. Pozostaw start `preserve`, aby RPi nie wysyłało ON/OFF przy uruchomieniu.
7. F2 na ekranie głównym kończy kreator. Następnie automatycznie otworzy się lokalne TUI bez logowania. W „Dane połączenia PC” znajdziesz adres RPi, port TLS/TCP, token i SHA256 certyfikatu.

Strzałki i Enter otwierają pozycje menu. Tab przechodzi między polami; Spacja zmienia wybór. F2 zatwierdza formularz, Esc anuluje. Minimum 80×24 znaków. TUI odświeża stan urządzeń; nie włącza projektorów przy wybranym `preserve`.

SSH zostaje włączone po ustawieniu konta. Przykład połączenia, gdzie wartości w nawiasach trzeba zastąpić własnymi:

```text
ssh <nazwa_konta>@<adres_RPi>
sudo guido-config
```

Hasło SSH i token aplikacji są różnymi danymi. Hasło konta zmienisz poleceniem `passwd`. TLS chroni osobny kanał PC–RPi, a certyfikat jest sprawdzany po odcisku. Certyfikat i klucze SSH są tworzone na danej karcie.

Interaktywne logowanie administratora przez SSH otwiera TUI automatycznie. Q wraca do powłoki. Lokalne TUI ma uprawnienia administratora bez logowania, zgodnie z wybranym trybem; osoba z fizycznym dostępem do klawiatury może zmieniać konfigurację.

## CueServer i Casio

Przed zmianą portu CueServer sprawdź, czy nie jest używany do innego urządzenia. Konfiguracja RPi nie zmienia automatycznie ustawień CueServer.

W CueServer: **Main → System Preferences → Port Settings → Serial Port (RS-232)**:

| Pole | Wartość dla Casio XJ-A252 |
|---|---|
| Baud Rate | 19200 |
| Serial Format | Normal (8-N-1) |
| Add CR+LF to Output Strings | wyłączone |
| Local Echo | wyłączone |
| Incoming Serial Protocol | Ignore, jeśli port obsługuje wyłącznie ten projektor |
| Outgoing Serial Protocol | Generic |

Komendy domyślne w RPi: `"(PWR1)"~4` i `"(PWR0)"~4`. Casio XJ-A252 wymaga właściwego kabla YK-60 do swojego złącza sterowania. Parametry i składnia są opisane w [dokumentacji producentów](zrodla.md).

UDP w tej integracji nie zwraca potwierdzenia stanu Casio. „Wysłano” wymaga sprawdzenia działania na fizycznym projektorze.

## Aplikacja PC

W ustawieniach wpisz IP RPi, domyślny port `41794`, token i odcisk SHA256 z menu RPi. Można skopiować odcisk z dwukropkami; program je usuwa. Ustawienia są zapisywane w `%LOCALAPPDATA%\ShadokProjektory-RPi\settings.json`.

WDARCIE WODY steruje wszystkimi projektorami włączonymi w konfiguracji RPi. Stan projektorów odczytuje oba Delle; dla Casio pokazuje brak dostępnego potwierdzenia. POŻAR i Zasilanie wysyłają dotychczasowe komendy UDP do osobno konfigurowanych adresów. Wszystkie pola adresów aplikacji PC są domyślnie puste. Można skonfigurować wyłącznie RPi i pozostawić pozostałe funkcje nieaktywne; POŻAR/Zasilanie wymagają uzupełnienia właściwych odbiorników przed wysłaniem.

W razie błędu jednego Della pozostałe urządzenia są obsługiwane niezależnie. Program pokazuje wyniki oddzielnie; działanie grupy nie jest transakcją „wszystko albo nic”. Nie ponawiaj OFF/ON automatycznie po timeout bez sprawdzenia stanu.

## Test odbiorczy na RPi 3B / 4B / 5

1. Start bez konwerterów: kreator i konsola muszą działać. Nie oczekuj potwierdzonej komunikacji z Dellami bez podłączonych projektorów.
2. Podłącz konwertery, przypisz stabilne ścieżki i odczytaj stan Dell 1/Dell 2 w terminalu.
3. Włącz jeden Dell, sprawdź obraz i odczyt stanu, następnie wyłącz. Powtórz dla drugiego.
4. Sprawdź Casio przez CueServer i potwierdź fizyczne ON/OFF.
5. Sprawdź przyciski WDARCIE WODY w aplikacji PC; potem osobno POŻAR i Zasilanie na urządzeniach instalacji.
6. Uruchom ponownie RPi z `startup=preserve`: nie powinno być komend ON/OFF w logach startu.
7. Odłącz i podłącz konwerter. Po upływie ustawionego czasu ponownego podłączenia odczyt stanu ma wrócić.

Ten sam plik obrazu służy do wgrania RPi 3B, 4B i 5. Przy zmianie modelu i portu USB ścieżki `by-path` mogą się różnić; trzeba je ponownie przypisać. RPi 5 korzysta z oficjalnego jądra 64-bit i aplikacji armhf; nie wymaga osobnego obrazu ani ręcznej zmiany `config.txt`. Nie wykonano jeszcze fizycznego testu rozruchu na żadnym z tych modeli; wymagany jest opisany odbiór sprzętowy.
