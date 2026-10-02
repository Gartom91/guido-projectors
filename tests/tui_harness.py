"""Real curses frontend with isolated filesystem and simulated devices for tests."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rpi"))
from guido_projectors import tui
from guido_projectors.config import defaults, load, save

configuration = Path(sys.argv[1])
report = Path(sys.argv[2])
wizard = len(sys.argv) > 3 and sys.argv[3] == "wizard"
config = defaults()
if not wizard:
    config["dell"][0].update(enabled=True, device="/dev/serial/by-id/DELL-TEST")
    config["casio"].update(enabled=True, host="127.0.0.1")
    save(config, configuration, ownership=False)
commands, actions = [], []
tui.CONFIG_PATH = configuration
tui.load = lambda: load(configuration)
tui.save = lambda value: save(value, configuration, ownership=False)
tui.cli.require_root = lambda: None
tui.cli.ensure_certificate = lambda: None


def request(action, target="all", **kwargs):
    actions.append(action)
    return {"v": 1, "ok": True, "results": {
        "dell1": {"ok": True, "status": "verified", "state": "standby"},
        "casio": {"ok": True, "status": "unavailable", "state": "unknown"},
    }}


tui.cli.local_request = request


def command(self, *args):
    commands.append(args)
    return "127.0.0.1\n" if args[0] == "hostname" else ""


tui.TUI.command = command
result = tui.open_tui(wizard=wizard)
temporary = report.with_suffix(".tmp")
temporary.write_text(json.dumps({"config": result, "actions": actions, "commands": commands}, ensure_ascii=False))
temporary.replace(report)
