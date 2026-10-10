"""만들기 전체 순서: 목소리 → 리허설 → 자동 녹화 → 동기 맞추기 → 편집·출력. 단계마다 중간 결과를 작업 폴더에 남긴다."""
from __future__ import annotations

import json
from pathlib import Path

from .capture import find_sync
from .compose import Composer
from .recorder import Recorder
from .scenario import Scenario

STAGES = ("목소리", "리허설", "녹화", "편집")


def narrate(sc: Scenario, work: Path, log=print) -> dict:
    """문장별 나레이션 → narration.json {키: [문장, wav, 길이]}. 이미 있으면 다시 만들지 않는다(만든 소리 재사용)."""
    from .. import narration as N
    out = work / "narration.json"
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    lines = [N.Line(l.key, l.text, l.rate, l.pitch) for l in sc.lines()]
    N.synthesize(lines, (work / "narration").resolve(), voice=sc.brand.voice, base_rate=sc.brand.voice_rate, log=log)
    nar = {l.key: [l.text, l.path, l.duration] for l in lines}
    out.write_text(json.dumps(nar, ensure_ascii=False, indent=1), encoding="utf-8")
    return nar


def make(sc: Scenario, work: Path, stages=STAGES, fast: bool = False, log=print) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    nar = narrate(sc, work, log) if "목소리" in stages else json.loads((work / "narration.json").read_text(encoding="utf-8"))
    dur = {k: v[2] for k, v in nar.items()}
    if "리허설" in stages:
        Recorder(sc, dur, log).run("dry", work)
    if "녹화" in stages:
        rec = Recorder(sc, dur, log).run("rec", work)
        off = find_sync(work / "cap.mkv", rec["marks"]["sync"])
        (work / "sync.json").write_text(json.dumps({"offset": off}))
        for f in ("body_src.mp4", "body.mp4"):          # 새 녹화면 본편을 다시 만든다
            (work / f).unlink(missing_ok=True)
    result = {}
    if "편집" in stages:
        result = Composer(sc, work, log).build(fast=fast)
    return result
