"""개인정보 감지: 화면 속 글자(OCR)와 말소리(대본) 양쪽에서 찾는다."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from .llm import LLM, LLMUnavailable
from .transcribe import Word

PATTERNS: dict[str, re.Pattern] = {
    "주민등록번호": re.compile(r"\d{6}\s*[-–]\s*[1-8][\d*]{6}"),
    "전화번호": re.compile(r"(?<!\d)(01[016789]|0[2-6]\d?|070)[\s.\-)]*\d{3,4}[\s.\-]*\d{4}(?!\d)"),
    "이메일": re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+"),
    "카드번호": re.compile(r"(?<!\d)\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}(?!\d)"),
    "차량번호": re.compile(r"(?<!\d)\d{2,3}\s?[가-힣]\s?\d{4}(?!\d)"),
    "주소": re.compile(r"[가-힣]+(?:시|도)\s?[가-힣]+(?:구|군|시)\s?[가-힣0-9]+(?:로|길|동|읍|면)\s?\d+"),
    "계좌번호": re.compile(r"(?<!\d)\d{2,6}-\d{2,6}-\d{2,8}(?:-\d{1,3})?(?!\d)"),
}
_DATE = re.compile(r"^(19|20)\d{2}-\d{1,2}-\d{1,2}$")


def regex_pii(text: str) -> str | None:
    t = text.replace("O", "0").replace("o", "0") if re.search(r"\d", text) else text
    for kind, pat in PATTERNS.items():
        m = pat.search(t)
        if not m:
            continue
        if kind == "계좌번호" and (_DATE.match(m.group(0)) or len(re.sub(r"\D", "", m.group(0))) < 10):
            continue
        return kind
    return None


# ───────────────────────── 화면 글자 ─────────────────────────

@dataclass
class Mosaic:
    start: float
    end: float
    x: int
    y: int
    w: int
    h: int
    kind: str
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Det:
    t: float
    text: str
    box: tuple[int, int, int, int]  # x1, y1, x2, y2


def _ocr_video(video: Path, interval: float, log) -> tuple[list[_Det], float]:
    import cv2
    import easyocr
    import torch

    reader = easyocr.Reader(["ko", "en"], gpu=torch.cuda.is_available(), verbose=False)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(round(fps * interval)))
    dets: list[_Det] = []
    prev_small, prev_res, prev_ocr_t = None, [], -1e9
    ocr_runs = 0
    for fi in range(total):
        if fi % step:
            if not cap.grab():
                break
            continue
        ok, frame = cap.read()
        if not ok:
            break
        t = fi / fps
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (320, 180)).astype(np.float32)
        # 화면이 안 바뀌었으면 이전 OCR 결과를 재사용 (정적인 화면에서 수십 배 빨라짐).
        # 평균 차이가 아니라 '바뀐 픽셀 비율'로 판단해야 작은 글자(알림 등)가 새로 뜨는 것도 잡힌다.
        changed = 1.0 if prev_small is None else float((np.abs(small - prev_small) > 18).mean())
        if changed < 0.001 and t - prev_ocr_t < 2.0:
            res = prev_res
        else:
            h, w = frame.shape[:2]
            scale = min(1.0, 1600 / max(w, h))
            img = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
            res = []
            for pts, text, conf in reader.readtext(img[:, :, ::-1]):
                if conf < 0.25 or not text.strip():
                    continue
                xs = [p[0] / scale for p in pts]
                ys = [p[1] / scale for p in pts]
                res.append((text.strip(), (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))))
            prev_small, prev_res, prev_ocr_t = small, res, t
            ocr_runs += 1
        dets += [_Det(t, text, box) for text, box in res]
        if fi % (step * 40) == 0:
            log(f"[개인정보] 화면 글자 검사 {t:6.1f}s / {total / fps:.1f}s (OCR {ocr_runs}회)")
    cap.release()
    return dets, interval


def _lines(dets_at_t: list[_Det]) -> list[list[_Det]]:
    """같은 줄에 있는 글자 상자를 묶는다 (전화번호가 상자 여러 개로 쪼개지는 경우 대비)."""
    rows: list[list[_Det]] = []
    for d in sorted(dets_at_t, key=lambda d: (d.box[1] + d.box[3]) / 2):
        yc, hh = (d.box[1] + d.box[3]) / 2, d.box[3] - d.box[1]
        if rows:
            last = rows[-1][-1]
            lyc = (last.box[1] + last.box[3]) / 2
            if abs(yc - lyc) < 0.5 * max(hh, last.box[3] - last.box[1]):
                rows[-1].append(d)
                continue
        rows.append([d])
    return [sorted(r, key=lambda d: d.box[0]) for r in rows]


class OcrVerdict(BaseModel):
    index: int
    kind: str = Field(description="개인정보 종류: 이름, 주소, 전화번호, 이메일, 계정ID, 계좌, 주민번호, 차량번호, 기타")


class OcrVerdicts(BaseModel):
    items: list[OcrVerdict]


OCR_SYSTEM = """영상 화면에서 OCR 로 읽은 글자 목록입니다. 이 중 개인정보라서 모자이크해야 하는 항목만 고르세요.
개인정보: 일반인의 실명, 상세 주소, 전화번호, 이메일, 메신저/SNS 아이디·닉네임(채팅·DM 화면), 계좌번호, 주민번호, 카드번호, 차량번호, 주문/송장번호, 로그인 정보.
개인정보 아님: 유명인·회사·브랜드·지명(동네 이름 수준), 앱 메뉴/버튼 글자, 자막, 일반 단어.
OCR 오타가 섞여 있을 수 있으니 형태로 판단하세요. 애매하면 개인정보로 판단합니다(가리는 쪽이 안전)."""


def detect_screen_pii(video: Path, interval: float, llm: LLM | None, allowlist: list[str],
                      frame_w: int, frame_h: int, log=print) -> tuple[list[Mosaic], list[tuple[float, tuple]]]:
    """반환: (모자이크 목록, 화면 글자 위치 [(시각, 상자)] — 일러스트 카드가 글자를 피해 가도록 쓰임)"""
    dets, interval = _ocr_video(video, interval, log)
    text_boxes = [(d.t, d.box) for d in dets]
    allow = [a.strip() for a in allowlist if a.strip()]

    # 1) 줄 단위 + 상자 단위로 정규식 검사
    pii_det: dict[int, tuple[str, str]] = {}  # id(det) -> (kind, text)
    by_t: dict[float, list[_Det]] = {}
    for d in dets:
        by_t.setdefault(d.t, []).append(d)
    for ds in by_t.values():
        for row in _lines(ds):
            joined = " ".join(d.text for d in row)
            kind = regex_pii(joined)
            for d in row:
                own = regex_pii(d.text)
                if own:
                    pii_det[id(d)] = (own, d.text)
                elif kind and re.search(r"[\d@]", d.text):
                    pii_det[id(d)] = (kind, joined)

    # 2) 정규식으로 못 잡는 이름·아이디 등은 Claude 가 판단
    if llm is not None and llm.available:
        uniq = sorted({d.text for d in dets if id(d) not in pii_det and len(d.text) >= 2})
        flagged: dict[str, str] = {}
        for start in range(0, len(uniq), 400):
            chunk = uniq[start:start + 400]
            listing = "\n".join(f"{i}: {t}" for i, t in enumerate(chunk))
            try:
                verdicts = llm.parse(OCR_SYSTEM, listing, OcrVerdicts, effort="low")
                for v in verdicts.items:
                    if 0 <= v.index < len(chunk):
                        flagged[chunk[v.index]] = v.kind
            except LLMUnavailable as e:
                log(f"[개인정보] Claude 판단 실패, 정규식 결과만 사용: {e}")
                break
        for d in dets:
            if d.text in flagged and id(d) not in pii_det:
                pii_det[id(d)] = (flagged[d.text], d.text)

    hits = [d for d in dets if id(d) in pii_det and not any(a in d.text for a in allow)]

    # 3) 같은 위치에 연속으로 나타난 것끼리 하나의 모자이크 구간으로 합친다
    tracks: list[dict] = []
    for d in sorted(hits, key=lambda d: d.t):
        for tr in tracks:
            if d.t - tr["last"] <= interval * 1.6 and _iou(tr["box"], d.box) > 0.2:
                tr["last"] = d.t
                tr["box"] = _union(tr["box"], d.box)
                break
        else:
            kind, text = pii_det[id(d)]
            tracks.append({"first": d.t, "last": d.t, "box": d.box, "kind": kind, "text": text})

    mosaics = []
    for tr in tracks:
        x1, y1, x2, y2 = tr["box"]
        mx, my = int((x2 - x1) * 0.12) + 6, int((y2 - y1) * 0.25) + 6
        x1, y1 = max(0, x1 - mx), max(0, y1 - my)
        x2, y2 = min(frame_w, x2 + mx), min(frame_h, y2 + my)
        if x2 - x1 < 4 or y2 - y1 < 4:
            continue
        # 샘플 사이 어딘가에서 나타났을 수 있으므로 앞뒤로 한 간격씩 여유
        mosaics.append(Mosaic(round(max(0.0, tr["first"] - interval), 2), round(tr["last"] + interval, 2),
                              x1, y1, x2 - x1, y2 - y1, tr["kind"], tr["text"]))
    log(f"[개인정보] 화면 속 개인정보 {len(mosaics)}건 모자이크 예정")
    return mosaics, text_boxes


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


# ───────────────────────── 말소리 ─────────────────────────

@dataclass
class Beep:
    start: float
    end: float
    kind: str
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


class SpokenPII(BaseModel):
    first_index: int = Field(description="개인정보가 시작되는 단어 번호")
    last_index: int = Field(description="개인정보가 끝나는 단어 번호")
    kind: str


class SpokenPIIList(BaseModel):
    items: list[SpokenPII]


SPOKEN_SYSTEM = """유튜브 영상 대본(번호 붙은 단어)입니다. 화자가 말로 노출한 개인정보 구간을 찾으세요.
대상: 일반인의 실명(풀네임), 전화번호, 상세 주소(번지·동호수), 계좌번호, 주민번호, 카드번호, 차량번호, 비밀번호/인증번호.
대상 아님: 유명인·회사·브랜드, 동네/도시 이름 수준의 지명, 화자 본인이 공개적으로 쓰는 채널명.
개인정보에 해당하는 단어들만 정확히 포함하도록 범위를 잡으세요. 없으면 빈 목록."""


def detect_spoken_pii(words: list[Word], llm: LLM | None, allowlist: list[str], log=print) -> list[Beep]:
    beeps: list[Beep] = []
    # 정규식: 연속된 단어 몇 개를 이어붙여서 숫자 패턴 검사
    for i in range(len(words)):
        if not re.search(r"[\d@]", words[i].text):  # 숫자/이메일이 시작되는 단어부터만 (앞 단어까지 삐- 처리하지 않게)
            continue
        for span in (1, 2, 3, 4):
            j = i + span - 1
            if j >= len(words):
                break
            text = " ".join(w.text for w in words[i:j + 1])
            kind = regex_pii(text)
            if kind:
                beeps.append(Beep(words[i].start, words[j].end, kind, text))
                break

    if llm is not None and llm.available and words:
        for start in range(0, len(words), 1200):
            chunk = range(start, min(len(words), start + 1200))
            listing = "\n".join(f"{i}: {words[i].text}" for i in chunk)
            try:
                found = llm.parse(SPOKEN_SYSTEM, listing, SpokenPIIList, effort="low")
            except LLMUnavailable as e:
                log(f"[개인정보] 말소리 Claude 판단 실패: {e}")
                break
            for it in found.items:
                a, b = sorted((it.first_index, it.last_index))
                if 0 <= a < len(words) and b < len(words) and b - a < 25:
                    text = " ".join(w.text for w in words[a:b + 1])
                    beeps.append(Beep(words[a].start, words[b].end, it.kind, text))

    allow = [a.strip() for a in allowlist if a.strip()]
    beeps = [b for b in beeps if not any(a in b.text for a in allow)]
    beeps.sort(key=lambda b: b.start)
    merged: list[Beep] = []
    for b in beeps:
        if merged and b.start <= merged[-1].end + 0.1:
            merged[-1].end = max(merged[-1].end, b.end)
        else:
            merged.append(Beep(round(b.start - 0.05, 3), round(b.end + 0.05, 3), b.kind, b.text))
    log(f"[개인정보] 말로 나온 개인정보 {len(merged)}건 삐- 처리 예정")
    return merged
