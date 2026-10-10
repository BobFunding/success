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
    """문장별 나레이션 → narration.json {키: [문장, wav, 길이]}.
    문장·목소리가 그대로면 만든 소리를 다시 쓰고, 바뀌었으면 새로 만든다."""
    from .. import narration as N
    out, meta_p = work / "narration.json", work / "narration_voice.json"
    meta = {"voice": sc.brand.voice, "rate": sc.brand.voice_rate}
    if out.exists():
        nar = json.loads(out.read_text(encoding="utf-8"))
        same_text = {k: v[0] for k, v in nar.items()} == {l.key: l.text for l in sc.lines()}
        same_voice = not meta_p.exists() or json.loads(meta_p.read_text()) == meta
        if same_text and same_voice and all(Path(v[1]).exists() for v in nar.values()):
            return nar
    lines = [N.Line(l.key, l.text, l.rate, l.pitch) for l in sc.lines()]
    N.synthesize(lines, (work / "narration").resolve(), voice=sc.brand.voice, base_rate=sc.brand.voice_rate, log=log)
    nar = {l.key: [l.text, l.path, l.duration] for l in lines}
    out.write_text(json.dumps(nar, ensure_ascii=False, indent=1), encoding="utf-8")
    meta_p.write_text(json.dumps(meta))
    return nar


def estimate(sc: Scenario, dur: dict, stages=STAGES) -> dict[str, float]:
    """단계별 예상 시간(초). 4코어 PC 기준 실측에서 잡은 대략값 — 화면에는 '약 N분' 으로만 보인다."""
    from .capture import capture_method
    body = sum(dur.get(s.key, 3) + s.gap for s in sc.scenes) + 2
    total = body + sum(dur.get(l.key, 3) for l in sc.intro + sc.outro) + 6
    k = 6 if capture_method() == "frames" else 1
    est = {"목소리": 15, "리허설": body * 1.1, "녹화": body * (1.4 * k if k > 1 else 1.1) + 10,
           "화면 연출": body * 8, "인트로·아웃트로·자막": 70, "출력": total * 3}
    keep = {"목소리": "목소리", "리허설": "리허설", "녹화": "녹화"}
    return {n: v for n, v in est.items() if keep.get(n, "편집") in stages}


def rehearse(sc: Scenario, work: Path, dur: dict, log=print) -> dict:
    """리허설(창 없이, 녹화 없이). 결과를 rehearsal.json 에 남긴다 — 화면은 이걸 읽어 그 장면 줄을 빨갛게 표시한다."""
    from .recorder import SceneError
    res = {"ok": True, "장면수": len(sc.scenes)}
    try:
        Recorder(sc, dur, log).run("dry", work)
    except SceneError as e:
        s = e.scene
        res = {"ok": False, "장면": s.no, "키": s.key, "대상": s.label or s.target, "말": s.line.text,
               "메시지": str(e), "사진": str(work / "last_dry.png")}
        raise
    finally:
        (work / "rehearsal.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def make(sc: Scenario, work: Path, stages=STAGES, fast: bool = False, log=print, rules: dict | None = None,
         on_stage=None, subtitles: bool = True) -> dict:
    """on_stage(이름, 예상초표): 화면에 진행 단계를 알리는 함수. rules 가 없으면 3층 규칙을 읽어 쓴다."""
    from . import rules as R
    work.mkdir(parents=True, exist_ok=True)
    rules = rules or R.merged(R.load_user(), sc.brand.rules, sc.rules)
    warn = R.apply(sc, rules)
    for w in warn:
        log(f"[규칙] {w}")
    stage = on_stage or (lambda name, est=None: None)
    stage("목소리 만들기")
    nar = narrate(sc, work, log) if "목소리" in stages else json.loads((work / "narration.json").read_text(encoding="utf-8"))
    dur = {k: v[2] for k, v in nar.items()}
    est = estimate(sc, dur, stages)
    if "리허설" in stages:
        stage("리허설", est)
        rehearse(sc, work, dur, log)
    if "녹화" in stages:
        stage("자동 녹화", est)
        rec = Recorder(sc, dur, log).run("rec", work)
        off = find_sync(work / "cap.mkv", rec["marks"]["sync"])
        (work / "sync.json").write_text(json.dumps({"offset": off}))
        for f in ("body_src.mp4", "body.mp4"):          # 새 녹화면 본편을 다시 만든다
            (work / f).unlink(missing_ok=True)
    result = {}
    if "편집" in stages:
        result = Composer(sc, work, log, rules=rules, subtitles=subtitles).build(fast=fast, on_stage=lambda n: stage(n, est))
        result["warnings"] = warn + R.warnings(sc, rules, result["total"])
    return result
