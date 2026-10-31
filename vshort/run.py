"""A run folder (~/notebooklm-videos/<slug>/): its files, its config and which steps are done."""
import json
import re
import tomllib
from pathlib import Path
from typing import Any

CONFIG = Path(__file__).resolve().parent.parent / "config.toml"


def config() -> dict[str, Any]:
    return tomllib.loads(CONFIG.read_text())


def set_config(key: str, value: float | str) -> None:
    """Rewrite one `key = value` line of config.toml in place."""
    text = CONFIG.read_text()
    line = f"{key} = {json.dumps(value)}"
    text, n = re.subn(rf"^{re.escape(key)} = .*$", line, text, flags=re.M)
    CONFIG.write_text(text if n else text.rstrip("\n") + f"\n{line}\n")


class Run:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._state_file = self.path / "state.json"
        self.state: dict[str, str] = json.loads(self._state_file.read_text()) if self._state_file.exists() else {}

    def done(self, step: str) -> bool:
        return self.state.get(step) == "done"

    def mark(self, step: str) -> None:
        self.state[step] = "done"
        self._state_file.write_text(json.dumps(self.state, indent=1))

    def file(self, name: str) -> Path:
        return self.path / name

    def read(self, name: str) -> Any:
        return json.loads(self.file(name).read_text(encoding="utf-8"))

    def write(self, name: str, data: Any) -> None:
        self.file(name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
