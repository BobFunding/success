"""장면 표(scenario.yaml) 읽기·검사, 브랜드 읽기.

장면 표는 사람이 읽고 고치는 파일이라 열쇠 이름이 한국어다(DESIGN.md 4절). 여기서 파이썬 객체로 바꾸고,
빠진 값은 1편 기준 기본값으로 채운다. 기본값을 바꾸면 1편 재현 검사가 깨지므로 바꾸지 않는다."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

PRESETS = Path(__file__).parent / "presets"
ACTIONS = ("클릭", "체크", "입력", "선택", "스크롤", "보여주기", "대기")
GAP = 0.55                      # 문장 사이 쉼(1편)


class ScenarioError(ValueError):
    """장면 표가 잘못됨. 메시지는 사람이 읽는 말로, 몇 번 장면인지 함께."""


@dataclass
class Line:
    """나레이션 한 문장."""
    key: str
    text: str
    rate: int = 0
    pitch: int = 0


@dataclass
class Field:
    """입력 장면의 칸 하나."""
    target: str
    value: str
    delay: float = 0.09          # 한 글자 간격
    approach: float = -150.0     # 칸 가운데에서 이만큼 왼쪽에 커서를 둔 채 클릭(1편)
    move: float = 0.5            # 커서 이동 시간


@dataclass
class Pick:
    """선택 장면의 목록 하나: 몇 번째 선택 상자에서 몇 번째 항목(또는 글자)."""
    box: int = -1                # 선택 상자(div[role=combobox]) 번호 — MUI 처럼 직접 만든 목록
    index: int | None = None
    text: str | None = None
    target: str = ""             # 기본 <select> 의 누를 곳 (이때는 text 로 고름)


@dataclass
class Scene:
    no: int                      # 1부터 (오류 메시지용)
    key: str
    step: int
    line: Line
    action: str
    target: str = ""             # 누를 곳 (Playwright 선택자 또는 보이는 글자)
    label: str = ""              # 사람이 보는 이름
    gap: float = GAP             # 문장 끝 뒤 쉼
    bubble: str = ""             # 말풍선
    # 클릭·체크
    lead: float = 0.35           # 문장 끝보다 이만큼 먼저 클릭
    move: float | None = None    # 커서 이동 시간 (없으면 문장 길이로 자동)
    pre_wait: float | None = None  # 이동 전 기다림: 문장 길이에 대한 비율 (없으면 자동)
    offset: tuple[float, float] = (0.0, 0.0)   # 커서 도착 위치 보정(CSS px)
    spot_target: str = ""        # 밝게 할 곳 (없으면 누를 곳)
    spot_pad: float = 8
    spot_hold: float | None = None  # 클릭 뒤 밝게 유지 (없으면 클릭 0.4, 버튼 없는 입력 0.3)
    spot_from: str = "문장"      # 밝게 시작: 문장(문장 시작) / 이동(커서 출발)
    spot_shape: str = "가로"     # 여러 칸 묶음: 가로(첫 칸 높이) / 세로(첫 칸 너비)
    spot_width: float | None = None
    spot_extend_left: float = 0
    next_url: str = ""           # 클릭 뒤 기다릴 주소
    wait_for: str = ""           # 클릭 뒤 나타날 때까지 기다릴 것
    # 입력·선택·스크롤
    fields: list[Field] = field(default_factory=list)
    button: str = ""
    button_move: float = 0.45
    picks: list[Pick] = field(default_factory=list)
    scroll_first: tuple[float, float] | None = None   # (위치, 시간)
    scrolls: list[tuple[str, float, float]] = field(default_factory=list)  # ("스크롤", 위치, 시간) / ("대기", 초, 0)


@dataclass
class Brand:
    name: str = ""               # 표기 (자막)
    spoken: str = ""             # 읽는 이름 (대본)
    background: tuple[str, str] = ("#1B2559", "#405BEA")
    accent: str = "#CC1424"
    point: str = "#54B4CC"
    highlight: str = "#FFD84D"   # 제목 강조 글자
    font: str = "Pretendard"
    logo: str = ""
    voice: str = "ko-KR-HyunsuMultilingualNeural"
    voice_rate: int = -8
    tone: str = "차분"
    greeting: str = ""           # 고정 인사말 (비우면 '안녕하세요, {읽는이름}입니다.')
    footer: str = ""             # 설명 끝 고정 문구 (내보내기용)
    rules: dict = field(default_factory=dict)   # 브랜드 규칙 층
    key: str = ""                # 파일 이름(presets/brands/<key>.yaml)


@dataclass
class Scenario:
    title: str
    url: str
    brand: Brand
    steps: list[str]
    scenes: list[Scene]
    intro: list[Line]
    outro: list[Line]
    file_name: str = "tutorial"
    next_episode: str = ""
    start_state: str = "로그아웃"
    privacy_fields: list[str] = field(default_factory=list)
    block_requests: str = ""     # 이 주소가 들어간 화면에서는 저장·발송 요청(xhr/fetch) 차단
    end_hold: float = 0.9        # 마지막 클릭 뒤 화면 유지
    rules: dict = field(default_factory=dict)   # 이번 영상만 규칙 층
    source: Path | None = None

    def lines(self) -> list[Line]:
        return self.intro + [s.line for s in self.scenes] + self.outro

    @property
    def title_plain(self) -> str:
        return self.title.replace("[", "").replace("]", "")


def _num(v, default):
    return default if v is None else float(v)


def _scene(i: int, d: dict, gap: float) -> Scene:
    where = f"{i}번 장면"
    if not isinstance(d, dict):
        raise ScenarioError(f"{where}의 형식이 잘못됐어요.")
    for k in ("키", "말", "동작", "단계"):
        if k not in d:
            raise ScenarioError(f"{where}에 '{k}'이(가) 없어요.")
    act = d["동작"]
    if act not in ACTIONS:
        raise ScenarioError(f"{where}의 동작 '{act}'을(를) 모르겠어요. 쓸 수 있는 동작: {', '.join(ACTIONS)}")
    ln = Line(str(d["키"]), str(d["말"]), int(d.get("속도", 0)), int(d.get("높낮이", 0)))
    sp = d.get("강조") or {}
    sc = Scene(no=i, key=ln.key, step=int(d["단계"]), line=ln, action=act,
               target=str(d.get("누를곳") or d.get("대상") or ""), label=str(d.get("대상") or ""),
               gap=_num(d.get("쉼"), gap), bubble=str(d.get("말풍선") or ""),
               lead=_num(d.get("앞당김"), 0.35), move=d.get("이동"), pre_wait=d.get("먼저기다림비율"),
               offset=tuple(d.get("커서보정") or (0, 0)),
               spot_target=str(sp.get("대상") or ""), spot_pad=_num(sp.get("여백"), 8),
               spot_hold=sp.get("유지"), spot_from=str(sp.get("시작") or "문장"),
               spot_shape=str(sp.get("모양") or "가로"), spot_width=sp.get("너비"),
               spot_extend_left=_num(sp.get("왼쪽늘리기"), 0),
               next_url=str(d.get("다음주소") or ""), wait_for=str(d.get("기다릴것") or ""),
               button=str(d.get("버튼") or ""), button_move=_num(d.get("버튼이동"), 0.45))
    if d.get("먼저스크롤") is not None:
        s = d["먼저스크롤"]
        sc.scroll_first = (float(s["위치"]), float(s["시간"]))
    if act in ("클릭", "체크") and not sc.target:
        raise ScenarioError(f"{where}({act})에 누를 곳이 없어요. '대상'에 버튼 글자를 적어 주세요.")
    if act == "입력":
        raw = d.get("칸") or ([{"대상": sc.target, "값": d.get("값", "")}] if sc.target else [])
        if not raw:
            raise ScenarioError(f"{where}(입력)에 적을 칸이 없어요.")
        for f in raw:
            sc.fields.append(Field(str(f.get("누를곳") or f.get("대상")), str(f.get("값", "")),
                                   _num(f.get("간격"), 0.09), _num(f.get("다가가기"), -150), _num(f.get("이동"), 0.5)))
    if act == "선택":
        for p in d.get("목록") or []:
            if p.get("누를곳"):
                sc.picks.append(Pick(text=str(p.get("항목", "")), index=p.get("항목번호"), target=str(p["누를곳"])))
            else:
                sc.picks.append(Pick(int(p["상자"]), p.get("항목번호"), p.get("항목")))
        if not sc.picks:
            raise ScenarioError(f"{where}(선택)에 고를 목록이 없어요.")
    if act == "스크롤":
        for s in d.get("스크롤") or []:
            if "대기" in s:
                sc.scrolls.append(("대기", float(s["대기"]), 0.0))
            else:
                sc.scrolls.append(("스크롤", float(s["위치"]), float(s["시간"])))
    return sc


USER_BRANDS = Path.home() / ".tutorial_maker" / "brands"


def brand_path(name: str) -> Path:
    """사용자가 만든 브랜드(PC 안) → 기본 제공 브랜드 순서로 찾는다."""
    for d in (USER_BRANDS, PRESETS / "brands"):
        if (d / f"{name}.yaml").exists():
            return d / f"{name}.yaml"
    return PRESETS / "brands" / f"{name}.yaml"


def brand_names() -> list[str]:
    names = {p.stem for d in (PRESETS / "brands", USER_BRANDS) if d.exists() for p in d.glob("*.yaml")}
    return sorted(names, key=lambda n: (n == "basic", n))


def load_brand(name_or_path: str, base: Path | None = None) -> Brand:
    p = Path(name_or_path)
    if not p.suffix:
        p = brand_path(name_or_path)
    elif base and not p.is_absolute():
        p = base / p
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    b = Brand(name=d.get("이름", ""), spoken=d.get("읽는이름", d.get("이름", "")))
    if "배경" in d:
        b.background = tuple(d["배경"])
    for k, a in (("강조색", "accent"), ("포인트색", "point"), ("제목강조색", "highlight"), ("글꼴", "font"),
                 ("목소리", "voice")):
        if k in d:
            setattr(b, a, str(d[k]))
    if "목소리빠르기" in d:
        b.voice_rate = int(d["목소리빠르기"])
    b.tone = str(d.get("말투") or "차분")
    b.greeting, b.footer = str(d.get("인사말") or ""), str(d.get("고정문구") or "")
    b.rules = dict(d.get("규칙") or {})
    b.key = p.stem
    if d.get("로고"):
        b.logo = str((p.parent / d["로고"]).resolve())
    return b


def load(path: str | Path) -> Scenario:
    path = Path(path)
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        raise ScenarioError("장면 표 파일을 읽지 못했어요.")
    for k in ("제목", "주소", "장면"):
        if k not in d:
            raise ScenarioError(f"장면 표에 '{k}'이(가) 없어요.")
    gap = float(d.get("쉼", GAP))
    scenes = [_scene(i, s, gap) for i, s in enumerate(d["장면"], 1)]
    steps = list(d.get("단계이름") or [])
    if steps:
        for s in scenes:
            if not 1 <= s.step <= len(steps):
                raise ScenarioError(f"{s.no}번 장면의 단계 {s.step}이(가) 단계이름 수({len(steps)})를 벗어나요.")
        if [s.step for s in scenes] != sorted(s.step for s in scenes):
            raise ScenarioError("장면이 단계 순서대로 놓여 있지 않아요.")
    lines = lambda key: [Line(str(x["키"]), str(x["말"]), int(x.get("속도", 0)), int(x.get("높낮이", 0)))
                         for x in d.get(key) or []]
    sc = Scenario(title=str(d["제목"]), url=str(d["주소"]),
                  brand=load_brand(str(d.get("브랜드", "taekwonworld")), path.parent),
                  steps=steps, scenes=scenes, intro=lines("인트로"), outro=lines("아웃트로"),
                  file_name=str(d.get("파일이름") or path.stem), next_episode=str(d.get("다음편") or ""),
                  start_state=str(d.get("시작상태") or "로그아웃"),
                  privacy_fields=list(d.get("개인정보칸") or []), block_requests=str(d.get("요청차단") or ""),
                  end_hold=float(d.get("끝유지", 0.9)), rules=dict(d.get("규칙") or {}), source=path)
    keys = [ln.key for ln in sc.lines()]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        raise ScenarioError(f"문장 키가 겹쳐요: {', '.join(sorted(dup))}")
    return sc


def subtitle_text(text: str, brand: Brand) -> str:
    """대본(읽는 이름)을 자막 표기로: '태권 월드' → '태권월드'."""
    if brand.spoken and brand.name and brand.spoken != brand.name:
        text = text.replace(brand.spoken, brand.name)
    return text
