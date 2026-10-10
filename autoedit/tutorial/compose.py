"""편집·합성: 인트로 + 본편(screenfx) + 아웃트로 → 자막·단계 표시·말풍선 → 나레이션 → 1440p60 / 1080p30, srt, 챕터.
(tutorials/ep1/build_ep1.py 일반화. 숫자·순서는 1편과 같아야 한다 — 1편 재현 검사)

작업 폴더 입력: narration.json, log_rec.json, sync.json, cap.mkv
작업 폴더 출력: body.mp4, intro.mp4, outro.mp4, <파일이름>.ass/.srt, narration.wav, <파일이름>_1440p60.mp4, _1080p30.mp4, 챕터.txt
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from ..ffmpeg_utils import FFMPEG
from ..narration import build_track
from ..screenfx import ScreenFxSettings, _background, render
from .scenario import Scenario, subtitle_text

FONTS = Path(__file__).parent / "fonts"          # 동봉 글꼴(Pretendard, OFL) — 운영체제와 무관하게 같은 모양
W, H, FPS = 2560, 1440, 60
GAP = 0.45                                        # 인트로·아웃트로 문장 사이


def run(*a):
    subprocess.run([FFMPEG, "-v", "error", "-y", *a], check=True)


def render_svg(svg: str, width: int, height: int) -> bytes:
    """illustrate.render_svg 와 같은 설정 + 동봉 글꼴 폴더."""
    import resvg_py
    return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width, height=height, font_family="Malgun Gothic",
                                       sans_serif_family="Malgun Gothic", font_dirs=[str(FONTS)]))


def ease(p):
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** 3


def ts(t):
    cs = int(round(t * 100)); h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_color(hex_, alpha=0):
    h = hex_.lstrip("#"); return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}"


def srt_time(x):
    return f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(round(x % 1 * 1000)) % 1000:03d}"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Composer:
    def __init__(self, sc: Scenario, work: Path, log=print):
        self.sc, self.work, self.say = sc, work, log
        b = sc.brand
        self.BG, self.ACCENT, self.POINT, self.FONT = tuple(b.background), b.accent, b.point, b.font
        self.STEPS = sc.steps
        nar = json.loads((work / "narration.json").read_text(encoding="utf-8"))
        self.NAR = nar
        self.DUR = {k: v[2] for k, v in nar.items()}
        self.TXT = {k: v[0] for k, v in nar.items()}
        self.rec = json.loads((work / "log_rec.json").read_text(encoding="utf-8"))
        self.OFF = json.loads((work / "sync.json").read_text())["offset"]

    # ── 그림 조각 ──
    def svg_layer(self, inner: str) -> np.ndarray:
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{inner}</svg>'
        png = render_svg(svg, W, H)
        return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED).astype(np.float32) / 255.0

    def logo_layer(self, y: int, scale: float = 1.45) -> np.ndarray:
        lg = cv2.imread(self.sc.brand.logo, cv2.IMREAD_UNCHANGED)
        lg = cv2.resize(lg, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        lh, lw = lg.shape[:2]
        pad_x, pad_y = 60, 40
        bw, bh = lw + 2 * pad_x, lh + 2 * pad_y
        x0 = (W - bw) // 2
        card = self.svg_layer(f'<rect x="{x0}" y="{y}" width="{bw}" height="{bh}" rx="28" fill="#ffffff"/>'
                              f'<rect x="{x0}" y="{y + 10}" width="{bw}" height="{bh}" rx="28" fill="#000" opacity="0.15"/>'
                              f'<rect x="{x0}" y="{y}" width="{bw}" height="{bh}" rx="28" fill="#ffffff"/>')
        a = lg[..., 3:4]
        ys, xs = y + pad_y, x0 + pad_x
        card[ys:ys + lh, xs:xs + lw, :3] = card[ys:ys + lh, xs:xs + lw, :3] * (1 - a) + lg[..., :3] * a
        return card

    def step_card(self, i: int, x: int, y: int, w: int, h: int, check: bool = False) -> str:
        F, P = self.FONT, self.POINT
        num = f'<circle cx="{x + 70}" cy="{y + h / 2}" r="38" fill="{P}"/>' \
              f'<text x="{x + 70}" y="{y + h / 2 + 15}" text-anchor="middle" font-family="{F}" font-weight="900" font-size="44" fill="#fff">{i + 1}</text>'
        if check:
            num = f'<circle cx="{x + 70}" cy="{y + h / 2}" r="38" fill="{self.ACCENT}"/>' \
                  f'<path d="M{x + 52},{y + h / 2} l12,13 l24,-26" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'
        return (f'<rect x="{x}" y="{y + 8}" width="{w}" height="{h}" rx="26" fill="#000" opacity="0.18"/>'
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="26" fill="#ffffff"/>{num}'
                f'<text x="{x + 130}" y="{y + h / 2 + 16}" font-family="{F}" font-weight="800" font-size="46" fill="#1B2559">{_esc(self.STEPS[i])}</text>')

    def title_svg(self) -> str:
        """'관장님 회원가입, [3단계]면 끝!' → [ ] 안은 제목 강조색."""
        t = _esc(self.sc.title).replace("[", f'<tspan fill="{self.sc.brand.highlight}">').replace("]", "</tspan>")
        return (f'<text x="{W / 2}" y="740" text-anchor="middle" font-family="{self.FONT}" font-weight="900" '
                f'font-size="104" fill="#ffffff">{t}</text>')

    def animate(self, out: Path, dur: float, layers: list[tuple[np.ndarray, float]]):
        """layers: (RGBA 레이어, 나타나는 시각). 0.45초 동안 페이드 + 아래에서 살짝 올라옴."""
        bg = _background(W, H, ScreenFxSettings(background=self.BG)).astype(np.float32) / 255.0
        proc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                                 "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                                 "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
        for fi in range(int(dur * FPS)):
            t = fi / FPS
            img = bg.copy()
            for lay, t_in in layers:
                p = ease((t - t_in) / 0.45)
                if p <= 0:
                    continue
                dy = int((1 - p) * 30)
                L = np.roll(lay, dy, axis=0) if dy else lay
                a = L[..., 3:4] * p
                img = img * (1 - a) + L[..., :3] * a
            k = min(1.0, (dur - t) / 0.3)            # 끝 0.3초 페이드 아웃(장면 전환)
            img = img * k + bg * (1 - k) if k < 1 else img
            proc.stdin.write((img * 255).astype(np.uint8).tobytes())
        proc.stdin.close(); proc.wait()

    def card_row(self):
        n = len(self.STEPS)
        cw = int(min(760, (W - 120 - (n - 1) * 50) / n))
        return cw, 130, [(W - n * cw - (n - 1) * 50) // 2 + i * (cw + 50) for i in range(n)]

    def bubble_time(self, key: str) -> float:
        mk = self.rec["marks"]
        if f"bubble_{key}" in mk:
            return mk[f"bubble_{key}"]
        if "reassure" in mk:                      # 1편 옛 기록 형식
            return mk["reassure"]
        return next(ln["t"] for ln in self.rec["lines"] if ln["key"] == key)

    # ── 전체 ──
    def build(self, fast: bool = False) -> dict:
        work, sc, DUR, TXT = self.work, self.sc, self.DUR, self.TXT
        base = sc.file_name
        mk = self.rec["marks"]
        TRIM0 = mk["body_start"] + self.OFF - 0.2
        TRIM1 = mk["body_end"] + self.OFF
        BODY_LEN = TRIM1 - TRIM0
        tb = lambda t: t + self.OFF - TRIM0           # 기록 시각 → 본편 시각

        # 1) 본편: 녹화본 자르기 → screenfx
        if not (work / "body.mp4").exists():
            run("-ss", f"{TRIM0:.3f}", "-to", f"{TRIM1:.3f}", "-i", str(work / "cap.mkv"),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "8", "-pix_fmt", "yuv420p", "-an", str(work / "body_src.mp4"))
            clicks = [dict(c, t=round(tb(c["t"]), 3)) for c in self.rec["clicks"]]
            spots = [dict(s, start=tb(s["start"]), end=tb(s["end"])) for s in self.rec["spots"]]
            s = ScreenFxSettings(background=self.BG, zoom=1.6, max_zoom=2.0, speedup=1.0, out_size=(W, H),
                                 crf=16, x264_preset="medium", padding=0.06)
            plan = render(work / "body_src.mp4", work / "body.mp4", s, clicks=clicks, spots=spots, out_fps=FPS)
            self.say(f"[편집] 본편 확대 {len(plan['focus'])}곳")

        # 2) 인트로·아웃트로 카드
        I = [k.key for k in sc.intro]
        O = [k.key for k in sc.outro]
        I1, I2 = 0.8, 0.8 + DUR[I[0]] + GAP
        INTRO_LEN = round(I2 + DUR[I[1]] + 0.7, 2)
        cw, chh, cx = self.card_row()
        cy = 900
        n = len(self.STEPS)
        if not (work / "intro.mp4").exists():
            layers = [(self.logo_layer(330), 0.15), (self.svg_layer(self.title_svg()), 0.6)]
            layers += [(self.svg_layer(self.step_card(i, cx[i], cy, cw, chh)), I2 + 1.2 + i * 0.9) for i in range(n)]
            self.animate(work / "intro.mp4", INTRO_LEN, layers)
        O1 = 0.5
        O2 = O1 + DUR[O[0]] + 0.9
        OUTRO_LEN = round(O2 + DUR[O[1]] + 1.0, 2)
        if not (work / "outro.mp4").exists():
            head = self.svg_layer(f'<text x="{W / 2}" y="420" text-anchor="middle" font-family="{self.FONT}" font-weight="900" '
                                  f'font-size="92" fill="#ffffff">오늘 배운 {_count(n)} 단계</text>')
            layers = [(head, 0.1)]
            layers += [(self.svg_layer(self.step_card(i, cx[i], 560, cw, chh)), 0.2) for i in range(n)]
            layers += [(self.svg_layer(self.step_card(i, cx[i], 560, cw, chh, check=True)), O1 + 0.9 + i * 0.55)
                       for i in range(n)]
            if sc.next_episode:
                nxt = self.svg_layer(f'<rect x="{W / 2 - 520}" y="830" width="1040" height="120" rx="60" fill="#ffffff" opacity="0.14"/>'
                                     f'<text x="{W / 2}" y="910" text-anchor="middle" font-family="{self.FONT}" font-weight="800" '
                                     f'font-size="58" fill="#ffffff">다음 편 ▶ {_esc(sc.next_episode)}</text>')
                layers += [(nxt, O2)]
            layers += [(self.logo_layer(1060, 1.1), O2 + 0.6)]
            self.animate(work / "outro.mp4", OUTRO_LEN, layers)

        # 3) 자막·단계 표시·말풍선 (ASS) + srt
        body_lines = [(ln["key"], tb(ln["t"]) + INTRO_LEN) for ln in self.rec["lines"]]
        placed = [(I[0], I1), (I[1], I2)] + body_lines + \
                 [(O[0], INTRO_LEN + BODY_LEN + O1), (O[1], INTRO_LEN + BODY_LEN + O2)]
        TOTAL = INTRO_LEN + BODY_LEN + OUTRO_LEN
        sub = lambda k: subtitle_text(TXT[k], sc.brand)
        ev = []
        for k, t in placed:
            ev.append(f"Dialogue: 0,{ts(t)},{ts(t + DUR[k] + 0.25)},Sub,,0,0,0,,{sub(k)}")
        st = [tb(mk[f"step{i + 1}"]) for i in range(n)] + [BODY_LEN]
        for i in range(n):
            ev.append(f"Dialogue: 1,{ts(INTRO_LEN + st[i])},{ts(INTRO_LEN + st[i + 1])},Step,,0,0,0,,"
                      f"{{\\fad(250,200)}}  {i + 1}/{n}  {self.STEPS[i]}  ")
        for s in sc.scenes:
            if s.bubble:
                r0 = tb(self.bubble_time(s.key)) + INTRO_LEN
                ev.append(f"Dialogue: 1,{ts(r0)},{ts(r0 + DUR[s.key] + 0.6)},Bubble,,0,0,0,,{{\\fad(200,200)}}  {s.bubble}  ")
        F, P, A = self.FONT, self.POINT, self.ACCENT
        ass = "\n".join([
            "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            # 자막: 흰 글씨 + 반투명 남청 상자 (어떤 화면 위에서도 읽힘)
            f"Style: Sub,{F} ExtraBold,60,&H00FFFFFF,&H00FFFFFF,{ass_color('#141B40', 0x30)},{ass_color('#141B40', 0x30)},-1,0,0,0,100,100,0,0,3,14,0,2,200,200,46,1",
            f"Style: Step,{F} ExtraBold,40,&H00FFFFFF,&H00FFFFFF,{ass_color(P)},{ass_color(P)},-1,0,0,0,100,100,0,0,3,10,0,7,150,0,22,1",
            f"Style: Bubble,{F} ExtraBold,56,&H00FFFFFF,&H00FFFFFF,{ass_color(A)},{ass_color(A)},-1,0,0,0,100,100,0,0,3,16,0,2,0,0,170,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *ev, ""])
        ass_path = work / f"{base}.ass"
        ass_path.write_text(ass, encoding="utf-8")
        srt = []
        for i, (k, t) in enumerate(placed, 1):
            srt += [str(i), f"{srt_time(t)} --> {srt_time(t + DUR[k] + 0.25)}", sub(k), ""]
        (work / f"{base}.srt").write_text("\n".join(srt), encoding="utf-8")

        # 4) 나레이션 트랙
        build_track([(t, self.NAR[k][1]) for k, t in placed], TOTAL, work / "narration.wav")

        # 5) 최종 합성
        final = work / f"{base}_1440p60.mp4"
        run("-i", str(work / "intro.mp4"), "-i", str(work / "body.mp4"), "-i", str(work / "outro.mp4"),
            "-i", str(work / "narration.wav"),
            "-filter_complex", f"[0:v][1:v][2:v]concat=n=3:v=1:a=0,fps={FPS},ass=filename='{ass_path}':fontsdir='{FONTS}'[v]",
            "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
            "-g", str(FPS * 2), "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{TOTAL:.3f}", str(final))
        if not fast:
            run("-i", str(final), "-vf", "scale=1920:1080:flags=lanczos,fps=30", "-c:v", "libx264", "-preset", "medium",
                "-b:v", "16M", "-maxrate", "20M", "-bufsize", "32M", "-pix_fmt", "yuv420p", "-g", "60",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", str(work / f"{base}_1080p30.mp4"))
        chap = [("인트로", 0)] + [(f"{i + 1}단계 {self.STEPS[i]}", INTRO_LEN + st[i]) for i in range(n)] + \
               [("마무리", INTRO_LEN + BODY_LEN)]
        (work / "챕터.txt").write_text("\n".join(f"{int(t // 60)}:{int(t % 60):02d} {c}" for c, t in chap), encoding="utf-8")
        self.say(f"[편집] 완성: 인트로 {INTRO_LEN:.1f}s + 본편 {BODY_LEN:.1f}s + 아웃트로 {OUTRO_LEN:.1f}s = {TOTAL:.1f}s")
        return {"intro": INTRO_LEN, "body": BODY_LEN, "outro": OUTRO_LEN, "total": TOTAL, "final": str(final)}


def _count(n: int) -> str:
    """3 → '세' (오늘 배운 세 단계)."""
    words = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열"]
    return words[n] if n < len(words) else str(n)
