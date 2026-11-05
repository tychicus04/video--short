import json

from vshort import shapes


def test_shape_file_rules():
    ok = {"name": "bộ nhớ", "strokes": [[[10, 10], [90, 10], [90, 90]]]}
    assert shapes.problems(ok, "bo-nho") == []
    assert shapes.problems(ok, "Bộ Nhớ")  # slug sai
    assert shapes.problems({"name": "x", "strokes": []}, "x")  # 0 nét
    assert shapes.problems({"name": "x", "strokes": [[[0, 0]]] * 13}, "x")  # 13 nét, nét 1 điểm
    assert shapes.problems({"name": "x", "strokes": [[[0, 0], [101, 5]]]}, "x")  # ra ngoài ô
    assert shapes.problems({"strokes": [[[0, 0], [1, 5]]]}, "x")  # thiếu tên


def test_run_shape_cannot_change_library_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(shapes, "LIBRARY", tmp_path / "lib")
    (tmp_path / "lib").mkdir()
    (tmp_path / "run" / "shapes").mkdir(parents=True)
    a = {"name": "nhân", "strokes": [[[0, 0], [100, 100]]]}
    (tmp_path / "lib" / "nhan.json").write_text(json.dumps(a))
    (tmp_path / "run" / "shapes" / "nhan.json").write_text(json.dumps(a | {"strokes": [[[0, 100], [100, 0]]]}))
    assert any("đặt tên mới" in p for p in shapes.check_run(tmp_path / "run"))
    (tmp_path / "run" / "shapes" / "nhan.json").write_text(json.dumps(a))  # the same shape, copied back: fine
    assert shapes.check_run(tmp_path / "run") == []


def test_find_prefers_the_run_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(shapes, "LIBRARY", tmp_path / "lib")
    (tmp_path / "lib").mkdir()
    (tmp_path / "run" / "shapes").mkdir(parents=True)
    (tmp_path / "lib" / "a.json").write_text(json.dumps({"name": "lib", "strokes": [[[0, 0], [1, 1]]]}))
    assert shapes.find("a", tmp_path / "run")["name"] == "lib"
    (tmp_path / "run" / "shapes" / "a.json").write_text(json.dumps({"name": "run", "strokes": [[[0, 0], [1, 1]]]}))
    assert shapes.find("a", tmp_path / "run")["name"] == "run"
    assert shapes.find("b", tmp_path / "run") is None and shapes.find("../x", None) is None


def test_strokes_fit_box_keeping_aspect():
    pts = shapes.strokes_in_box({"name": "x", "strokes": [[[0, 0], [100, 50]]]}, [100, 100, 300, 400])
    xs, ys = zip(*pts[0])
    assert min(xs) == 100 and max(xs) == 300 and max(ys) - min(ys) == 100  # rộng 200, cao 100, căn giữa dọc
    assert min(ys) == 200


def test_sheet_shows_each_new_shape(tmp_path):
    (tmp_path / "shapes").mkdir()
    for s in ("a", "b"):
        (tmp_path / "shapes" / f"{s}.json").write_text(json.dumps({"name": s, "strokes": [[[0, 0], [100, 100]]]}))
    img = shapes.sheet(tmp_path)
    assert img.width >= 2 * 240


def test_sheet_names_fit_their_cell(tmp_path):
    (tmp_path / "shapes").mkdir()
    (tmp_path / "shapes" / "du-lieu-khoa.json").write_text(
        json.dumps({"name": "dữ liệu và khóa", "strokes": [[[0, 0], [100, 100]]]}))
    import numpy as np
    a = np.asarray(shapes.sheet(tmp_path).convert("L"))
    under = a[shapes.CELL:, :]
    cols = np.where((under < 100).any(axis=0))[0]
    assert cols.min() > 4 and cols.max() < shapes.CELL - 4


def test_library_sheet_has_the_library_shapes_and_the_run_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(shapes, "LIBRARY", tmp_path / "lib")
    (tmp_path / "lib").mkdir()
    (tmp_path / "run" / "shapes").mkdir(parents=True)
    for slug in ("a", "b", "c"):
        (tmp_path / "lib" / f"{slug}.json").write_text(json.dumps({"name": f"lib {slug}", "strokes": [[[0, 0], [100, 100]]]}))
    (tmp_path / "run" / "shapes" / "b.json").write_text(json.dumps({"name": "run b", "strokes": [[[0, 100], [100, 0]]]}))
    (tmp_path / "run" / "shapes" / "z.json").write_text(json.dumps({"name": "run z", "strokes": [[[0, 0], [100, 100]]]}))
    seen = []
    real = shapes.strokes_in_box
    monkeypatch.setattr(shapes, "strokes_in_box", lambda doc, box: seen.append(doc["name"]) or real(doc, box))
    assert shapes.sheet(tmp_path / "run").width == 2 * 244  # without the flag: the run's own, as before
    assert seen == ["run b", "run z"]
    seen.clear()
    img = shapes.sheet(tmp_path / "run", library=True)
    assert seen == ["lib a", "run b", "lib c", "run z"]  # a name once, the run's copy over the library's
    assert img.width == 4 * 244
    monkeypatch.setattr(shapes, "LIBRARY", tmp_path / "missing")  # no library folder: the run's shapes alone
    assert shapes.sheet(tmp_path / "run", library=True).width == 2 * 244
