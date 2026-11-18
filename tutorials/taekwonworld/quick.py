"""태권월드 시리즈 빠른 만들기(2026-10-15, 사용자 요청: 기다리는 시간 줄이기).
- 보내기 전에 postfix 로 다시 압축하므로 중간 인코딩은 veryfast 로 충분하다(눈에 띄는 화질 차이 없음).
  엔진 기본값(medium)은 그대로 — 1편 재현 검사에는 영향 없음.
- 1080p30 은 만들지 않는다(fast=True). 필요하면 따로 만든다.
- 같은 장면 표·녹화기로 리허설(check)을 이미 통과했으면 만들기에서 리허설을 한 번 더 하지 않는다.
사용(각 편 run_epN.py 의 make): import quick; quick.make(maker, sc, work, HERE)
"""
import json
import os
from pathlib import Path

os.environ.setdefault("TUTORIAL_X264_PRESET", "veryfast")


def rehearsed(work: Path, here: Path) -> bool:
    r = work / "rehearsal.json"
    if not r.exists():
        return False
    try:
        if not json.loads(r.read_text(encoding="utf-8")).get("ok"):
            return False
    except Exception:
        return False
    srcs = [here / "scenario.yaml", *here.parent.glob("ep*/run_ep*.py"), *here.glob("phone/*.html")]
    return r.stat().st_mtime > max(p.stat().st_mtime for p in srcs if p.exists())


def make(maker, sc, work: Path, here: Path) -> dict:
    skip = rehearsed(work, here)
    stages = [s for s in maker.STAGES if not (skip and s == "리허설")]
    if skip:
        print("[빠르게] 리허설을 이미 통과해서 녹화 전 연습은 건너뛰어요")
    return maker.make(sc, work, stages=stages, fast=True)
