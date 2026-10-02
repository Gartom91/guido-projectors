# Walidacja wydania 1.1.0

## Potwierdzone

- Suma SHA256 pobranego oficjalnego obrazu `.img.xz` oraz rozpakowanego `.img` zgadza się z katalogiem Raspberry Pi.
- W obrazie są pliki firmware/DTB dla RPi 3B i 4B. Partycje i firmware zachowano z oficjalnej bazy.
- Każdy dodany plik jest ponownie odczytywany z rootfs i porównywany po SHA256. Manifest zapisuje sumy i tryby dostępu.
- Sumy gotowego wydania 1.1.0 znajdują się w `output/SHA256SUMS.txt` i `output/image-manifest.json`. Poprzedni obraz 1.0.0 nie zawiera pełnego TUI.
- `e2fsck -f -n` dla zmodyfikowanej partycji rootfs przechodzi wszystkie pięć etapów kontroli.
- Testy `pytest`: 38 zaliczonych. Obejmują protokoły, rekonfigurację i awarie z wydania 1.0.0 oraz rzeczywisty terminal curses: nawigację, zmianę rozmiaru okna, anulowanie, zapis nazwy z polskimi znakami, pierwszy kreator bez ON/OFF, ochronę przed nadpisaniem konfiguracji innej sesji, warunki autostartu SSH, blokadę prawdziwych urządzeń/zewnętrznych adresów w emulatorze, zamykanie jego zasobów i odrzucenie drugiej instancji.
- Aplikacja Windows: `dotnet build` bez błędów i ostrzeżeń, `dotnet publish` tworzy samodzielny EXE. Wykonano również `dotnet test`; projekt WinForms nie zawiera adaptera testów .NET, więc właściwe testy komunikacji realizują tryby `--self-test` i `--integration-test`.
- `--self-test`: połączenie TLS z przypiętym certyfikatem, kodowanie żądania i odpowiedzi, odrzucenie niepełnych danych dostępu.
- Faktyczny opublikowany EXE Windows połączył się z odbiornikiem pracującym na Pythonie ARM 3.13.5 i OpenSSL 3.5.7 z obrazu, uruchomionym pod QEMU. Odczyt stanu, ON oraz OFF obsłużyły dwa oddzielne symulowane porty RS232 i UDP Casio. W tym teście działał rzeczywisty odstęp 5 s po ON.
- ARM `systemd-analyze verify` z obrazu zaakceptował własne usługi bez błędów. Sprawdzono symlinki autostartu i maskowanie fabrycznego kreatora konta, zastąpionego kreatorem GUIDO.
- TUI zainstalowane w obrazie uruchomiono na Pythonie ARM i ncurses pod QEMU w terminalu 100×30 z `TERM=linux`. Wyświetlono ekran stanu i formularz Dell, zmieniono i zapisano nazwę, potwierdzono rzeczywisty kod klawisza F2 konsoli Linux. Symulowane urządzenia nie otrzymały ON/OFF. Backend tego testu jest celowo symulowany; osobny test integracyjny sprawdza rzeczywisty odbiornik ARM.
- ARM `visudo -c` zaakceptował wszystkie reguły, w tym ograniczony wyjątek autostartu TUI. `systemd-analyze verify` obejmuje teraz również `guido-console.service` i jego kolejność względem pierwszego kreatora i odbiornika.
- Widok główny aplikacji Windows sprawdzono wizualnie na wyrenderowanym zrzucie.
- Gotowy emulator WSL2 uruchomił rzeczywisty odbiornik oraz dwa wirtualne porty RS232 i CueServer. Opublikowany EXE zaliczył status/ON/OFF przez TCP/TLS. Trzy natywne odbiorniki UDP Windows odebrały i porównały wszystkich 15 pakietów testowych. Odbiorniki wcześniej zweryfikowały swoje porty pakietem gotowości; wynik nie dowodzi rozwiązania wcześniejszej utraty pierwszego UDP w instalacji.
- Ponownie zbudowano i opublikowano aplikację PC po dodaniu `--settings`. Test własny EXE sprawdza także oddzielny plik ustawień emulatora, bez nadpisania zwykłego profilu aplikacji.
- Test interaktywny gotowego emulatora wykonał rzeczywiste ON i OFF z TUI przez lokalny socket odbiornika i wirtualne RS232/UDP. Sprawdzono również, że zamknięcie samego panelu nie zatrzymuje odbiornika. Wyniki są w `tmp/emulator/tui-verification.json`.

## Instalator Windows i publikacja

- Instalator sprawdzono na Windows PowerShell 5.1: 30 asercji dotyczących dozwolonych adresów HTTPS, długości/SHA256, pamięci pobierania, ponowień po uszkodzeniu, nieużywania częściowych danych, zachowania istniejącego poprawnego pliku po błędzie, skrótów i pełnego przepływu samego pobierania z kontrolowanymi danymi.
- Osobno sprawdzane są rzeczywiste pobrania z opublikowanego GitHub Releases i zgodność katalogu Imager z oficjalnym schematem. Plik CMD zawiera cały kod instalatora; nie pobiera kolejnego skryptu do wykonania.
- Instalator sam pobiera obraz, EXE i dokumentację. Fizyczny zapis, wskazanie nośnika i potwierdzenie wymazania wykonuje użytkownik w Raspberry Pi Imager.
- Test CMD uruchomionego z PowerShell 7 wykrył konflikt odziedziczonych ścieżek modułów z Windows PowerShell 5.1. Poprawka 1.1.1 ustawia standardową ścieżkę modułów tylko wewnątrz procesu CMD (`setlocal`) i oblicza SHA256 strumieniowo przez .NET. Obraz i aplikacja PC pozostają w wersji 1.1.0.
- Instalator pobrany anonimowo z GitHub wykonał rzeczywiste pobranie obrazu, EXE i dokumentacji z poprawnymi SHA256, a następnie cały tryb instalacji bez otwierania Imager: rozpakowanie dokumentacji i tworzenie skrótów.
- Aplikacja PC 1.1.2 ma puste adresy urządzeń. Test własny sprawdza brak adresów w wartościach początkowych, możliwość zapisania niepełnej konfiguracji i odrzucenie POŻAR/Zasilanie przed wysyłaniem, gdy brakuje właściwych odbiorników.

## Ograniczenia wymagające testu w instalacji

Nie wykonano fizycznego startu RPi 3B/4B ani testu na prawdziwych konwerterach, projektorach i CueServer. Test ARM jest emulacją aplikacji, a nie rozruchem całego urządzenia. TUI sprawdzono w terminalach testowych, a logikę autostartu SSH ze stubem sudo. Fizyczny ekran/klawiatura, pierwszy kreator konta, uruchomienie panelu przez PID 1 na tty1, DHCP/Wi-Fi, powiększenie partycji oraz rzeczywiste logowanie SSH wymagają odbioru na RPi 4.

Datagramy Casio zostały odebrane i porównane bajt po bajcie w symulacji ARM/Linux. Test UDP Windows→WSL zakończył się timeoutem odbioru mimo udanego przekazania datagramów do stosu sieciowego. Dalszy test na aktywnym odbiorniku Windows ujawnił utratę pierwszego z pięciu pakietów przy nowym porcie lokalnym; kolejna seria na tym samym porcie odebrała wszystkie pięć oryginalnych komend POŻAR/Zasilanie w prawidłowej kolejności i treści. Niezależny pakiet kontrolny Pythona został odebrany. Przyczyna utraty pierwszego pakietu nie została ustalona; nie zmieniano reguł bezpieczeństwa. Zachowanie UDP na tym hoście nie jest w pełni potwierdzone. Te przyciski wymagają testu na docelowym PC i urządzeniach.

Firmware CueServer, aktualne adresy instalacji, rodzaje konwerterów i okablowanie nie są znane. Konfiguracja jest udostępniona w terminalu. Brak odpowiedzi UDP oznacza, że program nie może potwierdzić wykonania komendy Casio.

## Odtworzenie testu ARM + PC

Po zbudowaniu obrazu rozpakuj jego rootfs do `/tmp/guido-image-build/rootfs` przez `debugfs rdump`, skopiuj `qemu-arm-static` do jego `/usr/bin`, a następnie w WSL:

```text
python3 -m pytest tests -q
sudo python3 tests/integration_arm_pc.py
sudo python3 tests/verify_tui_arm.py
```

Skrypt korzysta wyłącznie z PTY i lokalnego symulatora CueServer. Tymczasowe bind-mounty są tworzone we wskazanym katalogu testowym i usuwane po teście; proces ARM jest zatrzymywany. Tryb `--pc-udp` dodatkowo sprawdza odbiór pięciu oryginalnych komend UDP z Windows i na tym hoście ujawnił opisane ograniczenie.

Test aktywnego odbiornika Windows: `python tests/windows_udp_loopback.py`. Zwraca błąd, jeżeli choć jeden z pięciu pakietów nie został odebrany lub różni się treścią/kolejnością; zapisuje raport w `tmp/windows-udp-active-receiver.json`.
