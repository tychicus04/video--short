"""A run folder (~/notebooklm-videos/<slug>/): its files, its config and which steps are done."""
import json
import os
import threading
import tomllib
from pathlib import Path
from typing import Any

CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
_STATE_LOCK = threading.Lock()  # `vshort auto` reads the voice in a thread while the pictures are made


def config() -> dict[str, Any]:
    return tomllib.loads(CONFIG.read_text())


class Run:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._state_file = self.path / "state.json"
        self.state: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        return json.loads(self._state_file.read_text()) if self._state_file.exists() else {}

    def _save(self) -> None:
        # whole file or nothing: a reader never sees it half written
        tmp = self._state_file.with_name(f".state.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(self.state, indent=1))
        tmp.replace(self._state_file)

    def done(self, step: str) -> bool:
        self.state = self._load()  # another Run (each vshort command opens its own) may have marked it since
        return self.state.get(step) == "done"

    def mark(self, step: str) -> None:
        with _STATE_LOCK:  # re-read first: another process or thread may have marked a step since we started
            self.state = self._load()
            self.state[step] = "done"
            self._save()

    def unmark(self, *steps: str) -> None:
        with _STATE_LOCK:
            self.state = self._load()
            for s in steps:
                self.state.pop(s, None)
            self._save()

    def file(self, name: str) -> Path:
        return self.path / name

    def read(self, name: str) -> Any:
        return json.loads(self.file(name).read_text(encoding="utf-8"))

    def write(self, name: str, data: Any) -> None:
        self.file(name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
