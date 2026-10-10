"""비밀번호 보관 (임시판, DESIGN.md 5.4 — 운영체제 키체인·"저장할까요?" 화면은 6단계).

장면 표에는 값 대신 '@보관함' 만 적는다. 녹화할 때 값은
1) 환경변수 TUTORIAL_SECRET, 2) PC 안 파일 ~/.tutorial_maker/secrets.json 의 {파일이름: 값}, 3) 검은 창에서 직접 입력(화면에 안 보임)
순서로 찾는다. 장면 표·영상·로그 어디에도 남지 않는다."""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

STORE = Path.home() / ".tutorial_maker" / "secrets.json"
_cache: dict[str, str] = {}


def get(name: str) -> str:
    if name in _cache:
        return _cache[name]
    v = os.environ.get("TUTORIAL_SECRET")
    if not v and STORE.exists():
        v = json.loads(STORE.read_text(encoding="utf-8")).get(name)
    if not v:
        v = getpass.getpass(f"'{name}' 비밀번호를 적어 주세요(화면에 보이지 않아요): ")
    _cache[name] = v
    return v
