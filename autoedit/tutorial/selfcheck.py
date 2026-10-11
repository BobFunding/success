"""자가 점검 (DESIGN.md 16절 10단계): 사용자 PC(Windows·Mac·Linux)에서 버튼 하나로 '이 PC에서 제대로 도는지' 확인한다.

1. 부품: Python, ffmpeg(인코더), 브라우저(Chromium), 목소리(edge-tts, 인터넷), 글꼴, 보관함, 쓰기 권한, 빈 공간.
2. 짧은 영상: 프로그램에 든 연습용 사이트를 PC 안에서 띄워 3장면짜리 영상을 끝까지 만든다(빠른 미리보기, 몇 분).
3. 1편 재현(선택, 오래 걸림·인터넷 필요): 이 PC에서 1편을 만들어, 클라우드에서 검사를 통과한 기준 기록
   (tutorials/ep1/reference: 누른 자리·밝게 할 곳·장면 안 박자·문장 길이)과 비교한다.
   원래 1편 코드는 Linux 가상 화면에서만 돌아서 Windows·Mac 에서는 '같은 때 원래 코드와 비교'를 할 수 없다.
   대신 기준 기록과 비교하고, 운영체제마다 글꼴이 달라 생기는 몇 px 차이는 허용한다(TOL_XY_OS).

결과는 화면과 '자가점검결과.md' 에 남는다(개인정보·키 없음). 그대로 복사해 개발자·AI 에게 보내면 된다.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "tutorials" / "ep1" / "reference"
SAMPLE = ROOT / "tutorials" / "sample_site"
TOL_XY_OS = 8          # px(녹화 픽셀): 운영체제마다 글꼴·글자 폭이 조금 달라 생기는 차이
TOL_T_OS = 0.35        # 초: 다른 PC·다른 녹화 방식(한 장씩 찍기)의 장면 안 박자
TOL_DUR = 0.15         # 초: 문장 길이(같은 목소리면 거의 같음)


def _item(name, ok, msg, level=None):
    return {"이름": name, "판정": level or ("ok" if ok else "fail"), "내용": msg}


def parts(log=print) -> list[dict]:
    from ..ffmpeg_utils import FFMPEG
    out = []
    v = sys.version_info
    out.append(_item("Python", v >= (3, 12), f"{platform.python_version()} ({'3.12 이상' if v >= (3, 12) else '3.12 이상이 필요해요 — setup 을 다시'})"))
    try:
        ver = subprocess.run([FFMPEG, "-version"], capture_output=True, text=True, timeout=10).stdout.split("\n")[0]
        enc = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10).stdout
        need = {"libx264": "영상", "aac": "소리", "libsvtav1": "웹용 AV1", "libwebp": "웹 포스터"}
        miss = [f"{k}({n})" for k, n in need.items() if k not in enc]
        out.append(_item("ffmpeg", "libx264" in enc and "aac" in enc, ver[:50] + (f" · 없음: {', '.join(miss)}" if miss else ""),
                         "warn" if miss and "libx264" in enc else None))
    except Exception as e:
        out.append(_item("ffmpeg", False, f"찾지 못함({type(e).__name__}) — setup 을 다시 실행해 주세요"))
    try:
        from playwright.sync_api import sync_playwright
        from .recorder import CHROME
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path=CHROME)
            pg = br.new_page(device_scale_factor=1.5, viewport={"width": 640, "height": 360})
            pg.set_content("<p style='font:24px sans-serif'>점검</p>")
            shot = pg.screenshot()
            br.close()
        out.append(_item("브라우저(Chromium)", len(shot) > 1000, f"화면 사진 {len(shot) // 1024}KB (배율 1.5)"))
    except Exception as e:
        out.append(_item("브라우저(Chromium)", False, f"열지 못함({type(e).__name__}) — '{sys.executable} -m playwright install chromium'"))
    try:
        from ..narration import Line
        from .voices import synthesize
        d = Path(tempfile.mkdtemp())
        ln = Line("T", "점검 문장입니다.")
        synthesize([ln], d, d, "ko-KR-HyunsuMultilingualNeural", -8, log=lambda *a: None)
        out.append(_item("목소리(인터넷)", ln.duration > 0.5, f"현수 목소리 {ln.duration:.2f}초"))
        shutil.rmtree(d, ignore_errors=True)
    except Exception as e:
        out.append(_item("목소리(인터넷)", False, f"만들지 못함({type(e).__name__}) — 인터넷 연결을 확인해 주세요(자막만 목소리는 인터넷 없이 됨)"))
    fonts = ROOT / "autoedit" / "tutorial" / "fonts"
    out.append(_item("글꼴(Pretendard)", (fonts / "Pretendard-Black.otf").exists(), "동봉 글꼴"))
    from . import secrets as SEC
    kr = SEC._kr()
    out.append(_item("비밀번호 보관함", True, "운영체제 보관함" if kr else "PC 안 파일(운영체제 보관함 없음)", None if kr else "warn"))
    try:
        t = ROOT / "output" / ".write_test"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("x"); t.unlink()
        free = shutil.disk_usage(ROOT).free / 1024 ** 3
        out.append(_item("저장 공간", free > 5, f"남은 공간 {free:.0f}GB (영상 한 편 만들 때 2~5GB 씀)", None if free > 5 else "warn"))
    except Exception as e:
        out.append(_item("저장 공간", False, f"output 폴더에 쓸 수 없어요({type(e).__name__})"))
    from .capture import capture_method
    m = capture_method()
    out.append(_item("녹화 방식", True, "운영체제 화면 녹화(x11)" if m == "x11" else "한 장씩 찍기(어느 PC 에서나 같은 화질, 녹화가 조금 오래 걸림)"))
    return out


class _Site:
    """연습용 사이트를 PC 안(127.0.0.1)에서만 띄운다. 비어 있는 포트를 골라 장면 표 주소를 바꿔 쓴다."""
    def __init__(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]; s.close()
        handler = lambda *a, **k: SimpleHTTPRequestHandler(*a, directory=str(SAMPLE), **k)
        SimpleHTTPRequestHandler.log_message = lambda *a: None
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


SAMPLE_SCENARIO = """제목: 도서관 회원 정보 입력, [2단계]면 끝!
주소: http://localhost:PORT/index.html
브랜드: basic
시작상태: 로그아웃
단계이름: [회원 정보 입력 화면 찾기, 회원 정보 입력하기]
개인정보칸: ['#name']
요청차단: /join.html
파일이름: 자가점검
인트로:
- {키: I1, 말: 안녕하세요.}
- {키: I2, 말: '오늘은 회원 정보 입력 방법을, 두 단계로 알려 드릴게요.'}
아웃트로:
- {키: O1, 말: '오늘 배운 두 단계, 기억하시죠?'}
- {키: O2, 말: 고맙습니다.}
장면:
- {키: S1, 단계: 1, 동작: 클릭, 대상: 회원가입 하기, 누를곳: "a:has-text('회원가입 하기')", 다음주소: '**/join.html', 말: '먼저, 회원가입 하기를 눌러 주세요.'}
- {키: S2, 단계: 2, 동작: 입력, 대상: 이름, 칸: [{누를곳: '#name', 값: 홍길동}], 말: 이름을 적어 주세요.}
- {키: S3, 단계: 2, 동작: 입력, 대상: 이메일, 칸: [{누를곳: '#email', 값: test@example.com}], 말: '마지막으로, 이메일을 적으면 끝이에요.'}
"""


def sample_video(work: Path, log=print, voice: str = "") -> dict:
    """연습용 사이트로 짧은 영상(빠른 미리보기)을 끝까지 만든다."""
    from . import maker
    from . import scenario as S
    site = _Site()
    try:
        work.mkdir(parents=True, exist_ok=True)
        p = work / "scenario.yaml"
        p.write_text(SAMPLE_SCENARIO.replace("PORT", str(site.port)), encoding="utf-8")
        sc = S.load(p)
        if voice:
            sc.brand.voice = voice
        t = time.time()
        r = maker.make(sc, work, preview=True, check=False, log=log)
        f = Path(r["final"])
        from ..ffmpeg_utils import probe
        info = probe(f)
        ok = f.exists() and info.duration > 8 and info.has_audio
        return _item("짧은 영상 만들기", ok, f"{info.duration:.1f}초 영상 · {info.width}×{info.height} · {time.time() - t:.0f}초 걸림 ({f.name})")
    except Exception as e:
        return _item("짧은 영상 만들기", False, f"멈춤: {type(e).__name__}: {str(e)[:200]}")
    finally:
        site.close()


def compare_reference(work: Path) -> list[dict]:
    """이 PC에서 만든 1편과 기준 기록 비교(위치·장면 안 박자·문장 길이·영상 길이)."""
    from .repro import _per_scene, compare_logs
    out = []
    ref = json.loads((REF / "log_rec.json").read_text(encoding="utf-8"))
    mine = json.loads((work / "log_rec.json").read_text(encoding="utf-8"))
    r = compare_logs(ref, mine, tol_t=99)
    same = r["clicks"][0] == r["clicks"][1] and r["spots"][0] == r["spots"][1] and r["lines"][0] and r["scene_events"]
    out.append(_item("1편: 장면·클릭 수", same, f"클릭 {r['clicks'][1]}/{r['clicks'][0]}, 밝게 {r['spots'][1]}/{r['spots'][0]}"))
    xy = max(r["click_xy"], r["spot_box"])
    out.append(_item("1편: 누른 자리·밝게 할 곳", xy <= TOL_XY_OS, f"차이 최대 {xy:.1f}px (허용 {TOL_XY_OS}px — 글꼴 차이)",
                     "warn" if TOL_XY_OS < xy <= 30 else None))
    out.append(_item("1편: 장면 안 박자", r["scene_t"] <= TOL_T_OS, f"{r['scene_t']:.3f}초 (허용 {TOL_T_OS}초)"))
    rd = json.loads((REF / "narration_durations.json").read_text(encoding="utf-8"))
    md = {k: v[2] for k, v in json.loads((work / "narration.json").read_text(encoding="utf-8")).items()}
    dd = max(abs(rd[k] - md.get(k, 0)) for k in rd)
    out.append(_item("1편: 문장 길이(목소리)", dd <= TOL_DUR, f"차이 최대 {dd:.3f}초", "warn" if TOL_DUR < dd <= 0.4 else None))
    tl = json.loads((REF / "timeline.json").read_text(encoding="utf-8"))
    mt = json.loads((work / "timeline.json").read_text(encoding="utf-8"))
    dt = abs(tl["total"] - mt["total"])
    out.append(_item("1편: 영상 길이", dt <= 1.0, f"{mt['total']:.1f}초 (기준 {tl['total']:.1f}초)"))
    return out


def ep1(work: Path, log=print) -> list[dict]:
    from . import maker
    from . import rules as R
    from . import scenario as S
    sc = S.load(ROOT / "tutorials" / "ep1" / "scenario.yaml")
    try:
        maker.make(sc, work, rules=R.merged(), check=False, fast=True, log=log)
    except Exception as e:
        return [_item("1편 재현", False, f"멈춤: {type(e).__name__}: {str(e)[:200]} (인터넷·사이트 접속 확인)")]
    return compare_reference(work)


def run(full: bool = False, log=print, on_stage=None) -> dict:
    stage = on_stage or (lambda n: None)
    work = ROOT / "output" / "자가점검"
    t0 = time.time()
    stage("부품 점검")
    items = parts(log)
    stage("짧은 영상 만들기")
    if all(i["판정"] != "fail" for i in items if i["이름"] in ("ffmpeg", "브라우저(Chromium)")):
        voice_ok = next((i for i in items if i["이름"] == "목소리(인터넷)"), {}).get("판정") == "ok"
        items.append(sample_video(work / "짧은영상", log, voice="" if voice_ok else "자막만"))
    if full:
        stage("1편 재현")
        items += ep1(work / "1편", log)
    ok = all(i["판정"] != "fail" for i in items)
    rep = {"판정": "ok" if ok else "fail", "항목": items, "컴퓨터": f"{platform.system()} {platform.release()} · {platform.machine()}",
           "날짜": time.strftime("%Y-%m-%d %H:%M"), "걸린시간": round(time.time() - t0), "1편": full}
    md = [f"# 자가 점검 — {'통과' if ok else '확인 필요'}", "", f"- 컴퓨터: {rep['컴퓨터']}", f"- 날짜: {rep['날짜']} · {rep['걸린시간']}초", ""]
    md += [f"- {'✓' if i['판정'] == 'ok' else '⚠' if i['판정'] == 'warn' else '✗'} {i['이름']}: {i['내용']}" for i in items]
    work.mkdir(parents=True, exist_ok=True)
    (work / "자가점검결과.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (work / "자가점검결과.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    rep["글"] = "\n".join(md)
    return rep
