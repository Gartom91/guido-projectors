# Protokoły integracji

## Oryginalna aplikacja PC

Zbadany plik: dostarczony `ShadokProjektory.exe`, wersja 1.0.0.0, 41 984 bajty. SHA256: `8a917af0a640d1203f823c38068b6b5590309873425005367b15e76e8a622509`.

Analiza statyczna .NET ustaliła:

| Funkcja | Odbiornik i transport | Dane |
|---|---|---|
| WDARCIE WODY WŁ, Dell | Dell 1 i Dell 2, TCP 41794 | `05 00 06 00 00 03 00 04 00` |
| WDARCIE WODY WYŁ, Dell | Dell 1 i Dell 2, TCP 41794 | `05 00 06 00 00 03 00 05 00` |
| WDARCIE WODY WŁ, Casio | CueServer projektora, UDP 52737 | `"(PWR1)"~4;"Projektor ON"~3` |
| WDARCIE WODY WYŁ, Casio | CueServer projektora, UDP 52737 | `"(PWR0)"~4` |
| POŻAR WŁ / WYŁ | Sterownik POŻAR, UDP 52737 | `Output 1 On; Output 2 On; Output 3 On;` / analogicznie `Off` |
| Zasilanie, pierwsze kliknięcie | Odtwarzacz i CueServer zasilania, UDP 52737 | `reconnect`, następnie `Output 8 On;` |
| Zasilanie, drugie kliknięcie | CueServer zasilania, UDP 52737 | `Output 8 Off;` |

Adresy instalacji są konfigurowane przez użytkownika i nie są publikowane. EXE otwiera oba połączenia TCP przed wysyłaniem UDP i nie czyta odpowiedzi. Pierwszy błąd połączenia może przerwać całą operację. Oryginalnego EXE nie zmodyfikowano na dysku użytkownika.

Nowa aplikacja PC wysyła jedno żądanie WDARCIE WODY do RPi. POŻAR, Output 8 i reconnect zachowują komendy i kolejność z oryginału, z konfigurowalnymi adresami. Nazwa przycisku Zasilanie oznacza następną operację: najpierw wyłącz, potem włącz. Odpowiada to sekwencji oryginału, nie odczytowi stanu zasilania.

## Nowy kanał PC–RPi

TLS 1.2/1.3 na konfigurowalnym porcie TCP, domyślnie 41794. Klient przypina SHA256 certyfikatu i sprawdza termin ważności. Żądanie jest obiektem JSON UTF-8 z końcowym LF, maksymalnie 2048 bajtów. Jedno żądanie na połączenie. Wymagany token; opcjonalnie filtr klientów IP/CIDR. Socket lokalny jest dostępny administratorowi bez tokenu.

```json
{"v":1,"token":"<token-z-menu-RPi>","action":"on","target":"all"}
```

Akcje: `on`, `off`, `status`. Cele: `all`, `dell1`, `dell2`, `casio`. `all` obejmuje urządzenia włączone w konfiguracji. Odpowiedź zawiera `v`, `ok`, `results`; błąd protokołu zawiera `error`. Wyniki są oddzielne dla każdego urządzenia.

Statusy: `verified` = zmierzony stan; `already_set` = stan już ustawiony; `acknowledged` = komenda przyjęta, stan końcowy jeszcze niepotwierdzony; `sent_unconfirmed` = wysłano; `unavailable` = brak odczytu; `busy` = inne polecenie w toku; `disabled` = urządzenie wyłączone w konfiguracji; `error` = błąd.

## Dell S518WL

19200 bps, 8N1, bez kontroli przepływu. Pakiety binarne, młodszy bajt pola pierwszy:

| Funkcja | Pełny pakiet HEX |
|---|---|
| ON | `BE EF 10 05 00 C6 FF 11 11 01 00 01` |
| OFF | `BE EF 10 05 00 0C 3E 11 11 01 00 18` |
| System Status | `BE EF 10 05 00 46 7E 11 11 01 00 FF` |

ACK: `00`; `01` oznacza niedostępną komendę, `02` błąd komendy/CRC. Stan: `00 FF xx`, gdzie `01` czuwanie, `02` rozgrzewanie, `03` włączony, `04` chłodzenie, `05` oszczędzanie energii. Sterownik wymusza 5 s po własnej komendzie ON i czeka na odpowiedź przed następną komendą. Dokumentacja wskazuje skrzyżowanie pinów 2 i 3 kabla RS232 oraz masę na pinie 5. [Dell RS232 Protocol Document](https://dl.dell.com/manuals/all-products/esuprt_display_projector/esuprt_projector/dell-s518wl-projector_users-guide2_en-us.pdf).

## Casio XJ-A252 przez CueServer 1

Casio używa ASCII `(PWR1)` / `(PWR0)`, 19200 bps, 8N1. CueScript `"(PWR1)"~4` przekazuje te znaki na RS232; domyślny port odbioru CueScript to UDP 52737. CR/LF nie są dodawane przez RPi. Ustawienie dopisywania CR/LF należy sprawdzić osobno na CueServer. Wersja instrukcji CueServer dotyczy oprogramowania 4.1; firmware urządzenia trzeba sprawdzić przy instalacji. [Casio](https://support.casio.jp/pdf/007/A257_M256_UsersGuide_JA.pdf), [CueServer 1](https://downloads.interactive-online.com/CueServer%201/Documents/D0420%20CueServer%20Users%20Manual.pdf).
