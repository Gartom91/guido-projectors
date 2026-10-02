# Guido — sterowanie projektorami z Raspberry Pi

Obraz dla Raspberry Pi 3B i 4B, z aplikacją tekstową obsługującą dwa Dell S518WL przez dwa konwertery USB–RS232 oraz jeden Casio XJ-A252 przez CueServer 1 Mini. Dołączona aplikacja Windows 10/11 x64 zastępuje przesłany `ShadokProjektory.exe`; zachowuje funkcje WDARCIE WODY, POŻAR i Zasilanie.

## Uruchomienie

Na Windows 10/11 x64 pobierz tylko [Install-Guido.cmd](https://github.com/Gartom91/guido-projectors/releases/latest/download/Install-Guido.cmd) i uruchom dwuklikiem. Skrypt sam pobierze obraz oraz aplikację PC z GitHub, sprawdzi SHA256, utworzy skróty i otworzy Raspberry Pi Imager z systemem Guido. Wybierz kartę SD i zatwierdź jej wymazanie w Imager. Nie są wymagane Git, .NET SDK, Python ani WSL. [Szczegóły instalatora](docs/instalator-windows.md).

Gotowe pliki są w [GitHub Releases](https://github.com/Gartom91/guido-projectors/releases/latest). Instrukcja ręczna:

1. W Raspberry Pi Imager wybierz własny obraz `output/guido-projectory-rpi3-rpi4-1.1.0.img.xz` i kartę 32 GB. Wskazana karta zostanie nadpisana.
2. Pierwszy start wykonaj z monitorem HDMI i klawiaturą USB. Kreator ustawi konto, hasło SSH, porty Dell, adres CueServer i odbiornik sieciowy.
3. Uruchom `output/pc/ShadokProjektory-RPi.exe`. W ustawieniach wpisz IP RPi, port, token i odcisk SHA256 certyfikatu wyświetlone na RPi.
4. Pełne TUI otwiera się automatycznie na lokalnym monitorze bez logowania oraz po interaktywnym zalogowaniu administratora przez SSH. Ręczne uruchomienie: `sudo guido-config`.

TUI: strzałki i Enter wybierają opcję, Tab przechodzi między polami, Spacja zmienia wybór, F2 zatwierdza formularz, Esc anuluje. Minimum 80×24 znaków. Ekran stanu odświeża się bez wysyłania ON/OFF. Odbiornik działa niezależnie od panelu. Lokalny panel ma pełne uprawnienia administracyjne, zgodnie z wybranym trybem bez logowania; SSH nadal wymaga konta i hasła.

Domyślny start systemu i restart usługi nie przełączają zasilania projektorów. Opcje `on` i `off` wykonują jednorazową próbę po starcie systemu; są wyraźnie konfigurowalne.

## Dokumentacja

- [Instalacja i test na RPi 4](docs/instalacja.md)
- [Administracja w terminalu](docs/administracja.md)
- [Protokoły i ustalenia z przesłanego EXE](docs/protokoly.md)
- [Walidacja i ograniczenia](docs/walidacja.md)
- [Źródła producentów](docs/zrodla.md)
- [Gotowy emulator na tym PC](docs/emulator.md): launchery `emulation/Uruchom-TUI.cmd` i `emulation/Uruchom-PC.cmd`.
- [Instalator Windows i przygotowanie wydania](docs/instalator-windows.md)
- [Składniki i źródła](NOTICE.md)

## Budowanie

Python na RPi korzysta wyłącznie z biblioteki standardowej; nie wymaga pobierania pakietów przy uruchomieniu. Aplikacja Windows jest publikowana z własnym środowiskiem .NET, w jednym EXE.

Na Windows z WSL Ubuntu:

```powershell
dotnet build pc/ShadokProjektory.RPi/ShadokProjektory.RPi.csproj -c Release
dotnet test pc/ShadokProjektory.RPi/ShadokProjektory.RPi.csproj -c Release --no-build
dotnet publish pc/ShadokProjektory.RPi/ShadokProjektory.RPi.csproj -c Release -o output/pc
wsl -d Ubuntu -- python3 -m pytest tests -q
wsl -d Ubuntu -u root -- python3 image/build.py
```

Budowanie obrazu wymaga `curl`, `xz`, `debugfs`, `e2fsck`, `mcopy`. Emulacja testowa dodatkowo wymaga `qemu-arm-static` i `pytest`. Obraz jest modyfikowany jako plik; skrypt budowania nie zapisuje na dyskach fizycznych. Dane bazowe są przypięte do konkretnego wydania i dwóch sum SHA256. Plik `output/image-manifest.json` zawiera sumę obrazu i każdego dodanego pliku.

Repozytorium zawiera źródła aplikacji i skrypt odtworzenia obrazu. Wydanie nie zawiera skonfigurowanego hasła, tokenu ani kluczy prywatnych urządzenia.
