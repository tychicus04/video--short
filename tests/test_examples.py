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


def test_agent_instructions_quote_the_limits_the_code_checks():
    # a limit written twice drifts: MAX_SEEN was 4 in motion.py while the reviewer counted to 7 (research §4)
    from vshort import kit, render

    agents = EX.parent.parent / "claude" / "agents"
    motion_md, reviewer_md = ((agents / f"{a}.md").read_text(encoding="utf-8") for a in ("vs-motion", "vs-reviewer"))
    assert f"Tối đa **{motion.MAX_SEEN} thứ**" in motion_md and f"tối đa {motion.MAX_SEEN} thứ" in reviewer_md
    assert f"tối đa {kit.MAX_LABEL} ký tự" in motion_md
    assert f"chữ cỡ {kit.LABEL_EM} (nhỏ nhất {kit.MIN_LABEL_EM}" in motion_md
    assert f"tâm y≈{render.SUB_Y}" in reviewer_md
