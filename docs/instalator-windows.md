# Instalator Windows — pojedynczy plik

## Instalacja karty i aplikacji PC

1. Pobierz [Install-Guido.cmd](https://github.com/Gartom91/guido-projectors/releases/latest/download/Install-Guido.cmd). To cały wymagany plik startowy; obrazu nie pobierasz ręcznie.
2. Uruchom plik dwuklikiem na Windows 10/11 x64 z dostępem do Internetu. Nie wymaga Git, Pythona, .NET SDK ani WSL. Skrypt może leżeć w Pobranych lub na nośniku USB; pobrane dane zapisuje na dysku PC.
3. Instalator pobierze z konkretnego wydania GitHub Releases obraz `.img.xz`, samodzielny EXE i dokumentację. Zweryfikuje ich rozmiary i SHA256 przypięte wewnątrz skryptu. Gdy zabraknie Raspberry Pi Imager 2.x, pobierze oficjalny instalator producenta, także z przypiętym SHA256, i otworzy jego kreator; ta instalacja może wymagać uprawnień administratora/UAC.
4. W otwartym Imager wybierz RPi 3B, 4B albo 5, system **Guido — projektory / TUI**, następnie właściwą kartę SD 32 GB. Sprawdź nazwę i pojemność karty. Zatwierdź wymazanie, poczekaj na zapis i weryfikację. Instalator nie wybiera nośnika i sam nie wykonuje zapisu fizycznego dysku.
5. Uruchom RPi z kartą, HDMI i klawiaturą. Na RPi ustaw konto/hasło SSH oraz urządzenia. Konto, token i certyfikaty są indywidualne dla danej karty. Dane połączenia PC znajdziesz w TUI.
6. Aplikację otworzysz skrótem **Projektory Shadok** na pulpicie lub w menu Start → **Guido Projektory**. Wpisz dane połączenia RPi. Skrót **Przygotuj kartę SD** ponownie otwiera Imager z pobranym obrazem.

Na PC potrzebne jest ok. 1,5 GB wolnego miejsca. Instalator 1.2.0 pobiera wspólny obraz 1.2.0 dla RPi 3B/4B/5, sprawdzony EXE aplikacji PC 1.1.2 i dokumentację z wydania GitHub 1.2.0. Pliki trafiają do `%LOCALAPPDATA%\GuidoProjectors\1.2.0`. Wszystkie pola adresów nowej aplikacji PC są puste; konfigurujesz je sam. Istniejące prywatne ustawienia aplikacji w `%LOCALAPPDATA%\ShadokProjektory-RPi` pozostają zachowane. Instalator nie uruchamia aplikacji sterującej i nie wysyła komend do urządzeń.

Pobrany skrypt działa bez logowania do GitHub; repozytorium i wydanie są publiczne. Windows może wyświetlić ostrzeżenie o pobranym pliku bez podpisu. Pobieraj go wyłącznie z podanego repozytorium. Skrypt nie zmienia globalnej polityki PowerShell, zapory ani ustawień SSH/sieci PC. Tryb emulatora jest osobnym, wcześniej przygotowanym środowiskiem i nie jest instalowany.

## Powtórzenie i obsługa błędów

Prawidłowo pobrane pliki są wykorzystywane ponownie po ponownym sprawdzeniu SHA256. Pobranie uszkodzone lub przerwane jest ponawiane maksymalnie trzy razy. Niekompletny plik `.part` nie jest używany. Blokada katalogu zapobiega dwóm jednoczesnym instalacjom do tej samej wersji.

Jeżeli Imager był już otwarty, zamknij go przed uruchomieniem skrótu przygotowania karty. Jeśli katalog Guido nie pojawi się, wybierz **Use custom / Użyj własnego** i wskaż pobrany `.img.xz` z katalogu instalacji. Nie personalizuj obrazu w Imager: konfigurację realizuje pierwszy kreator na RPi.

W razie odmowy UAC lub anulowania instalacji Imager poprawnie pobrane pliki pozostają na dysku. Uruchom skrypt ponownie po rozwiązaniu błędu; informacja w konsoli wskazuje etap. Karta jest zapisywana dopiero po osobnym zatwierdzeniu w Imager.

Zaawansowany wariant PowerShell, po pobraniu `Install-Guido.ps1` z tego samego wydania, pozwala zmienić katalog lub tylko pobrać pliki. Użyj standardowego „Uruchom w programie PowerShell” albo uruchom poniższe polecenia, jeżeli lokalna polityka zezwala na skrypty:

```powershell
.\Install-Guido.ps1 -InstallDirectory C:\Guido -DownloadOnly
.\Install-Guido.ps1 -NoLaunch
```

`-DownloadOnly` nie instaluje Imager, nie tworzy skrótów i nie otwiera okien. `-NoLaunch` wykonuje instalację i tworzy skróty, lecz nie otwiera Imager po jej zakończeniu. Skrypt odmawia zapisania pobieranych danych do głównego katalogu dysku, lokalizacji sieciowej lub nośnika oznaczonego jako wymienny.

Wariant CMD obsługuje te same tryby: `Install-Guido.cmd --download-only` i `Install-Guido.cmd --no-launch`. Nie wymaga zmiany polityki wykonywania plików PowerShell.

## Pakowanie kolejnego wydania

Najpierw zbuduj aplikację PC i obraz według README. Wersja instalatora `VERSION` w `installer/package.py` może być nowsza od wersji obrazu. Tag wydania instalatora to `v<VERSION>`. Obraz i EXE są publikowane razem w wydaniu wersji obrazu; poprawka samego instalatora może używać tych samych plików. Nazwę obrazu skrypt odczytuje z `image-manifest.json`. Pobierz przypięty oficjalny Imager do katalogu budowania, a następnie uruchom pakowanie:

```powershell
New-Item -ItemType Directory -Force tmp\installer
Invoke-WebRequest -UseBasicParsing https://github.com/raspberrypi/rpi-imager/releases/download/v2.0.11.1/imager-v2.0.11.1.exe -OutFile tmp\installer\imager-v2.0.11.1.exe
python installer/package.py
powershell -NoProfile -Command "& ([scriptblock]::Create((Get-Content -Raw tests/installer.Tests.ps1)))"
```

Skrypt pakowania odczytuje metadane obrazu, oblicza hashe aktualnych plików i generuje `output/installer/Install-Guido.cmd`, `.ps1`, `release.json`, ZIP dokumentacji i wspólne `SHA256SUMS.txt`. Aktualizuje też przypięte metadane w źródłowym PS1. Pliki instalatora publikuj w nowym GitHub Releases. Obraz, EXE i ich metadane muszą być dostępne pod adresami z `release.json`; nie powielaj ich przy wydaniu samej poprawki instalatora. Do Git trafiają źródła i dokumentacja. Oficjalny instalator Imager jest pobierany z repozytorium producenta.

Integrator Imager korzysta z udokumentowanego `--repo <plik>` oraz lokalnego katalogu JSON; katalog zawiera rozmiar i SHA256 rozpakowanego obrazu, trzy modele RPi z tagami `pi3-32bit`, `pi4-32bit`, `pi5-32bit` i `init_format=none`. Źródła: [argumenty Imager](https://github.com/raspberrypi/rpi-imager/blob/v2.0.11.1/src/main.cpp), [schemat katalogu](https://github.com/raspberrypi/rpi-imager/blob/v2.0.11.1/doc/json-schema/os-list-schema.json).
