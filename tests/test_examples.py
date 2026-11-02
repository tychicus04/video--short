import json
from pathlib import Path

import pytest

from vshort import motion

EX = Path(__file__).resolve().parent.parent / "examples" / "motion"


@pytest.mark.parametrize("name", ["coruna", "goi-tin"])
def test_example_binds_and_draws(name, tmp_path):
    doc, bind, script = (json.loads((EX / f"{name}{x}.json").read_text()) for x in ("", ".bind", ".script"))
    assert motion.bind_problems(doc, bind, script, tmp_path) == []
    img = motion.bind_sheet(doc, bind, script, tmp_path)
    assert img.width > len(doc["beats"]) * motion.SHEET_W
