"""Bounded JSON-line TCP API and root-only local control socket."""

import asyncio
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import signal
import ssl

from .config import CERT_PATH, KEY_PATH, SOCKET_PATH, STATE_PATH
from .controller import Controller

LOG = logging.getLogger(__name__)
MAX_LINE = 2048
MAX_CLIENTS = 4


class Server:
    def __init__(self, config, controller):
        self.config = config
        self.controller = controller
        self.clients = 0

    async def client(self, reader, writer, local=False):
        counted = False
        try:
            if self.clients >= MAX_CLIENTS:
                raise ValueError("Serwer zajety")
            self.clients += 1
            counted = True
            if not local:
                peer = ipaddress.ip_address(writer.get_extra_info("peername")[0])
                allowed = self.config["server"]["allowed_clients"]
                if allowed and not any(peer in ipaddress.ip_network(cidr, strict=False) for cidr in allowed):
                    raise ValueError("Adres klienta niedozwolony")
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            if not line.endswith(b"\n") or len(line) > MAX_LINE:
                raise ValueError("Wymagany JSON zakonczony LF, maksymalnie 2048 bajtow")
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("Wymagany obiekt JSON")
            if not local:
                token = request.get("token")
                if not isinstance(token, str) or not hmac.compare_digest(token.encode("utf-8"), self.config["server"]["token"].encode("ascii")):
                    raise ValueError("Nieprawidlowy token")
            reply = await asyncio.to_thread(self.controller.dispatch, request)
        except (ValueError, UnicodeDecodeError, asyncio.TimeoutError) as error:
            reply = {"v": 1, "ok": False, "error": str(error) or "Timeout pakietu"}
        except (ConnectionError, OSError):
            writer.close()
            return
        except Exception:
            LOG.exception("Blad obslugi klienta")
            reply = {"v": 1, "ok": False, "error": "Blad serwera; sprawdz dziennik"}
        finally:
            if counted:
                self.clients -= 1
        try:
            writer.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            await writer.drain()
        except (OSError, ConnectionError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ConnectionError):
                pass


async def serve(config, socket_path=SOCKET_PATH, state_path=STATE_PATH,
                cert_path=CERT_PATH, key_path=KEY_PATH):
    controller = Controller(config, state_path)
    controller.start()
    api = Server(config, controller)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    path = Path(socket_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    if path.exists():
        path.unlink()
    startup = None
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert_path, key_path)
        tcp = await asyncio.start_server(api.client, config["server"]["host"], config["server"]["port"], limit=MAX_LINE,
                                        ssl=context, ssl_handshake_timeout=5)
        unix = await asyncio.start_unix_server(lambda r, w: api.client(r, w, local=True), path=str(path), limit=MAX_LINE)
        os.chmod(path, 0o600)
        async with tcp, unix:
            LOG.info("Odbiornik TCP %s:%s", config["server"]["host"], config["server"]["port"])
            startup = asyncio.create_task(asyncio.to_thread(controller.startup))
            await stopped.wait()
            controller.stop.set()
        await startup
    finally:
        controller.stop.set()
        if startup is not None and not startup.done():
            await startup
        await asyncio.to_thread(controller.close)
        path.unlink(missing_ok=True)
