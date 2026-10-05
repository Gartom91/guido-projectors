FROM debian:trixie-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a
RUN apt-get update && apt-get install -y --no-install-recommends \
    network-manager dnsmasq-base dbus iproute2 iputils-ping python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY verify.py /test/verify.py
COPY guido-ethernet-dhcp.nmconnection /test/profiles/
COPY guido-ethernet-fallback.nmconnection /test/profiles/
CMD ["python3", "/test/verify.py"]
