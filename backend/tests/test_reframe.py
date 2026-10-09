"""9:16 crop math: face/subject center, clamp, and a still center fallback."""

import numpy as np

from app.reframe import crop_size, crop_x_expression, lock_to_biggest_face, motion_center


def test_landscape_frame_crops_to_nine_sixteen():
    cw, ch = crop_size(1920, 1080)
    assert ch == 1080
    assert cw % 2 == 0
    assert abs((cw / ch) - (9 / 16)) < 0.02
    assert cw < 1920


def test_portrait_frame_already_nine_sixteen_is_unchanged():
    assert crop_size(1080, 1920) == (1080, 1920)


def test_tall_frame_crops_height_instead_of_width():
    cw, ch = crop_size(1080, 2400)
    assert cw == 1080
    assert ch % 2 == 0
    assert ch < 2400
    assert abs((cw / ch) - (9 / 16)) < 0.02


def test_crop_x_clamps_a_left_edge_subject_to_zero():
    assert crop_x_expression([(0.0, 100.0)], crop_w=600, frame_w=1920) == "0"


def test_crop_x_centers_a_steady_subject():
    assert crop_x_expression([(0.0, 1200.0), (2.0, 1200.0)], crop_w=600, frame_w=1920) == "900"


def test_crop_x_jumps_at_a_shot_cut_instead_of_panning():
    expr = crop_x_expression([(0.0, 400.0), (2.0, 1600.0)], crop_w=600, frame_w=1920)
    assert expr == "if(lt(t\\,2.000)\\,100\\,1300)"


def test_crop_x_ignores_tiny_moves_between_shots():
    expr = crop_x_expression([(0.0, 1200.0), (3.0, 1220.0)], crop_w=600, frame_w=1920)
    assert expr == "900"


def test_crop_x_uses_the_shot_already_on_screen_at_segment_start():
    expr = crop_x_expression([(-4.0, 400.0), (-1.0, 1600.0)], crop_w=600, frame_w=1920)
    assert expr == "1300"


def test_lock_to_biggest_face_ignores_the_smaller_person():
    samples = [
        (0.0, 400.0, 2000.0),
        (0.4, 420.0, 2100.0),
        (0.8, 1500.0, 8000.0),
        (1.2, 1510.0, 8200.0),
        (1.6, 390.0, 1900.0),
    ]
    assert lock_to_biggest_face(samples) == 1510.0


def test_lock_to_biggest_face_ignores_a_one_frame_false_positive():
    samples = [(index * 0.4, 900.0 + index, 6000.0) for index in range(10)]
    samples.append((2.0, 300.0, 20000.0))
    assert 900.0 <= lock_to_biggest_face(samples) <= 910.0


def test_lock_without_faces_returns_none():
    assert lock_to_biggest_face([]) is None


def test_missing_track_falls_back_to_center_crop():
    expr = crop_x_expression([], crop_w=600, frame_w=1920)
    assert expr == "(in_w-out_w)/2"


def test_motion_center_finds_a_bright_blob():
    prev = np.zeros((100, 200), np.uint8)
    gray = np.zeros((100, 200), np.uint8)
    gray[40:60, 150:170] = 255
    center = motion_center(prev, gray)
    assert center is not None
    assert center[0] > 140
    assert 40 < center[1] < 60
