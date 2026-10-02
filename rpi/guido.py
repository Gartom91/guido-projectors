#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import sys

from guido_projectors.cli import local_request, menu as text_menu, require_root
from guido_projectors.tui import menu
from guido_projectors.config import load
from guido_projectors.firstboot import firstboot
from guido_projectors.server import serve


def main():
    parser = argparse.ArgumentParser(description="Guido projector controller")
    parser.add_argument("command", nargs="?", default="config", choices=("config", "config-text", "serve", "firstboot", "check", "status", "on", "off"))
    parser.add_argument("--target", default="all", choices=("all", "dell1", "dell2", "casio"))
    args = parser.parse_args()
    try:
        if args.command == "serve":
            config = load()
            logging.basicConfig(level=config["log_level"], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
            asyncio.run(serve(config))
        elif args.command == "check":
            load()
            print("Konfiguracja poprawna")
        else:
            require_root()
            if args.command == "config":
                menu()
            elif args.command == "config-text":
                text_menu()
            elif args.command == "firstboot":
                firstboot()
            else:
                reply = local_request(args.command, args.target)
                print(json.dumps(reply, indent=2, ensure_ascii=False))
                return 0 if reply["ok"] else 1
    except (ValueError, OSError) as error:
        print(f"BLAD: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
