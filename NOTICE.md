# Składniki i źródła

Źródła aplikacji Guido, aplikacji PC, emulatora, instalatora i testów znajdują się w tym repozytorium. Oryginalny dostarczony EXE i lokalne kopie instrukcji producentów nie są częścią repozytorium; dokumentacja projektu odsyła do instrukcji źródłowych.

Obraz zawiera Raspberry Pi OS Lite 32-bit Trixie, bazę z 2026-09-15, i pakiety Debian. Poszczególne składniki zachowują swoje licencje; teksty licencji i informacje o prawach autorskich są w `/usr/share/doc/*/copyright` na obrazie. Oficjalne obrazy i repozytoria źródeł: [Raspberry Pi OS](https://www.raspberrypi.com/software/operating-systems/), [Raspberry Pi packages](https://archive.raspberrypi.com/debian/), [Raspbian](https://archive.raspbian.org/raspbian/), [Debian Sources](https://sources.debian.org/). Adres bazy i jej SHA256 są w `image/build.py` oraz `image-manifest.json` wydania.

Aplikacja PC zawiera środowisko Microsoft .NET, publikowane przez `dotnet publish --self-contained`. Źródła, licencje i informacje o składnikach: [.NET Runtime](https://github.com/dotnet/runtime) i [Windows Forms](https://github.com/dotnet/winforms).

Instalator pobiera Raspberry Pi Imager z oficjalnego wydania producenta tylko wtedy, gdy brak zgodnej instalacji. Imager nie jest modyfikowany. [Źródła i licencja Imager](https://github.com/raspberrypi/rpi-imager).
