"""1편 편집·합성: 인트로 + 본편(screenfx) + 아웃트로 → 자막·단계 표시 → 나레이션 → 1440p60 / 1080p30."""
import json, subprocess, sys
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, "/home/user/success")
from autoedit.illustrate import render_svg
from autoedit.narration import build_track
from autoedit.screenfx import ScreenFxSettings, _background, render

here = Path(__file__).parent
W, H, FPS = 2560, 1440, 60
BG = ("#1B2559", "#405BEA")          # 남청 → 브랜드 파랑
ACCENT, POINT = "#CC1424", "#54B4CC"  # 강조(로고 빨강), 1편 포인트(하늘)
FONT = "Pretendard"
NAR = json.loads((here / "narration.json").read_text(encoding="utf-8"))
DUR = {k: v[2] for k, v in NAR.items()}
TXT = {k: v[0] for k, v in NAR.items()}
log = json.loads((here / "log_rec.json").read_text(encoding="utf-8"))
OFF = json.loads((here / "sync.json").read_text())["offset"]
STEPS = ["가입 화면 찾기", "정보 입력하기", "약관 동의하고 등록"]


def run(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


# ───────── 1) 본편: 녹화본 자르기 → screenfx ─────────
mk = log["marks"]
TRIM0 = mk["body_start"] + OFF - 0.2
TRIM1 = mk["body_end"] + OFF
BODY_LEN = TRIM1 - TRIM0
tb = lambda t: t + OFF - TRIM0                     # 기록 시각 → 본편 시각
if not (here / "body.mp4").exists():
    run("-ss", f"{TRIM0:.3f}", "-to", f"{TRIM1:.3f}", "-i", str(here / "cap.mkv"),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "8", "-pix_fmt", "yuv420p", "-an", str(here / "body_src.mp4"))
    clicks = [dict(c, t=round(tb(c["t"]), 3)) for c in log["clicks"]]
    spots = [dict(s, start=tb(s["start"]), end=tb(s["end"])) for s in log["spots"]]
    s = ScreenFxSettings(background=BG, zoom=1.6, max_zoom=2.0, speedup=1.0, out_size=(W, H),
                         crf=16, x264_preset="medium", padding=0.06)
    plan = render(here / "body_src.mp4", here / "body.mp4", s, clicks=clicks, spots=spots, out_fps=FPS)
    print("본편 줌", len(plan["focus"]), "곳")


# ───────── 2) 인트로·아웃트로 카드 ─────────
def svg_layer(inner: str) -> np.ndarray:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{inner}</svg>'
    png = render_svg(svg, W, H)
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED).astype(np.float32) / 255.0


def logo_layer(y: int, scale: float = 1.45) -> np.ndarray:
    lg = cv2.imread(str(here / "logo.png"), cv2.IMREAD_UNCHANGED)
    lg = cv2.resize(lg, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
    lh, lw = lg.shape[:2]
    pad_x, pad_y = 60, 40
    bw, bh = lw + 2 * pad_x, lh + 2 * pad_y
    x0 = (W - bw) // 2
    card = svg_layer(f'<rect x="{x0}" y="{y}" width="{bw}" height="{bh}" rx="28" fill="#ffffff"/>'
                     f'<rect x="{x0}" y="{y + 10}" width="{bw}" height="{bh}" rx="28" fill="#000" opacity="0.15"/>'
                     f'<rect x="{x0}" y="{y}" width="{bw}" height="{bh}" rx="28" fill="#ffffff"/>')
    a = lg[..., 3:4]
    ys, xs = y + pad_y, x0 + pad_x
    card[ys:ys + lh, xs:xs + lw, :3] = card[ys:ys + lh, xs:xs + lw, :3] * (1 - a) + lg[..., :3] * a
    return card


def step_card(i: int, x: int, y: int, w: int, h: int, check: bool = False) -> str:
    num = f'<circle cx="{x + 70}" cy="{y + h / 2}" r="38" fill="{POINT}"/>' \
          f'<text x="{x + 70}" y="{y + h / 2 + 15}" text-anchor="middle" font-family="{FONT}" font-weight="900" font-size="44" fill="#fff">{i + 1}</text>'
    if check:
        num = f'<circle cx="{x + 70}" cy="{y + h / 2}" r="38" fill="{ACCENT}"/>' \
              f'<path d="M{x + 52},{y + h / 2} l12,13 l24,-26" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'
    return (f'<rect x="{x}" y="{y + 8}" width="{w}" height="{h}" rx="26" fill="#000" opacity="0.18"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="26" fill="#ffffff"/>{num}'
            f'<text x="{x + 130}" y="{y + h / 2 + 16}" font-family="{FONT}" font-weight="800" font-size="46" fill="#1B2559">{STEPS[i]}</text>')


def ease(p):
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** 3


def animate(out: Path, dur: float, layers: list[tuple[np.ndarray, float]]):
    """layers: (RGBA 레이어, 나타나는 시각). 0.45초 동안 페이드 + 아래에서 살짝 올라옴."""
    bg = _background(W, H, ScreenFxSettings(background=BG)).astype(np.float32) / 255.0
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
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
        # 끝 0.3초 페이드 아웃(장면 전환)
        k = min(1.0, (dur - t) / 0.3)
        img = img * k + bg * (1 - k) if k < 1 else img
        proc.stdin.write((img * 255).astype(np.uint8).tobytes())
    proc.stdin.close(); proc.wait()


GAP = 0.45
I1, I2 = 0.8, 0.8 + DUR["I1"] + GAP
INTRO_LEN = round(I2 + DUR["I2"] + 0.7, 2)
cw, chh, cy = 760, 130, 900
cx = [(W - 3 * cw - 2 * 50) // 2 + i * (cw + 50) for i in range(3)]
if not (here / "intro.mp4").exists():
    title = svg_layer(f'<text x="{W / 2}" y="740" text-anchor="middle" font-family="{FONT}" font-weight="900" '
                      f'font-size="104" fill="#ffffff">관장님 회원가입, <tspan fill="#FFD84D">3단계</tspan>면 끝!</text>')
    layers = [(logo_layer(330), 0.15), (title, 0.6)]
    layers += [(svg_layer(step_card(i, cx[i], cy, cw, chh)), I2 + 1.2 + i * 0.9) for i in range(3)]
    animate(here / "intro.mp4", INTRO_LEN, layers)

O1 = 0.5
O2 = O1 + DUR["O1"] + 0.9
OUTRO_LEN = round(O2 + DUR["O2"] + 1.0, 2)
if not (here / "outro.mp4").exists():
    head = svg_layer(f'<text x="{W / 2}" y="420" text-anchor="middle" font-family="{FONT}" font-weight="900" '
                     f'font-size="92" fill="#ffffff">오늘 배운 세 단계</text>')
    layers = [(head, 0.1)]
    layers += [(svg_layer(step_card(i, cx[i], 560, cw, chh)), 0.2)
               for i in range(3)]
    layers += [(svg_layer(step_card(i, cx[i], 560, cw, chh, check=True)), O1 + 0.9 + i * 0.55) for i in range(3)]
    nxt = svg_layer(f'<rect x="{W / 2 - 520}" y="830" width="1040" height="120" rx="60" fill="#ffffff" opacity="0.14"/>'
                    f'<text x="{W / 2}" y="910" text-anchor="middle" font-family="{FONT}" font-weight="800" '
                    f'font-size="58" fill="#ffffff">다음 편 ▶ 2편: 로그인하기</text>')
    layers += [(nxt, O2), (logo_layer(1060, 1.1), O2 + 0.6)]
    animate(here / "outro.mp4", OUTRO_LEN, layers)


# ───────── 3) 자막·단계 표시 (ASS) ─────────
def ts(t):
    cs = int(round(t * 100)); h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_color(hex_, alpha=0):
    h = hex_.lstrip("#"); return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}"


body_lines = [(ln["key"], tb(ln["t"]) + INTRO_LEN) for ln in log["lines"]]
placed = [("I1", I1), ("I2", I2)] + body_lines + \
         [("O1", INTRO_LEN + BODY_LEN + O1), ("O2", INTRO_LEN + BODY_LEN + O2)]
TOTAL = INTRO_LEN + BODY_LEN + OUTRO_LEN

ev = []
for k, t in placed:
    ev.append(f"Dialogue: 0,{ts(t)},{ts(t + DUR[k] + 0.25)},Sub,,0,0,0,,{TXT[k].replace('태권 월드', '태권월드')}")
st = [tb(mk["step1"]), tb(mk["step2"]), tb(mk["step3"]), BODY_LEN]
for i in range(3):
    ev.append(f"Dialogue: 1,{ts(INTRO_LEN + st[i])},{ts(INTRO_LEN + st[i + 1])},Step,,0,0,0,,"
              f"{{\\fad(250,200)}}  {i + 1}/3  {STEPS[i]}  ")
r0 = tb(mk["reassure"]) + INTRO_LEN
ev.append(f"Dialogue: 1,{ts(r0)},{ts(r0 + DUR['F7'] + 0.6)},Bubble,,0,0,0,,{{\\fad(200,200)}}  처음 한 번만!  ")
ass = "\n".join([
    "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
    "[V4+ Styles]",
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
    "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    # 자막: 흰 글씨 + 반투명 남청 상자 (어떤 화면 위에서도 읽힘)
    f"Style: Sub,{FONT} ExtraBold,60,&H00FFFFFF,&H00FFFFFF,{ass_color('#141B40', 0x30)},{ass_color('#141B40', 0x30)},-1,0,0,0,100,100,0,0,3,14,0,2,200,200,46,1",
    f"Style: Step,{FONT} ExtraBold,40,&H00FFFFFF,&H00FFFFFF,{ass_color(POINT)},{ass_color(POINT)},-1,0,0,0,100,100,0,0,3,10,0,7,150,0,22,1",
    f"Style: Bubble,{FONT} ExtraBold,56,&H00FFFFFF,&H00FFFFFF,{ass_color(ACCENT)},{ass_color(ACCENT)},-1,0,0,0,100,100,0,0,3,16,0,2,0,0,170,1",
    "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *ev, ""])
(here / "ep1.ass").write_text(ass, encoding="utf-8")
srt = []
for n, (k, t) in enumerate(placed, 1):
    a, b = t, t + DUR[k] + 0.25
    f = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(round(x % 1 * 1000)) % 1000:03d}"
    srt += [str(n), f"{f(a)} --> {f(b)}", TXT[k].replace("태권 월드", "태권월드"), ""]
(here / "태권월드_1편_관장님회원가입.srt").write_text("\n".join(srt), encoding="utf-8")

# ───────── 4) 나레이션 트랙 ─────────
build_track([(t, NAR[k][1]) for k, t in placed], TOTAL, here / "narration.wav")

# ───────── 5) 최종 합성 ─────────
FINAL = here / "태권월드_1편_관장님회원가입_1440p60.mp4"
run("-i", str(here / "intro.mp4"), "-i", str(here / "body.mp4"), "-i", str(here / "outro.mp4"), "-i", str(here / "narration.wav"),
    "-filter_complex", f"[0:v][1:v][2:v]concat=n=3:v=1:a=0,fps={FPS},ass=filename='{here / 'ep1.ass'}'[v]",
    "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
    "-g", str(FPS * 2), "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
    "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{TOTAL:.3f}", str(FINAL))
run("-i", str(FINAL), "-vf", "scale=1920:1080:flags=lanczos,fps=30", "-c:v", "libx264", "-preset", "medium",
    "-b:v", "16M", "-maxrate", "20M", "-bufsize", "32M", "-pix_fmt", "yuv420p", "-g", "60",
    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
    "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", str(here / "태권월드_1편_관장님회원가입_1080p30.mp4"))
chap = [("인트로", 0), ("1단계 가입 화면 찾기", INTRO_LEN + st[0]), ("2단계 정보 입력하기", INTRO_LEN + st[1]),
        ("3단계 약관 동의하고 등록", INTRO_LEN + st[2]), ("마무리", INTRO_LEN + BODY_LEN)]
(here / "챕터.txt").write_text("\n".join(f"{int(t // 60)}:{int(t % 60):02d} {n}" for n, t in chap), encoding="utf-8")
print(f"완성: 인트로 {INTRO_LEN:.1f}s + 본편 {BODY_LEN:.1f}s + 아웃트로 {OUTRO_LEN:.1f}s = {TOTAL:.1f}s")
