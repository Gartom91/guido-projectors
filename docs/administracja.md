# Administracja GUIDO w terminalu

TUI uruchamia się automatycznie lokalnie na HDMI bez logowania oraz po interaktywnym logowaniu administratora przez SSH na port 22. Dostęp SSH wymaga własnego konta i hasła. Ręcznie: `sudo guido-config`.

Strzałki i Enter wybierają opcję, Tab / Shift+Tab przechodzą między polami, Spacja / lewo-prawo zmieniają pola wyboru, F2 zatwierdza formularz, Esc anuluje. Ctrl+U czyści pole tekstowe. F3 w formularzu Dell pokazuje dostępne porty. F5 odświeża ekran stanu. Logi i instrukcję przewija się strzałkami lub PgUp/PgDn. Terminal musi mieć co najmniej 80×24 znaków.

W pierwszym kreatorze po ustawieniu konta otwiera się TUI konfiguracji. F2 na ekranie głównym kończy kreator; wcześniej możesz edytować poszczególne urządzenia i sieć. Q po SSH zamyka TUI i wraca do powłoki. Na lokalnej konsoli zamknięty panel uruchamia się ponownie po 2 s. Zamknięcie panelu nie zatrzymuje odbiornika.

## Menu

| Opcja | Działanie |
|---|---|
| 1 | Stan Dell/Casio i usługi |
| 2, 3 | Port USB, nazwa, włączenie urządzenia, baud, bity danych, parzystość, bity stopu, timeouty, odpowiedzi Dell |
| 4 | Adres/port CueServer, nazwa Casio, komendy ON/OFF, odstęp komend |
| 5 | IP nasłuchu, port TLS/TCP, dozwolone IP/CIDR, odnowienie tokenu |
| 6 | Zachowanie po uruchomieniu, poziom logów, czas ponownego podłączania USB |
| 7 | nmtui: Ethernet, Wi-Fi, DHCP, stały IP, brama i DNS |
| 8 | raspi-config: ustawienia systemu, SSH, nazwa hosta i ustawienia regionalne |
| 9 | Ostatnie 150 wpisów dziennika |
| 10 | Ręczny ON/OFF/status dla dell1, dell2, casio lub all |
| 11 | Adresy RPi, port, token i odcisk certyfikatu do wpisania na PC |
| 12 | Import/eksport konfiguracji JSON |
| 13 | Restart odbiornika |
| 14 | Ta instrukcja |

Zmiany aplikacji są sprawdzane przed zapisem, a zapis jest atomowy. Ostatnie 10 konfiguracji pozostaje w kopiach `/etc/guido-projectors/config-*.bak.json`. Import kopii wykonaj przez opcję 12. Eksport zawiera token; plik ma uprawnienia 0600. Eksport nie zawiera prywatnego klucza TLS, a odcisk certyfikatu przy przeniesieniu na inne RPi będzie inny.

Zmiana IP aktywnego połączenia może zerwać SSH; konfiguruj ją na lokalnym monitorze.

## Start i awarie

- `preserve`: brak automatycznej komendy zasilania; konfiguracja domyślna.
- `on` / `off`: jedna próba po 10 sekundach od uruchomienia odbiornika na nowym starcie systemu. Restart samej usługi nie powtarza tej próby. Błąd nie powoduje automatycznego ponawiania zasilania. Sprawdź logi i wykonaj test ręczny.
- Po odpięciu konwertera port jest zamykany i ponownie otwierany, domyślnie co 5 sekund. Nie jest przy tym wysyłany ON/OFF.
- Delle są obsługiwane równolegle, z blokadą pojedynczego urządzenia. Kolejna operacja dla zajętego urządzenia otrzyma `busy`; nie będzie odkładana do późniejszego wykonania.
- Domyślnie odbiornik odczytuje odpowiedzi Dell i stan zasilania. Włączenie jest oddzielone od następnej komendy minimum 5 sekundami. Oczekiwanie na zakończenie rozgrzewania/chłodzenia jest ograniczone timeoutem.
- Wyłączenie weryfikacji odpowiedzi Dell jest opcją serwisową dla instalacji bez sprawnego RX. Wtedy aplikacja raportuje tylko wysłanie; nie potwierdza stanu.
- CueServer otrzymuje datagram UDP. Bez dodatkowego programu sprzężenia zwrotnego nie da się ustalić wykonania ani stanu Casio. Ustawiony odstęp komend jest ograniczeniem lokalnym odbiornika, a nie pomiarem gotowości projektora.

## Polecenia

```text
sudo guido-config status
sudo guido-config on --target dell1
sudo guido-config off --target dell2
sudo guido-config status --target all
sudo guido-config check
sudo guido-config config-text
sudo journalctl -u guido-projectors.service -f
sudo systemctl restart guido-projectors.service
passwd
```

`on` / `off` wykonują rzeczywiste polecenia; używaj po sprawdzeniu przypisania kabli. `check` sprawdza konfigurację, nie urządzenia fizyczne.

Odbiornik pracuje jako osobny użytkownik systemowy z dostępem do grupy `dialout`. Konfiguracja i klucz TLS są czytelne dla administratora i tej grupy. Lokalny socket sterowania jest chroniony uprawnieniami. TUI pracuje jako root: lokalnie bez logowania zgodnie z wybranym trybem instalacji. Po SSH konto z grupy `sudo` otwiera TUI bez drugiego pytania o hasło; wyjątek sudo dotyczy wyłącznie `/usr/local/bin/guido-config` bez argumentów. Pozostałe polecenia administracyjne zachowują standardowe reguły sudo. Dziennik ma limit 64 MB i retencję 14 dni.

Usługa panelu: `guido-console.service`; odbiornik: `guido-projectors.service`. Zwykły ekran logowania pozostaje na dodatkowych konsolach, np. Ctrl+Alt+F2. Przy pracy administracyjnej lokalnie można zatrzymać panel przez SSH: `sudo systemctl stop guido-console.service`, a następnie uruchomić go ponownie. Na tty1 standardowy getty jest maskowany, aby dwa procesy nie używały jednocześnie klawiatury i ekranu.

Interaktywne SSH otwiera TUI, a polecenia bez terminala i SCP/SFTP nie otwierają panelu. Współbieżne TUI wykrywają zmianę konfiguracji z innej sesji i wymagają ponownego otwarcia formularza, aby nie nadpisać nieaktualną kopią ustawień.

Konto i hasło ustawia pierwszy lokalny kreator. Hasło później zmienisz przez `passwd`; ustawienia dostępu SSH przez menu systemowe. Token aplikacji zmienisz w opcji 5; aktualizację trzeba wykonać także na PC. Nie udostępniaj tokenu i pliku eksportu osobom nieuprawnionym.
