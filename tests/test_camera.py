from vshort import camera, kit
from vshort.kit import FULL, SAFE


def test_full_view_is_identity():
    assert camera.view(SAFE) == FULL
    assert kit.screen(FULL, 123, 456) == (123, 456)


def test_small_box_zooms_to_max_and_centres():
    v = camera.view((200, 300, 300, 400))
    assert v == (250.0, 350.0, 2.0)
    assert kit.screen(v, 250, 350) == (360.0, 573.0)


def test_view_never_shows_past_the_canvas():
    assert camera.view((40, 96, 140, 196)) == (180.0, 286.5, 2.0)


def test_keys_glide_between_beats_and_pull_back():
    ks = camera.keys([(0, 5), (5, 10)], [(200, 300, 300, 400), None], lead=0.35)
    assert ks[0] == (-0.35, 250.0, 350.0, 2.0) and ks[-1] == (9.2, *FULL)
    assert camera.at(ks, 2.0)[:2] == (250.0, 350.0) and 2.0 <= camera.at(ks, 2.0)[2] <= 2.0 * (1 + camera.DRIFT)
    assert 1.0 < camera.at(ks, 5.4)[2] < 2.0
    assert camera.at(ks, 6.0)[:2] == FULL[:2] and 1.0 <= camera.at(ks, 6.0)[2] <= 1 + camera.DRIFT


def test_camera_drifts_while_a_beat_holds():
    ks = camera.keys([(0, 5), (5, 10)], [(200, 300, 300, 400), None], lead=0.35)
    assert camera.at(ks, 1.0)[2] < camera.at(ks, 4.9)[2] <= 2.0 * (1 + camera.DRIFT) + 1e-9
    assert camera.at(ks, 6.0)[2] < camera.at(ks, 7.9)[2]
    assert ks[-1] == (9.2, *FULL)
