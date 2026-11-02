"""A run folder (~/notebooklm-videos/<slug>/): its files, its config and which steps are done."""
import json
import tomllib
from pathlib import Path
from typing import Any

CONFIG = Path(__file__).resolve().parent.parent / "config.toml"


def config() -> dict[str, Any]:
    return tomllib.loads(CONFIG.read_text())


class Run:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._state_file = self.path / "state.json"
        self.state: dict[str, str] = json.loads(self._state_file.read_text()) if self._state_file.exists() else {}

    def done(self, step: str) -> bool:
        return self.state.get(step) == "done"

    def mark(self, step: str) -> None:
        # re-read first: another process (tts | plates -> stills run in parallel) may have marked a step since we started
        self.state = json.loads(self._state_file.read_text()) if self._state_file.exists() else {}
        self.state[step] = "done"
        self._state_file.write_text(json.dumps(self.state, indent=1))

    def unmark(self, *steps: str) -> None:
        self.state = json.loads(self._state_file.read_text()) if self._state_file.exists() else {}
        for s in steps:
            self.state.pop(s, None)
        self._state_file.write_text(json.dumps(self.state, indent=1))

    def file(self, name: str) -> Path:
        return self.path / name

    def read(self, name: str) -> Any:
        return json.loads(self.file(name).read_text(encoding="utf-8"))

    def write(self, name: str, data: Any) -> None:
        self.file(name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
