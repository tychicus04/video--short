from vshort.media import frame_at, iter_frames, probe


def test_probe(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 2, "#F3EFE6")], captions=[])
    p = probe(v)
    assert (p.width, p.height) == (720, 1280) and p.fps == 30 and abs(p.duration - 2) < 0.05


def test_iter_frames_crop_and_times(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000"), (1, 2, "#FFFFFF")], captions=[])
    frames = list(iter_frames(v, crop=(10, 10, 0, 0)))
    assert len(frames) == 60 and frames[0][1].shape == (10, 10)
    assert frames[0][1].mean() < 20 and frames[45][1].mean() > 235 and abs(frames[45][0] - 1.5) < 1e-6


def test_frame_at_exact(make_video, tmp_path):
    v = make_video(tmp_path, scenes=[(0, 1, "#000000"), (1, 2, "#FFFFFF")], captions=[])
    assert frame_at(v, 1.02, gray=True).mean() > 235


def test_iter_frames_early_stop_is_quiet(make_video, tmp_path, capfd):
    v = make_video(tmp_path, scenes=[(0, 2, "#000000")], captions=[])
    for _ in iter_frames(v):
        break
    assert "Broken pipe" not in capfd.readouterr().err
