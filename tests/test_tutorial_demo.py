"""튜토리얼 메이커 3단계: 문장 자동 생성(조사·말투), 한 번 해 보이기 기록 정리."""
from autoedit.tutorial import sentences as T
from autoedit.tutorial.demo_record import build_scenario, clean_events
from autoedit.tutorial.recorder import is_selector


def test_josa_follows_batchim():
    assert T.josa("아이디", "을/를") == "아이디를"
    assert T.josa("비밀번호", "을/를") == "비밀번호를"
    assert T.josa("이름", "을/를") == "이름을"
    assert T.josa("관심 분야", "은/는") == "관심 분야는"
    assert T.josa("생년월일", "은/는") == "생년월일은"
    assert T.josa("서울", "으로/로") == "서울로" and T.josa("부산", "으로/로") == "부산으로"
    assert T.josa("1", "을/를") == "1을" and T.josa("2", "을/를") == "2를"
    assert T.josa("ID", "을/를") == "ID를" and T.josa("URL", "을/를") == "URL을"
    assert T.josa("★", "을/를") == "★을(를)"            # 모르면 둘 다


def test_scene_lines_match_episode1_style():
    assert T.scene_line("클릭", "회원가입", first=True) == "먼저, 회원가입 버튼을 눌러 주세요."
    assert T.scene_line("입력", "아이디", button="중복확인") == "아이디를 적고, 중복확인을 눌러 주세요."
    assert T.scene_line("선택", "성별") == "성별은 목록에서 골라 주세요."
    assert T.scene_line("클릭", "등록", last=True) == "마지막으로, 등록 버튼을 누르면 끝이에요."
    assert T.scene_line("클릭", "등록 버튼") == "등록 버튼을 눌러 주세요."    # '버튼 버튼' 안 됨
    assert T.scene_line("클릭", "공지사항", kind="링크") == "공지사항을 눌러 주세요."
    assert T.scene_line("입력", "이름", tone="전문") == "이름을 입력합니다."


def test_intro_outro_and_title():
    intro, outro = T.intro_outro("관장님 회원가입 방법", 3, "태권 월드", "로그인")
    assert intro == ["안녕하세요, 태권 월드입니다.", "오늘은 관장님 회원가입 방법을, 세 단계로 알려 드릴게요."]
    assert outro == ["오늘 배운 세 단계, 기억하시죠?", "다음 영상에서는 로그인 방법을 알려 드릴게요. 태권 월드였습니다."]
    assert T.title("관장님 회원가입", 3) == "관장님 회원가입, [3단계]면 끝!"
    assert T.intro_outro("가입", 2, "")[1][1] == "고맙습니다."


def test_is_selector():
    assert not is_selector("로그인(관장)") and not is_selector("이메일 주소")
    assert is_selector("button:has-text('등록')") and is_selector("#name") and is_selector('text="관장님"')


def _ev(ev, t, url="http://s/join", **k):
    base = dict(ev=ev, t=t, url=url, tag="button", role="", type="", name="", text="", label="", placeholder="",
                aria="", sel=[], box={"x": 100, "y": 100, "w": 200, "h": 40}, combo=-1, option=-1, heading="회원 정보 입력",
                hit=True)
    base.update(k)
    return base


def test_clean_events_drops_mistakes_and_merges():
    evs = [
        _ev("click", 0, url="http://s/", tag="a", text="자료 검색", sel=["a:has-text('자료 검색')"]),       # 실수
        _ev("click", 1500, url="http://s/", tag="div", hit=False),                                       # 빈 곳
        _ev("click", 2000, url="http://s/", tag="a", text="회원가입", sel=["a:has-text('회원가입')"]),
        _ev("click", 2100, url="http://s/", tag="a", text="회원가입", sel=["a:has-text('회원가입')"]),      # 두 번 누름
        _ev("click", 3000, tag="input", type="text", sel=["#name"]),                                     # 칸 누르기
        _ev("input", 3100, tag="input", type="text", sel=["#name"], label="이름", value="홍"),
        _ev("input", 3300, tag="input", type="text", sel=["#name"], label="이름", value="홍길동"),
        _ev("input", 4000, tag="input", type="email", sel=["#email"], label="이메일", value="a@b.c",
            box={"x": 100, "y": 200, "w": 300, "h": 50}),
        _ev("click", 4500, text="중복 확인", sel=["#check"], box={"x": 420, "y": 205, "w": 90, "h": 40}),
        _ev("click", 5000, tag="label", forCheck=True, sel=["label"]),
        _ev("check", 5001, tag="input", type="checkbox", sel=["#agree"], label="약관에 동의합니다", checked=True),
        _ev("check", 5400, tag="input", type="checkbox", sel=["#agree"], label="약관에 동의합니다", checked=False),
        _ev("check", 5800, tag="input", type="checkbox", sel=["#agree"], label="약관에 동의합니다", checked=True),
        _ev("click", 6000, text="가입하기", sel=["button:has-text('가입하기')"]),
    ]
    navs = [(10, "http://s/search"), (900, "http://s/"), (2050, "http://s/join")]   # 실수 → 뒤로 가기
    out = clean_events(evs, navs)
    assert [(o["action"], o["name"]) for o in out] == [
        ("클릭", "회원가입"), ("입력", "이름"), ("입력", "이메일"), ("체크", "약관 동의"), ("클릭", "가입하기")]
    assert out[1]["value"] == "홍길동" and out[1]["private"]
    assert out[2]["button"] == "#check" and out[2]["button_name"] == "중복 확인"


def test_build_scenario_never_stores_passwords():
    evs = [_ev("click", 0, url="http://s/", tag="a", text="회원가입", sel=["a:has-text('회원가입')"]),
           _ev("input", 1000, tag="input", type="password", sel=["#pw"], label="비밀번호", value="", secret=True),
           _ev("click", 2000, text="가입하기", sel=["button:has-text('가입하기')"])]
    sc = build_scenario("http://s/", evs, [(500, "http://s/join")], topic="회원가입 방법")
    pw = sc["장면"][1]
    assert pw["칸"][0]["값"] == "@보관함" and "#pw" in sc["개인정보칸"]
    assert "요청차단" not in sc                    # 비밀번호 칸 하나뿐인 화면 = 로그인 화면은 막지 않음(로그인은 돼야 함)
    assert sc["장면"][0]["다음주소"] == "**/join"
    assert sc["제목"].endswith("면 끝!") and sc["인트로"][1]["말"].startswith("오늘은 회원가입 방법을")


def test_block_pages_signup_vs_login():
    from autoedit.tutorial.demo_record import block_pages
    mk = lambda url, act="입력", secret=False: {"action": act, "url": url, "secret": secret}
    login = [mk("http://s/login"), mk("http://s/login", secret=True)]
    signup = [mk("http://s/join"), mk("http://s/join", secret=True), mk("http://s/join", secret=True), mk("http://s/join", "체크")]
    form = [mk("http://s/member/new"), mk("http://s/member/new")]
    assert block_pages(login + form) == ["/member/new"]
    assert block_pages(signup) == ["/join"]          # 비밀번호 확인이 있으면 회원가입 → 막음


def test_verify_code_is_asked_and_menu_hover_kept():
    evs = [_ev("click", 0, url="http://s/admin", tag="a", text="회원 등록", sel=["a:has-text('회원 등록')"], hover="a:has-text('회원 관리')"),
           _ev("input", 1000, url="http://s/new", tag="input", type="text", sel=["#code"], label="인증번호", value="482913")]
    sc = build_scenario("http://s/admin", evs, [(500, "http://s/new")], topic="회원 등록")
    assert sc["장면"][0]["먼저올리기"] == "a:has-text('회원 관리')"
    assert sc["장면"][1]["칸"][0]["값"].startswith("@물어보기:인증번호")
    assert sc["장면"][1]["화면주소"] == "http://s/new"


def test_set_start_state_moves_login_to_pre_steps():
    from autoedit.tutorial.demo_record import set_start_state
    d = {"제목": "x, [3단계]면 끝!", "주소": "http://s/login", "단계이름": ["로그인", "메뉴", "등록"],
         "인트로": [{"키": "I1", "말": "안녕"}, {"키": "I2", "말": "오늘은 x 방법을, 세 단계로 알려 드릴게요."}],
         "아웃트로": [{"키": "O1", "말": "오늘 배운 세 단계, 기억하시죠?"}, {"키": "O2", "말": "끝"}],
         "장면": [{"키": "S1", "단계": 1, "동작": "입력", "대상": "아이디", "칸": [{"누를곳": "#id", "값": "a"}], "말": "a"},
                {"키": "S2", "단계": 1, "동작": "입력", "대상": "비밀번호", "칸": [{"누를곳": "#pw", "값": "@보관함"}], "말": "b"},
                {"키": "S3", "단계": 1, "동작": "클릭", "대상": "로그인", "누를곳": "#go", "말": "c"},
                {"키": "S4", "단계": 2, "동작": "클릭", "대상": "회원 관리", "누를곳": "#m", "말": "d", "화면주소": "http://s/admin"},
                {"키": "S5", "단계": 3, "동작": "클릭", "대상": "저장", "누를곳": "#s", "말": "e"}]}
    a = set_start_state(d, "로그인")
    assert [x["키"] for x in a["미리하기"]] == ["P1", "P2", "P3"] and len(a["장면"]) == 2
    assert a["주소"] == "http://s/admin" and a["로그인주소"] == "http://s/login"
    assert a["단계이름"] == ["메뉴", "등록"] and [x["단계"] for x in a["장면"]] == [1, 2]
    assert a["제목"] == "x, [2단계]면 끝!" and "두 단계" in a["인트로"][1]["말"] and "두 단계" in a["아웃트로"][0]["말"]
    b = set_start_state(a, "로그아웃")
    assert len(b["장면"]) == 5 and b["주소"] == "http://s/login" and "세 단계" in b["인트로"][1]["말"]
