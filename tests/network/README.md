# Test adresu awaryjnego na rzeczywistym NetworkManagerze

Test uruchamia NetworkManager 1.52.1, serwer DHCP i wirtualne Ethernety w odizolowanym kontenerze oraz osobnej przestrzeni sieciowej klienta. Używa plików profili kopiowanych z `image/files`. Wbudowany NetworkManager obrazu RPi ma wersję 1.52.1-1+rpt4; test kontenerowy używa wydania Debian 1.52.1-1.

Sprawdza DHCP, brak DHCP po podłączeniu kabla, osiągalność `192.168.0.1`, brak bramy domyślnej, powrót do DHCP po symulowanym ponownym starcie, konflikt ARP oraz pierwszeństwo własnego profilu statycznego. Uruchomienie skryptu poza kontenerem lub z interfejsem podłączonym do innej sieci jest odrzucane.

Na Windows z Docker Desktop, w katalogu repozytorium:

```powershell
New-Item -ItemType Directory -Force tmp/network-build
Copy-Item tests/network/verify.py,image/files/guido-ethernet-dhcp.nmconnection,image/files/guido-ethernet-fallback.nmconnection tmp/network-build
docker build --tag guido-network-test:1.3.0 --file tests/network/Dockerfile tmp/network-build
docker run --name guido-network-test --network none --cap-add NET_ADMIN --cap-add SYS_ADMIN --security-opt seccomp=unconfined --env GUIDO_NETWORK_TEST=isolated-container guido-network-test:1.3.0
docker cp guido-network-test:/test/result.json tmp/network-result.json
docker rm guido-network-test
```

`NET_ADMIN`, `SYS_ADMIN` i wyłączenie filtra seccomp są potrzebne tylko w kontenerze testowym do utworzenia interfejsów i przestrzeni sieciowych. Kontener startuje bez połączenia z siecią hosta i nie montuje katalogów hosta. Kontekst budowania zawiera tylko trzy jawnie skopiowane pliki; nie przesyła prywatnych kopii ani binariów projektu do Dockera. Test nie uruchamia projektorów, aplikacji sterującej ani SSH.

W produkcyjnym obrazie funkcja korzysta z istniejącego NetworkManagera, bez nowego demona i dodatkowych pakietów. Wymagany pozostaje test rozruchu oraz Ethernetu na fizycznym RPi.
