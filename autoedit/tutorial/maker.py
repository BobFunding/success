"""만들기 전체 순서: 목소리 → 리허설 → 자동 녹화 → 동기 맞추기 → 편집·출력. 단계마다 중간 결과를 작업 폴더에 남긴다."""
from __future__ import annotations

import json
from dataclasses import asdict
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


def recording_key(sc: Scenario, dur: dict) -> str:
    """녹화에 영향을 주는 것(장면·문장 길이·주소·흐림·차단·녹화 방식)이 같으면 이미 찍은 녹화를 다시 쓴다."""
    from .capture import capture_method
    return json.dumps([sc.url, [asdict(s) for s in sc.scenes], {k: round(v, 3) for k, v in dur.items()},
                       sc.privacy_fields, sc.block_requests, sc.close_popups, sc.end_hold, capture_method()],
                      ensure_ascii=False, sort_keys=True, default=str)


def estimate(sc: Scenario, dur: dict, stages=STAGES, reuse_rec: bool = False, preview: bool = False,
             pron: bool = True) -> dict[str, float]:
    """단계별 예상 시간(초). 4코어 PC 기준 실측에서 잡은 대략값 — 화면에는 '약 N분' 으로만 보인다."""
    from .capture import capture_method
    body = sum(dur.get(s.key, 3) + s.gap for s in sc.scenes) + 2
    total = body + sum(dur.get(l.key, 3) for l in sc.intro + sc.outro) + 6
    k = 6 if capture_method() == "frames" else 1
    est = {"목소리": 15, "발음 검사": (60 + 4 * len(dur)) if pron else 0, "리허설": 0 if reuse_rec else body * 1.1,
           "녹화": 0 if reuse_rec else body * (1.4 * k if k > 1 else 1.1) + 10,
           "화면 연출": body * (0.8 if preview else 8), "인트로·아웃트로·자막": 70, "출력": total * (0.5 if preview else 3),
           "자동 검수": 0 if preview else total * 2.5}
    keep = {"목소리": "목소리", "발음 검사": "목소리", "리허설": "리허설", "녹화": "녹화"}
    return {n: v for n, v in est.items() if keep.get(n, "편집") in stages and v}


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
         on_stage=None, subtitles: bool = True, preview: bool = False, check: bool = True) -> dict:
    """on_stage(이름, 예상초표): 화면에 진행 단계를 알리는 함수. rules 가 없으면 3층 규칙을 읽어 쓴다.
    preview: 빠른 미리보기(저화질). 같은 장면 표면 녹화는 최종본에서 다시 쓴다.
    check: 발음 검사·자동 검수를 한다(1편 재현 검사처럼 영상만 필요할 때는 끔)."""
    from . import qa
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
    rkey = recording_key(sc, dur)
    kp = work / "cap.mkv.key"
    reuse = "녹화" in stages and (work / "cap.mkv").exists() and kp.exists() and kp.read_text(encoding="utf-8") == rkey \
        and (work / "sync.json").exists() and (work / "log_rec.json").exists()
    est = estimate(sc, dur, stages, reuse, preview, check)
    if check and "목소리" in stages:
        stage("발음 검사", est)
        qa.pronunciation(sc, nar, work, log=log)
    if reuse:
        log("[녹화] 장면 표가 그대로라 이미 찍은 녹화를 다시 써요")
    else:
        if "리허설" in stages:
            stage("리허설", est)
            rehearse(sc, work, dur, log)
        if "녹화" in stages:
            stage("자동 녹화", est)
            rec = Recorder(sc, dur, log).run("rec", work)
            off = find_sync(work / "cap.mkv", rec["marks"]["sync"])
            (work / "sync.json").write_text(json.dumps({"offset": off}))
            kp.write_text(rkey, encoding="utf-8")
    result = {}
    if "편집" in stages:
        result = Composer(sc, work, log, rules=rules, subtitles=subtitles).build(
            fast=fast, on_stage=lambda n: stage(n, est), preview=preview)
        result["warnings"] = warn + R.warnings(sc, rules, result["total"])
        if check and not preview:
            stage("자동 검수", est)
            result["qa"] = qa.review(sc, work, result, log)
    return result
