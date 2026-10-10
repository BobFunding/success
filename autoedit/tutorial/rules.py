"""규칙 3층 (DESIGN.md 10절): 기본 규칙(1편 기준) ← 브랜드 규칙 ← 이번 영상만. 아래 층이 위를 덮어쓴다.

- 자동으로 고치는 규칙: 문장 사이 쉼, "눌러 주세요" 뒤 쉼, 표현 바꾸기, 확대 배율
- 경고만 하는 규칙: 목표·최대 길이, 한 문장 최대 글자, 안심 문장 없음
- 잠긴 규칙: 개인정보 흐림, 저장·발송 차단 (끌 수 없음 — 화면에도 잠금으로 표시)
기본값을 바꾸면 1편 재현 검사가 깨지므로 바꾸지 않는다."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULT = {
    "목표길이": 90,          # 초
    "최대길이": 180,
    "문장최대글자": 40,
    "문장사이쉼": 0.55,      # 초 (1편)
    "눌러주세요뒤쉼": 0.55,  # "눌러 주세요" 로 끝나는 문장 뒤 (1편은 따로 두지 않음 = 문장 사이 쉼과 같음)
    "표현바꾸기": {},        # {"필수 항목": "꼭 적어야 하는 칸"}
    "확대": 1.6,
    "최대확대": 2.0,
    "안전": {"개인정보흐림": True, "저장차단": True},   # 잠금
}
USER_DIR = Path.home() / ".tutorial_maker"


def merged(*layers: dict | None) -> dict:
    out = copy.deepcopy(DEFAULT)
    for lay in layers:
        for k, v in (lay or {}).items():
            if k == "안전":
                continue                      # 잠긴 규칙은 어느 층도 끌 수 없다
            if k not in DEFAULT:
                continue
            if isinstance(DEFAULT[k], dict):
                out[k] = {**out[k], **(v or {})}
            else:
                out[k] = type(DEFAULT[k])(v)
    return out


def load_user() -> dict:
    p = USER_DIR / "rules.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {} if p.exists() else {}


def save_user(d: dict) -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in d.items() if k in DEFAULT and k != "안전" and v != DEFAULT[k]}
    (USER_DIR / "rules.yaml").write_text(yaml.safe_dump(clean, allow_unicode=True, sort_keys=False), encoding="utf-8")


def apply(sc, rules: dict) -> list[str]:
    """장면 표에 자동 규칙을 적용하고, 경고 목록을 돌려준다. 장면 표에 직접 적은 쉼은 그대로 둔다."""
    from .scenario import GAP
    reps = rules["표현바꾸기"]
    for ln in sc.lines():
        for a, b in reps.items():
            ln.text = ln.text.replace(a, b)
    for s in sc.scenes:
        if s.gap == GAP:                       # 장면 표에 따로 적지 않은 쉼만
            s.gap = rules["문장사이쉼"]
            if s.line.text.rstrip(".!? ").endswith(("눌러 주세요", "누르세요")):
                s.gap = max(s.gap, rules["눌러주세요뒤쉼"])
    return warnings(sc, rules)


def warnings(sc, rules: dict, total: float | None = None) -> list[str]:
    out = []
    for s in sc.scenes:
        if len(s.line.text) > rules["문장최대글자"]:
            out.append(f"{s.no}번 장면 문장이 {len(s.line.text)}자예요(최대 {rules['문장최대글자']}자). 짧게 나누면 따라 하기 쉬워요.")
    if total and total > rules["최대길이"]:
        out.append(f"영상이 {total / 60:.1f}분이에요(최대 {rules['최대길이'] / 60:.0f}분). 장면을 나눠 두 편으로 만드는 게 좋아요.")
    return out
