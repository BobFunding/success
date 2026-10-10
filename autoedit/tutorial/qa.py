"""품질·안전 검사 (DESIGN.md 12절): 1편 때 사람이 하던 확인을 프로그램이 한다.

- 발음 검사: 만든 목소리를 받아쓰기로 다시 듣고, 다르게 들린 단어와 고칠 방법을 알려 준다.
- 자동 검수(RULES.md 9절 체크리스트): 주소창·테두리·배율, 밝게 하기·클릭 효과 위치, 개인정보 노출(글자 인식),
  자막·단계 표시, 영상·소리 길이, 나레이션과 클릭 시각, 의도치 않은 오류 메시지.
결과는 qa.json(화면이 읽음)과 장면별 사진 qa_scenes.jpg.
판정: ok(통과) / warn(사람이 한 번 보면 좋음) / fail(내보내기 전에 꼭 확인). 실패해도 영상은 그대로 남는다.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from ..ffmpeg_utils import FFMPEG, FFPROBE
from .scenario import Scenario, subtitle_text

ERROR_WORDS = re.compile(r"오류|에러|실패|잘못된|문제가 발생|찾을 수 없|error|failed|exception|not found|\b40[34]\b|\b50[0-3]\b", re.I)


# ── 발음 검사 ──
def _audio16k(wav: str) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", wav, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def _norm(s: str) -> str:
    return re.sub(r"[^\w가-힣]", "", s).lower()


def compare_heard(said: str, heard: str) -> tuple[float, list[str]]:
    """띄어쓰기·문장부호는 무시하고 글자로 비교. (같은 정도, 다르게 들린 대본 단어들)"""
    words = re.findall(r"[\w가-힣]+", said)
    flat, owner = "", []
    for i, w in enumerate(words):
        flat += _norm(w)
        owner += [i] * len(_norm(w))
    h = _norm(heard)
    sm = difflib.SequenceMatcher(a=flat, b=h, autojunk=False)
    bad = set()
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace" and h[b0:b1].isdigit():
            continue                                      # '네 가지' 를 '4가지' 로 받아 적는 것은 발음 문제가 아님
        if a1 > a0:
            bad.update(owner[a0:a1])
        elif owner:                                       # 덧붙여 들린 글자: 앞 단어에 붙임
            bad.add(owner[max(0, min(a0, len(owner)) - 1)])
    return sm.ratio(), [words[i] for i in sorted(bad)]


def suggest(word: str, brand_spoken: str = "") -> str:
    w = word
    if brand_spoken and brand_spoken.replace(" ", "") in w.replace(" ", "") and " " in brand_spoken:
        return f"'{brand_spoken}' 처럼 띄어 써 보세요."
    if len(w) >= 5 and re.fullmatch(r"[가-힣]+", w):
        return "단어 사이를 띄어 쓰거나 앞에 쉼표를 넣어 보세요."
    if re.search(r"[A-Za-z]", w):
        return "영어 단어는 한글 발음으로 적어 보세요(예: 로그인)."
    if re.search(r"\d", w):
        return "숫자는 읽는 대로 한글로 적어 보세요."
    return "다른 말로 바꾸거나 쉼표로 끊어 보세요."


def pronunciation(sc: Scenario, nar: dict, work: Path, model_size: str = "medium", log=print) -> dict:
    """문장마다 받아쓰기 → 대본과 비교. 결과는 pronunciation.json (문장·목소리가 같으면 다시 안 함)."""
    out = work / "pronunciation.json"
    key = {"모델": model_size, **{k: [v[0], round(v[2], 3)] for k, v in nar.items()}}
    if out.exists():
        old = json.loads(out.read_text(encoding="utf-8"))
        if old.get("key") == key:
            return old
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {"key": key, "skipped": "받아쓰기 부품이 없어 발음 검사를 건너뛰었어요.", "items": []}
    log(f"[발음] 받아쓰기 모델 준비({model_size}) — 처음에는 내려받느라 몇 분 걸려요")
    try:
        model = WhisperModel(model_size, device="auto", compute_type="auto")
    except Exception:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    items = []
    for ln in sc.lines():
        text, wav, _ = nar[ln.key]
        segs, _ = model.transcribe(_audio16k(wav), language="ko", beam_size=5, vad_filter=False,
                                   condition_on_previous_text=False)
        heard = " ".join(s.text.strip() for s in segs)
        ratio, bad = compare_heard(text, heard)
        ok = ratio >= 0.9 or not bad
        items.append({"키": ln.key, "말": text, "들림": heard, "같은정도": round(ratio, 3), "ok": ok,
                      "다르게": [] if ok else [{"단어": w, "제안": suggest(w, sc.brand.spoken)} for w in bad]})
    res = {"key": key, "items": items, "ok": all(i["ok"] for i in items)}
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[발음] {sum(not i['ok'] for i in items)}문장에서 다르게 들린 단어가 있어요" if not res["ok"] else "[발음] 모두 대본대로 들려요")
    return res


# ── 자동 검수 ──
def _probe(p: Path) -> dict:
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,duration,width,height:format=duration",
                          "-of", "json", str(p)], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    st, whole = j["streams"], float(j.get("format", {}).get("duration") or 0)
    v = next(s for s in st if s["codec_type"] == "video")
    a = next((s for s in st if s["codec_type"] == "audio"), {})
    # mkv 는 스트림 길이가 비어 있어 파일 길이를 쓴다
    return {"v": float(v.get("duration") or whole), "a": float(a.get("duration") or (whole if a else 0)),
            "w": v["width"], "h": v["height"]}


def _frame(p: Path, t: float, size: tuple[int, int] | None = None) -> np.ndarray:
    vf = ["-vf", f"scale={size[0]}:{size[1]}"] if size else []
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", str(p), "-frames:v", "1", *vf,
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    w, h = size or (_probe(p)["w"], _probe(p)["h"])
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3)


def _psnr(a, b) -> float:
    m = float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))
    return 99.0 if m == 0 else 10 * np.log10(255 ** 2 / m)


def check_frame(work: Path, rec: dict, off: float) -> dict:
    """주소창·브라우저 테두리·화면 배율: 녹화 중에 찍은 브라우저 화면 사진과 같은 순간의 녹화 프레임이 같은지
    (테두리가 찍히거나 배율이 틀리면 달라진다)."""
    from PIL import Image
    cap, shot = work / "cap.mkv", work / "check_shot.png"
    t0 = rec["marks"].get("check_shot")
    if not (cap.exists() and shot.exists() and t0 is not None):
        return {"이름": "주소창·테두리·배율", "판정": "warn", "내용": "비교할 화면 사진이 없어 확인하지 못했어요."}
    info = _probe(cap)
    b = np.asarray(Image.open(shot).convert("RGB").resize((960, 540)))
    best = 0.0
    for dt in (-0.1, -0.033, 0.0, 0.033, 0.1, 0.2):            # 사진 찍는 데 걸린 시간만큼 앞뒤로
        t = min(max(0.0, t0 + off + dt), info["v"] - 0.05)
        a = _frame(cap, t, (960, 540))
        best = max(best, min(_psnr(a, b), _psnr(a[:40], b[:40])))
    ok = info["w"] == 2880 and info["h"] == 1620 and best >= 26
    return {"이름": "주소창·테두리·배율", "판정": "ok" if ok else "fail",
            "내용": f"녹화 {info['w']}×{info['h']}, 브라우저 화면과 일치 {best:.0f}dB" + ("" if ok else " — 테두리나 배율이 다를 수 있어요")}


def check_spots(rec: dict) -> dict:
    """클릭 효과(빨간 파동) 자리가 밝게 한 곳(누를 곳) 안에 있는지."""
    clicks, spots = rec["clicks"], rec["spots"]
    miss = []
    for c in clicks:
        if c.get("kind") == "목록":
            continue                                       # 펼친 목록의 항목은 밝게 한 칸 밖에 열린다
        inside = any(s["start"] - 0.3 <= c["t"] <= s["end"] + 0.3 and s["x"] - 20 <= c["x"] <= s["x"] + s["w"] + 20
                     and s["y"] - 20 <= c["y"] <= s["y"] + s["h"] + 20 for s in spots)
        if not inside:
            miss.append(round(c["t"] - rec["marks"]["body_start"], 1))
    n = len([c for c in clicks if c.get("kind") != "목록"])
    return {"이름": "밝게 하기·클릭 효과 위치", "판정": "ok" if not miss else "warn",
            "내용": f"{n - len(miss)}/{n} 클릭이 밝게 한 곳 안" + (f" — 본편 {', '.join(map(str, miss))}초 확인" if miss else "")}


def check_timing(sc: Scenario, rec: dict, dur: dict) -> dict:
    """나레이션과 클릭 시각: 장면의 클릭이 그 문장이 나오는 동안(+쉼) 일어났는지."""
    starts = {ln["key"]: ln["t"] for ln in rec["lines"]}
    keys = [s.key for s in sc.scenes]
    bad = []
    for i, s in enumerate(sc.scenes):
        if s.action not in ("클릭", "체크") or s.key not in starts:
            continue
        a = starts[s.key]
        z = starts.get(keys[i + 1], a + dur[s.key] + s.gap + 2) if i + 1 < len(keys) else a + dur[s.key] + 3
        mine = [c for c in rec["clicks"] if a <= c["t"] < z]
        if not mine or mine[-1]["t"] > a + dur[s.key] + 0.6:
            bad.append(s.no)
    return {"이름": "나레이션과 클릭 시각", "판정": "ok" if not bad else "warn",
            "내용": "모든 클릭이 해당 문장 안에서" if not bad else f"{', '.join(map(str, bad))}번 장면은 클릭이 말보다 늦거나 없어요"}


def check_subs(sc: Scenario, work: Path, nar: dict, intro_len: float, body_t) -> dict:
    """자막 문장 = 대본, 단계 표시가 맞는 구간에 나오는지."""
    ass = next((p for p in (work / f"{sc.file_name}.ass", work / "ep1.ass") if p.exists()), None)
    if not ass:
        return {"이름": "자막·단계 표시", "판정": "warn", "내용": "자막 파일이 없어요."}

    def sec(t):
        h, m, s = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    subs, steps = [], []
    for ln in ass.read_text(encoding="utf-8").splitlines():
        if ln.startswith("Dialogue:"):
            f = ln.split(",", 9)
            (subs if f[3] == "Sub" else steps if f[3] == "Step" else []).append((sec(f[1]), sec(f[2]), f[9]))
    want = [subtitle_text(nar[l.key][0], sc.brand) for l in sc.lines()]
    text_ok = not subs or [s[2] for s in subs] == want
    wrong = []
    for s in sc.scenes:
        t = body_t(s.key)
        if t is None:
            continue
        on = [st for st in steps if st[0] <= t + intro_len + 0.3 <= st[1]]
        if not on or not re.search(rf"\b{s.step}/", on[0][2]):
            wrong.append(s.no)
    ok = text_ok and not wrong
    msg = ("자막 문장이 대본과 같고, " if text_ok else "자막 문장이 대본과 달라요. ") + \
          ("단계 표시가 모두 맞는 구간에" if not wrong else f"{', '.join(map(str, wrong))}번 장면의 단계 표시가 달라요")
    return {"이름": "자막·단계 표시", "판정": "ok" if ok else "fail", "내용": msg}


def check_length(final: Path) -> dict:
    p = _probe(final)
    d = abs(p["v"] - p["a"])
    return {"이름": "영상·소리 길이", "판정": "ok" if d < 0.1 else "warn", "내용": f"영상 {p['v']:.2f}초, 소리 {p['a']:.2f}초"}


def private_values(sc: Scenario) -> list[str]:
    """개인정보 칸에 적은 값(데모 값이라도 화면에 보이면 안 됨)."""
    vals = []
    priv = set(sc.privacy_fields)
    for s in sc.scenes:
        for f in s.fields:
            if f.target in priv and len(_norm(f.value)) >= 3 and not f.value.startswith("@"):
                vals.append(f.value)
    return vals


def check_ocr(sc: Scenario, final: Path, interval: float = 1.5, log=print) -> tuple[dict, dict]:
    """완성 영상을 글자 인식으로 훑어: 개인정보(전화·이메일 등 + 개인정보 칸에 적은 값), 오류 메시지."""
    from ..privacy import _ocr_video, regex_pii
    try:
        dets, _ = _ocr_video(final, interval, log)
    except ImportError:
        skip = {"판정": "warn", "내용": "글자 인식 부품이 없어 건너뛰었어요."}
        return {"이름": "개인정보 최종 검사 (글자 인식)", **skip}, {"이름": "의도치 않은 오류 메시지", **skip}
    vals = [_norm(v) for v in private_values(sc)]
    pii, errs = [], []
    by_t: dict[float, list[str]] = {}
    for d in dets:
        by_t.setdefault(round(d.t, 1), []).append(d.text)
    for t, texts in sorted(by_t.items()):
        joined = " ".join(texts)
        kind = regex_pii(joined) or next((regex_pii(x) for x in texts if regex_pii(x)), None)
        flat = _norm(joined)
        if kind or any(v and v in flat for v in vals):
            pii.append(f"{t:.0f}초({kind or '적은 값'})")
        m = ERROR_WORDS.search(joined)
        if m:
            errs.append(f"{t:.0f}초 '{m.group(0)}'")
    a = {"이름": "개인정보 최종 검사 (글자 인식)", "판정": "ok" if not pii else "fail",
         "내용": "노출 0건" if not pii else f"보일 수 있는 곳: {', '.join(pii[:6])}"}
    b = {"이름": "의도치 않은 오류 메시지", "판정": "ok" if not errs else "warn",
         "내용": "없음" if not errs else f"확인해 보세요: {', '.join(errs[:6])}"}
    return a, b


def _safe(name: str, fn, *a, log=print, n: int = 1):
    """검사 하나가 부품이 없거나 실패해도 만들기는 성공으로 끝낸다 — 그 검사만 'warn: 건너뜀'."""
    try:
        return fn(*a)
    except ModuleNotFoundError as e:
        msg = f"부품({e.name})이 없어 건너뛰었어요. setup 을 다시 실행하면 설치돼요."
    except Exception as e:
        msg = f"확인하지 못해 건너뛰었어요({type(e).__name__})."
    log(f"[검수] {name}: {msg}")
    r = {"이름": name, "판정": "warn", "내용": msg}
    return r if n == 1 else tuple(dict(r, 이름=x) for x in name.split(" / "))


def scene_sheet(sc: Scenario, final: Path, times: list[tuple[int, float]], out: Path) -> None:
    """장면별 사진 한 장으로 모아 보기."""
    from PIL import Image, ImageDraw
    tiles = []
    for no, t in times:
        tiles.append((no, Image.fromarray(_frame(final, t, (480, 270)))))
    if not tiles:
        return
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 480, rows * 290), "white")
    d = ImageDraw.Draw(sheet)
    for i, (no, im) in enumerate(tiles):
        x, y = (i % cols) * 480, (i // cols) * 290
        sheet.paste(im, (x, y + 20))
        d.text((x + 6, y + 4), f"#{no}", fill="black")
    sheet.save(out, quality=85)


def review(sc: Scenario, work: Path, result: dict, log=print, ocr: bool = True) -> dict:
    """만든 영상 자동 검수. result 는 Composer.build 결과."""
    rec = json.loads((work / "log_rec.json").read_text(encoding="utf-8"))
    nar = json.loads((work / "narration.json").read_text(encoding="utf-8"))
    dur = {k: v[2] for k, v in nar.items()}
    off = json.loads((work / "sync.json").read_text())["offset"]
    final = Path(result["final"])
    trim0 = rec["marks"]["body_start"] + off - 0.2
    starts = {ln["key"]: ln["t"] for ln in rec["lines"]}
    body_t = lambda k: (starts[k] + off - trim0) if k in starts else None
    items = [_safe("주소창·테두리·배율", check_frame, work, rec, off, log=log),
             _safe("밝게 하기·클릭 효과 위치", check_spots, rec, log=log),
             _safe("나레이션과 클릭 시각", check_timing, sc, rec, dur, log=log),
             _safe("자막·단계 표시", check_subs, sc, work, nar, result["intro"], body_t, log=log),
             _safe("영상·소리 길이", check_length, final, log=log)]
    if ocr:
        log("[검수] 완성 영상 글자 인식 중…")
        a, b = _safe("개인정보 최종 검사 (글자 인식) / 의도치 않은 오류 메시지",
                     lambda: check_ocr(sc, final, log=log), log=log, n=2)
        items += [a, b]
    pron = work / "pronunciation.json"
    if pron.exists():
        p = json.loads(pron.read_text(encoding="utf-8"))
        bad = [i for i in p.get("items", []) if not i["ok"]]
        items.append({"이름": "발음 검사", "판정": "warn" if bad else "ok",
                      "내용": p.get("skipped") or ("다르게 들린 단어 없음" if not bad else
                                                   f"{len(bad)}문장 확인: " + ", ".join(w['단어'] for i in bad for w in i['다르게'])[:80])})
    # 장면별 사진: 클릭 장면은 클릭 순간, 나머지는 문장 시작 1.5초 뒤
    times = []
    for s in sc.scenes:
        t = body_t(s.key)
        if t is None:
            continue
        cl = [c["t"] for c in rec["clicks"] if starts[s.key] <= c["t"] <= starts[s.key] + dur[s.key] + 1]
        tt = (cl[-1] + off - trim0) if cl else t + 1.5
        times.append((s.no, result["intro"] + tt))
    sheet = _safe("장면별 사진", scene_sheet, sc, final, times, work / "qa_scenes.jpg", log=log)
    if isinstance(sheet, dict):
        items.append(sheet)
    worst = "fail" if any(i["판정"] == "fail" for i in items) else "warn" if any(i["판정"] == "warn" for i in items) else "ok"
    res = {"판정": worst, "항목": items, "사진": str(work / "qa_scenes.jpg") if (work / "qa_scenes.jpg").exists() else ""}
    (work / "qa.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[검수] {sum(i['판정'] == 'ok' for i in items)}/{len(items)} 통과")
    return res
