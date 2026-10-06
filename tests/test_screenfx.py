import numpy as np

from autoedit.screenfx import FrameActivity, Focus, ScreenFxSettings, camera_path, plan_focus, speed_map

FPS = 30.0


def _acts(n, events=()):
    """n 프레임짜리 활동 목록. events: (시작 프레임, 끝 프레임, box, any_change만 있고 내용 변화 없음 여부)."""
    acts = [FrameActivity(i / FPS, 0.0, False, None) for i in range(n)]
    for a, b, box, cursor_only in events:
        for i in range(a, b):
            acts[i] = FrameActivity(i / FPS, 0.0 if cursor_only else 0.001, True, None if cursor_only else box)
    return acts


def test_auto_focus_on_persistent_local_change():
    # 3~5초 동안 입력창(가운데 위) 근처에서 글자가 계속 바뀜 → 그 자리로 줌
    acts = _acts(300, [(90, 150, (0.40, 0.44, 0.48, 0.48), False)])
    f = plan_focus(acts, [], 1920, 1080, ScreenFxSettings())
    assert len(f) == 1
    assert abs(f[0].cx - 0.44) < 0.01 and abs(f[0].cy - 0.46) < 0.01
    assert f[0].zoom > 1.5


def test_no_focus_for_cursor_only_or_brief_change():
    acts = _acts(300, [(30, 90, None, True),                        # 커서만 움직임
                       (200, 202, (0.1, 0.1, 0.12, 0.12), False)])  # 한두 프레임 깜빡임
    assert plan_focus(acts, [], 1920, 1080, ScreenFxSettings()) == []


def test_wide_change_is_not_zoomed():
    # 차트처럼 화면 폭 대부분이 바뀌면 전체를 보여줘야 한다
    acts = _acts(300, [(60, 120, (0.15, 0.45, 0.97, 0.57), False)])
    assert plan_focus(acts, [], 1920, 1080, ScreenFxSettings()) == []


def test_click_focus_uses_click_position():
    acts = _acts(300)
    f = plan_focus(acts, [{"t": 2.0, "x": 1800, "y": 60}], 1920, 1080, ScreenFxSettings())
    assert len(f) == 1 and f[0].source == "click"
    assert abs(f[0].cx - 0.9375) < 1e-6 and f[0].start < 2.0 < f[0].end


def test_camera_is_smooth_and_stays_inside_frame():
    s = ScreenFxSettings()
    path = camera_path(300, FPS, [Focus(1.0, 6.0, 0.98, 0.02, 2.0, "click")], s)
    assert np.allclose(path[0], [0.5, 0.5, 1.0])
    # 한 프레임에 확 튀지 않음
    assert np.abs(np.diff(path, axis=0)).max() < 0.05
    # 확대된 화면이 원본 밖으로 나가지 않음
    half = 0.5 / path[:, 2]
    assert (path[:, 0] >= half - 1e-9).all() and (path[:, 0] <= 1 - half + 1e-9).all()
    # 줌 구간 안에서는 목표에 가까이 다가감
    assert path[150, 2] > 1.8


def test_speed_map_skips_idle_frames_only():
    s = ScreenFxSettings(speedup=4.0, idle_min=1.0, idle_margin=0.2)
    acts = _acts(300, [(0, 60, None, True), (240, 300, None, True)])  # 2~8초는 완전히 정지
    frames = speed_map(acts, [], s)
    assert frames[:60] == list(range(60))          # 움직이는 구간은 그대로
    assert frames[-60:] == list(range(240, 300))
    assert len(frames) < 300 - 120                 # 정지 구간은 대부분 건너뜀
    assert frames == sorted(frames)


def test_speedup_off():
    acts = _acts(100)
    assert speed_map(acts, [], ScreenFxSettings(speedup=1.0)) == list(range(100))


def test_click_focus_includes_what_changed_after_click():
    # 슬라이드 화살표(오른쪽 끝)를 누르면 가운데 슬라이드가 바뀜 → 화살표가 아니라 슬라이드 쪽을 보여줘야 한다
    acts = _acts(300, [(62, 80, (0.30, 0.35, 0.68, 0.60), False)])
    f = plan_focus(acts, [{"t": 2.0, "x": 1375, "y": 573}], 1920, 1080, ScreenFxSettings())
    assert len(f) == 1
    assert 0.45 < f[0].cx < 0.55          # 화살표(0.72)보다 슬라이드 쪽
    assert 1.2 <= f[0].zoom <= ScreenFxSettings().zoom
