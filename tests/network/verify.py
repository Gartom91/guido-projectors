"""Real NetworkManager/DHCP/ARP tests confined to an offline Docker network namespace."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def run(*args, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if check and result.returncode:
        raise RuntimeError(f"{args}: {result.stderr.strip()}")
    return result


def wait_for(predicate, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise AssertionError("Network state did not reach the expected condition")


def addresses():
    devices = json.loads(run("ip", "-j", "-4", "address", "show", "dev", "eth0").stdout)
    return [item["local"] for device in devices for item in device["addr_info"]]


def main():
    # Never run this test against a host NIC or a container connected to the LAN.
    if not Path("/.dockerenv").exists() or os.environ.get("GUIDO_NETWORK_TEST") != "isolated-container":
        raise RuntimeError("Use the documented offline Docker test")
    if {item["ifname"] for item in json.loads(run("ip", "-j", "link").stdout)} != {"lo"}:
        raise RuntimeError("Test container must start with --network none")
    profiles = Path("/etc/NetworkManager/system-connections")
    profiles.mkdir(parents=True, exist_ok=True)
    config = Path("/test/NetworkManager.conf")
    config.write_text("[main]\nplugins=keyfile\nno-auto-default=*\n[device-test]\nmatch-device=interface-name:eth0\nmanaged=1\nignore-carrier=false\n"
                      "[logging]\nlevel=DEBUG\n")
    run("ip", "netns", "add", "peer")
    run("ip", "link", "add", "eth0", "type", "veth", "peer", "name", "pc0")
    run("ip", "link", "set", "pc0", "netns", "peer")
    run("ip", "link", "set", "lo", "up")
    run("ip", "link", "set", "eth0", "up")
    run("ip", "netns", "exec", "peer", "ip", "link", "set", "lo", "up")
    run("ip", "netns", "exec", "peer", "ip", "link", "set", "pc0", "up")
    run("ip", "netns", "exec", "peer", "ip", "address", "add", "192.0.2.1/24", "dev", "pc0")
    Path("/run/dbus").mkdir(exist_ok=True)
    run("dbus-daemon", "--system", "--fork", "--nopidfile")
    daemon = dhcp = None
    logs = []
    report = {"ok": False, "networkmanager": run("NetworkManager", "--version").stdout.strip(), "cases": []}

    def stop_nm():
        nonlocal daemon
        if daemon is not None:
            daemon.terminate()
            daemon.wait(timeout=10)
            daemon = None
        run("ip", "-4", "address", "flush", "dev", "eth0")

    def start_nm(custom=False):
        nonlocal daemon
        stop_nm()
        for path in profiles.iterdir():
            if path.is_file():
                path.unlink()
        for path in Path("/test/profiles").glob("*.nmconnection"):
            destination = profiles / path.name
            shutil.copyfile(path, destination)
            destination.chmod(0o600)
        if custom:
            path = profiles / "custom.nmconnection"
            path.write_text("[connection]\nid=User Ethernet\nuuid=9677847e-70f1-41dd-a99f-9b3a2c847783\n"
                            "type=ethernet\ninterface-name=eth0\nautoconnect=true\n"
                            "[ethernet]\n[ipv4]\nmethod=manual\naddress1=192.0.2.50/24\n"
                            "[ipv6]\nmethod=disabled\n")
            path.chmod(0o600)
        # Each start simulates a fresh boot; discard test-only lease/backoff state.
        for path in Path("/var/lib/NetworkManager").glob("*"):
            if path.is_file():
                path.unlink()
        shutil.rmtree("/run/NetworkManager", ignore_errors=True)
        log = Path(f"/test/nm-{len(logs)}.log").open("w")
        logs.append(log)
        daemon = subprocess.Popen(["NetworkManager", "--debug", "--config", str(config)],
                                  stdout=log, stderr=subprocess.STDOUT)
        wait_for(lambda: run("nmcli", "general", "status", check=False).returncode == 0, 10)

    def start_dhcp():
        nonlocal dhcp
        dhcp = subprocess.Popen(["ip", "netns", "exec", "peer", "dnsmasq", "--keep-in-foreground",
                                 "--conf-file=/dev/null", "--port=0", "--interface=pc0", "--bind-interfaces",
                                 "--dhcp-range=192.0.2.10,192.0.2.20,255.255.255.0,1h",
                                 "--dhcp-leasefile=/test/leases", "--dhcp-authoritative", "--no-ping"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        if dhcp.poll() is not None:
            raise RuntimeError("DHCP fixture failed")

    def stop_dhcp():
        nonlocal dhcp
        if dhcp is not None:
            dhcp.terminate()
            dhcp.wait(timeout=10)
            dhcp = None

    def passed(name):
        report["cases"].append(name)
        print("PASS: " + name, flush=True)

    try:
        start_dhcp()
        start_nm()
        wait_for(lambda: any(ip.startswith("192.0.2.") for ip in addresses()))
        assert "192.168.0.1" not in addresses()
        passed("DHCP available: leased address, no fallback")

        stop_dhcp()
        stop_nm()
        run("ip", "netns", "exec", "peer", "ip", "link", "set", "pc0", "down")
        start_nm()
        time.sleep(2)
        assert not addresses(), f"No carrier: unexpected addresses {addresses()}"
        run("ip", "netns", "exec", "peer", "ip", "link", "set", "pc0", "up")
        start = time.monotonic()
        wait_for(lambda: addresses() == ["192.168.0.1"])
        assert time.monotonic() - start >= 25, "Fallback skipped the DHCP attempt"
        assert not run("ip", "-4", "route", "show", "default").stdout.strip()
        run("ip", "netns", "exec", "peer", "ip", "address", "add", "192.168.0.2/24", "dev", "pc0")
        run("ip", "netns", "exec", "peer", "ping", "-c", "1", "-W", "2", "192.168.0.1")
        passed("No DHCP after cable insertion: 192.168.0.1/24 reachable, no default gateway")

        start_dhcp()
        time.sleep(5)
        assert addresses() == ["192.168.0.1"], "New DHCP server unexpectedly interrupted fallback access"
        start_nm()
        wait_for(lambda: any(ip.startswith("192.0.2.") for ip in addresses()))
        assert "192.168.0.1" not in addresses()
        passed("DHCP restored on restart; active fallback remains stable until then")

        stop_dhcp()
        stop_nm()
        run("ip", "netns", "exec", "peer", "ip", "address", "add", "192.168.0.1/24", "dev", "pc0")
        start_nm()
        def conflict_detected():
            text = Path(logs[-1].name).read_text().lower()
            return "192.168.0.1" in text and any(word in text for word in ("conflict", "duplicate", "already in use"))
        wait_for(conflict_detected, 45)
        time.sleep(2)
        assert "192.168.0.1" not in addresses()
        assert "GUIDO Ethernet awaryjny" not in run("nmcli", "-t", "-f", "NAME", "connection", "show", "--active").stdout
        passed("Occupied fallback address rejected by ARP conflict detection")
        run("ip", "netns", "exec", "peer", "ip", "address", "del", "192.168.0.1/24", "dev", "pc0")

        start_nm(custom=True)
        wait_for(lambda: addresses() == ["192.0.2.50"], 10)
        time.sleep(2)
        assert addresses() == ["192.0.2.50"]
        passed("User static profile takes precedence over factory profiles")
        report["ok"] = True
    finally:
        stop_dhcp()
        stop_nm()
        for log in logs:
            log.close()
        Path("/test/result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
