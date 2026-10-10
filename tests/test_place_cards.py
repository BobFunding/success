from autoedit.illustrate import Insert, place_cards


def _ins(placement="side", start=0.0, end=5.0):
    return Insert(start, end, "개념", "그림", "", placement)


def _overlap(ins, box):
    x1, y1, x2, y2 = box
    return max(0, min(ins.x + ins.size, x2) - max(ins.x, x1)) * max(0, min(ins.y + ins.size, y2) - max(ins.y, y1))


def test_default_right_middle_when_screen_is_empty():
    ins = _ins()
    place_cards([ins], [], 1280, 720)
    assert ins.x > 640 and ins.size > 0
    assert ins.y == (720 - ins.size) // 2


def test_avoids_text_on_the_right():
    ins = _ins()
    box = (900, 200, 1270, 500)  # 오른쪽 가운데에 화면 글자
    place_cards([ins], [(1.0, box)], 1280, 720)
    assert _overlap(ins, box) == 0


def test_ignores_text_outside_insert_time():
    ins = _ins(start=10, end=15)
    place_cards([ins], [(1.0, (900, 200, 1270, 500))], 1280, 720)
    assert ins.x > 640 and ins.y == (720 - ins.size) // 2


def test_shrinks_when_no_free_spot_at_full_size():
    # 위아래에 가로로 긴 글자(제목, 자막)가 있어서 큰 카드는 어디에 둬도 걸치고, 작은 카드는 피할 수 있는 경우
    boxes = [(0, 0, 1280, 100), (0, 600, 1280, 720)]
    ins = _ins()
    place_cards([ins], [(1.0, b) for b in boxes], 1280, 720)
    assert all(_overlap(ins, b) == 0 for b in boxes)
    big = _ins()
    place_cards([big], [], 1280, 720)
    assert ins.size < big.size


def test_full_placement_untouched():
    ins = _ins("full")
    place_cards([ins], [], 1280, 720)
    assert (ins.x, ins.y, ins.size) == (0, 0, 0)
