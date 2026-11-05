import json
from pathlib import Path

import pytest

from vshort import motion

EX = Path(__file__).resolve().parent.parent / "examples" / "motion"


@pytest.mark.parametrize("name", ["coruna", "goi-tin"])
def test_example_binds_and_draws(name, tmp_path):
    doc, bind, script = (json.loads((EX / f"{name}{x}.json").read_text()) for x in ("", ".bind", ".script"))
    assert motion.bind_problems(doc, bind, script, tmp_path) == []
    assert motion.ui_problems(motion.bound(doc, bind)) == []  # the agents copy these: they keep clear of the platforms
    img = motion.bind_sheet(doc, bind, script, tmp_path)
    assert img.width > len(doc["beats"]) * motion.SHEET_W


def test_agent_instructions_quote_the_limits_the_code_checks():
    # a limit written twice drifts: MAX_SEEN was 4 in motion.py while the reviewer counted to 7 (research §4)
    from vshort import kit, render, textfit, visuals

    agents = EX.parent.parent / "claude" / "agents"
    motion_md, reviewer_md = ((agents / f"{a}.md").read_text(encoding="utf-8") for a in ("vs-motion", "vs-reviewer"))
    assert f"Tối đa **{motion.MAX_SEEN} thứ**" in motion_md and f"tối đa {motion.MAX_SEEN} thứ" in reviewer_md
    assert f"tối đa {kit.MAX_LABEL} ký tự" in motion_md
    assert f"chữ cỡ {kit.LABEL_EM} (nhỏ nhất {kit.MIN_LABEL_EM}" in motion_md
    assert f"đáy hộp y≈{render.SUB_BOTTOM}" in reviewer_md and f"chữ không quá x {textfit.UI_RIGHT}" in reviewer_md
    visuals_md = (agents / "vs-visuals.md").read_text(encoding="utf-8")
    assert f"vùng phụ đề y {visuals.SUBTITLE[1]}–{visuals.SUBTITLE[3]}" in visuals_md
    assert (f"y {visuals.REF_TOP}–{visuals.REF_BOTTOM}, và từ y {visuals.REF_RIGHT_FROM} trở xuống chỉ tới x {visuals.REF_RIGHT}"
            in visuals_md)
    assert (f"y {textfit.UI_TOP}–{kit.SAFE[3]}** (khung 720×1280), và **không vào góc\n  x > {textfit.UI_RIGHT} từ y "
            f"{textfit.UI_RIGHT_FROM} trở xuống**" in motion_md)
    assert visuals.ZOOM == render.ZOOM  # visuals cannot import render (render -> motion -> visuals)


def test_vs_nhip_quotes_the_limits_the_code_checks():
    from vshort import render, shots, textfit

    md = (EX.parent.parent / "claude" / "agents" / "vs-nhip.md").read_text(encoding="utf-8")
    vi = lambda x: str(x).replace(".", ",")  # noqa: E731  the agent reads Vietnamese numbers
    for want in (f"Tối đa {shots.MAX_POPS} `pop`", f"≤ {shots.MAX_POP_LEN} ký tự", f"Không quá {vi(shots.MAX_GAP)} giây",
                 f"tối đa {vi(shots.MAX_ZOOM_STILL)} lần", f"trước lời {vi(shots.LEAD)} s", f"({vi(shots.SNAP)} s)",
                 f"vẽ dần ~{vi(shots.DRAW)} s", f"y từ {textfit.UI_TOP} tới {shots.SUBTITLE[1]}, x từ {shots.MARGIN}",
                 f"x tối đa {textfit.UI_RIGHT}", f"từ y {textfit.UI_RIGHT_FROM} trở xuống", f"tới {render.W - shots.MARGIN})"):
        assert want in md, want


def test_captions_and_patches_stay_clear_of_what_the_platforms_draw():
    from vshort import render, textfit, visuals

    assert render.SUB_BOTTOM < textfit.UI_BOTTOM  # the description starts under the box
    assert render.W / 2 + textfit.MAX_TEXT_W / 2 <= textfit.UI_RIGHT  # the widest phrase ends left of the buttons
    one_line = render.LINE_H + 2 * render.PAD_Y
    assert visuals.SUBTITLE[1] < render.SUB_BOTTOM - one_line  # patched text is never under the caption box
    assert motion.kit.SAFE[3] <= render.SUB_BOTTOM - one_line  # nor is the drawn canvas
