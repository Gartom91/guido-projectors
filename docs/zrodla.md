# Zweryfikowane źródła

- [Raspberry Pi OS — oficjalne obrazy i zgodność modeli](https://www.raspberrypi.com/software/operating-systems/): Lite 32-bit, wydanie 2026-09-15, SHA256 XZ `c766b3fb279b95c12cb4dd22d06f8eab31972c372675d05bd0ca95b060523a7f`.
- [Oficjalny katalog Raspberry Pi Imager V4](https://downloads.raspberrypi.com/os_list_imagingutility_v4.json): adres pobrania, suma obrazu rozpakowanego, tagi `pi3-32bit` i `pi4-32bit`.
- [Personalizacja lokalnych obrazów w Imager](https://github.com/raspberrypi/rpi-imager/blob/main/doc/os_customisation_formats.md): lokalny plik obrazu może nie udostępniać personalizacji; przygotowano własny lokalny kreator.
- [Dell S518WL — instrukcja PL](https://dl.dell.com/manuals/all-products/esuprt_display_projector/esuprt_projector/dell-s518wl-projector_user's_guide_po-pl.pdf).
- [Dell S718QL/S518WL RS232 Protocol Document](https://dl.dell.com/manuals/all-products/esuprt_display_projector/esuprt_projector/dell-s518wl-projector_users-guide2_en-us.pdf): strony 1–2, 4–6; odczytano także renderowane strony PDF, ponieważ część treści jest zapisana jako grafika.
- [Casio XJ-A252 — oficjalna instrukcja rodziny XJ-A](https://support.casio.jp/pdf/007/A257_M256_UsersGuide_JA.pdf): strony 78–80; YK-60, 19200/8N1 i PWR 0/1. Model XJ-A252 potwierdzono z użytkownikiem.
- [CueServer 1 User's Manual, firmware 4.1](https://downloads.interactive-online.com/CueServer%201/Documents/D0420%20CueServer%20Users%20Manual.pdf): strony drukowane 149–153; ustawienia RS232, Generic, operator ~4 i UDP 52737.
- [Python 3.13 curses](https://docs.python.org/3.13/library/curses.html): TUI korzysta z modułu dostępnego w bazowym Raspberry Pi OS, bez dodatkowych pakietów aplikacji. Wywołania curses wykonuje tylko główny wątek.

Podczas opracowania używano lokalnych kopii instrukcji w `docs/reference/`; repozytorium odsyła do oficjalnych źródeł. Parametry istniejącej aplikacji PC ustalono z przesłanego EXE.
