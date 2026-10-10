"""내보내기 (DESIGN.md 8절): 올릴 곳을 고르면 필요한 파일과 '복사해 붙여 넣을 글'을 올릴 곳별 폴더에 정리하고, 규격을 자동 검사한다.

- 연결표·규격은 presets/platforms.yaml 하나에 있다(플랫폼이 바꾸면 그 파일만).
- 원본은 만들기 결과(1440p60, 1080p30, srt, timeline.json, 본편·인트로·아웃트로 조각). 원본은 바꾸지 않는다(1편 재현 검사 영향 없음).
- 같은 종류 영상(세로 등)은 한 번만 만들어 여러 올릴 곳 폴더에 나눠 둔다(가능하면 하드 링크).
- 올리기는 사람이 한다(자동 업로드 없음). 노출·인용은 보장할 수 없다 — 조건을 빠짐없이 갖추는 것까지.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlencode, urlparse

import numpy as np
import yaml

from ..ffmpeg_utils import FFMPEG, FFPROBE
from ..screenfx import ScreenFxSettings, _background
from . import sentences as T
from .compose import FONTS, ass_color, ff_path, render_svg, srt_time, ts
from .scenario import Scenario

PLATFORMS = Path(__file__).parent / "presets" / "platforms.yaml"
VERSION = "1"        # 만드는 방식을 바꾸면 올린다 → 예전에 만들어 둔 변형을 다시 만든다


def load_platforms() -> dict:
    return yaml.safe_load(PLATFORMS.read_text(encoding="utf-8"))


def run(*a):
    subprocess.run([FFMPEG, "-v", "error", "-y", *a], check=True)


def slugify(s: str) -> str:
    s = re.sub(r"[\[\]{}()<>:;\"'|?*/\\.,!~`@#$%^&=+]", " ", s)
    return re.sub(r"\s+", "-", s.strip()).strip("-")


def place(src: Path, dst: Path) -> Path:
    """같은 파일을 여러 폴더에: 하드 링크, 안 되면 복사."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
    return dst


def utm(url: str, source: str, campaign: str) -> str:
    if "?" not in url and urlparse(url).path == "":
        url += "/"
    sep = "&" if "?" in url else "?"
    return url + sep + urlencode({"utm_source": source, "utm_medium": "video", "utm_campaign": campaign})


def iso_dur(sec: float) -> str:
    sec = int(round(sec))
    return f"PT{sec // 60}M{sec % 60}S" if sec >= 60 else f"PT{sec}S"


class Exporter:
    def __init__(self, sc: Scenario, work: Path, log=print, site: str = ""):
        self.sc, self.work, self.say = sc, work, log
        self.P = load_platforms()
        base = sc.file_name
        self.final = work / f"{base}_1440p60.mp4"
        self.v1080 = work / f"{base}_1080p30.mp4"
        if not self.final.exists():
            raise ValueError("먼저 영상을 만들어 주세요(최종본이 없어요).")
        if not (work / "timeline.json").exists():          # 7단계 전에 만든 영상
            raise ValueError("이 영상은 예전 방식으로 만들어져 시간표가 없어요. [문장 고치고 다시 만들기]로 한 번 다시 만들어 주세요"
                             "(녹화는 다시 하지 않아요).")
        self.tl = json.loads((work / "timeline.json").read_text(encoding="utf-8"))
        self.out = work / "내보내기"
        self.cache = work / "variants"
        self.cache.mkdir(exist_ok=True)
        self.topic = T.topic_words(sc.title_plain.split(",")[0])
        u = urlparse(sc.login_url or sc.url)
        self.site = site or f"{u.scheme}://{u.netloc}"
        latin = sc.brand.key if sc.brand.key and sc.brand.key != "basic" else (u.netloc.split(":")[0].split(".")[-2]
                                                                               if u.netloc.count(".") else u.netloc.split(":")[0])
        self.slug = slugify(f"{latin} {self.topic} 방법")              # taekwonworld-관장님-회원가입-방법
        self.n_steps = len(sc.steps)
        # 링크 꼬리표의 캠페인 이름은 영문만(한글은 %EA%B4%80… 처럼 길어져 설명란이 지저분해짐)
        self.campaign = f"{re.sub(r'[^a-z0-9]+', '-', latin.lower()).strip('-') or 'tutorial'}-{dt.date.today():%Y%m%d}"
        self.made: dict[str, dict[str, list[str]]] = {}               # 올릴 곳 → 항목 → 파일들
        self.texts: dict[str, dict[str, str]] = {}
        self.key = f"{self.final.stat().st_mtime}|{VERSION}"

    # ── 공통 재료 ──
    def _cached(self, name: str, make) -> Path:
        f = self.cache / name
        kp = self.cache / (name + ".key")
        if f.exists() and kp.exists() and kp.read_text() == self.key:
            return f
        make(f)
        kp.write_text(self.key)
        return f

    def meta_args(self, extra_title: str = "") -> list[str]:
        b = self.sc.brand
        year = dt.date.today().year
        title = self.sc.title_plain + (f" ({extra_title})" if extra_title else "")
        desc = f"{self.topic} 방법을 {T.count_word(self.n_steps)} 단계로 알려 드려요. {self.site}"
        return ["-metadata", f"title={title}", "-metadata", f"comment={desc}", "-metadata", f"description={desc}",
                "-metadata", f"artist={b.name or urlparse(self.site).netloc}", "-metadata", f"copyright=© {year} {b.name or ''}".strip(),
                "-metadata", "language=kor", "-metadata:s:a:0", "language=kor", "-metadata:s:v:0", "language=kor"]

    def with_meta(self, src: Path, dst: Path, extra: str = "") -> Path:
        run("-i", str(src), "-map", "0", "-c", "copy", *self.meta_args(extra), "-movflags", "+faststart", str(dst))
        return dst

    def frame(self, src: Path, t: float, out: Path, size=None) -> Path:
        vf = ["-vf", f"scale={size[0]}:{size[1]}:flags=lanczos"] if size else []
        run("-ss", f"{max(0, t):.3f}", "-i", str(src), "-frames:v", "1", *vf, "-q:v", "2", str(out))
        return out

    # ── 영상 종류 ──
    def v_1440(self) -> Path:
        return self._cached(f"{self.slug}.mp4", lambda f: self.with_meta(self.final, f))

    def v_youtube(self) -> Path:
        """유튜브: 끝에 '최종 화면' 자리 8초(브랜드 배경만, 유튜브 스튜디오에서 다음 영상·구독 요소를 올림)."""
        def make(f):
            bg = self.cache / "endscreen.png"
            self._bg_png(2560, 1440, bg, text="봐 주셔서 고맙습니다")
            # 최종본은 다시 인코딩하지 않는다: 8초 꼬리만 같은 규격으로 만들어 그대로 이어 붙임(1440p60 재인코딩은 10분 넘게 걸림)
            j = self.probe(self.final)
            v = next(s for s in j["streams"] if s["codec_type"] == "video")
            num, den = v["r_frame_rate"].split("/")
            fps = round(float(num) / float(den))
            tail = self.cache / "endscreen.mp4"
            run("-loop", "1", "-framerate", str(fps), "-t", "8", "-i", str(bg), "-f", "lavfi", "-t", "8",
                "-i", "anullsrc=r=48000:cl=stereo", "-vf", f"scale={v['width']}:{v['height']},format=yuv420p",
                "-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast", "-crf", "18", "-r", str(fps),
                "-video_track_timescale", str(fps * 256), "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2", "-shortest", str(tail))
            lst = self.cache / "endscreen.txt"
            lst.write_text(f"file '{self.final.resolve().as_posix()}'\nfile '{tail.resolve().as_posix()}'\n", encoding="utf-8")
            run("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", *self.meta_args(), "-movflags", "+faststart", str(f))
            d = float(self.probe(f)["format"]["duration"])
            if abs(d - (float(j["format"]["duration"]) + 8)) > 0.3:      # 이어 붙이기가 어긋나면 안전하게 다시 인코딩
                self.say("[내보내기] 이어 붙이기 길이가 맞지 않아 다시 인코딩해요(오래 걸려요).")
                run("-i", str(self.final), "-i", str(tail), "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                    "-g", "120", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    "-c:a", "aac", "-b:a", "320k", "-ar", "48000", *self.meta_args(), "-movflags", "+faststart", str(f))
        return self._cached(f"{self.slug}-유튜브.mp4", make)

    def v_1080(self) -> Path:
        src = self.v1080 if self.v1080.exists() else self.final
        if src == self.final:
            def make(f):
                run("-i", str(self.final), "-vf", "scale=1920:1080:flags=lanczos,fps=30", "-c:v", "libx264", "-preset", "medium",
                    "-b:v", "16M", "-maxrate", "20M", "-bufsize", "32M", "-pix_fmt", "yuv420p", "-g", "60",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    "-c:a", "aac", "-b:a", "320k", *self.meta_args(), "-movflags", "+faststart", str(f))
            return self._cached(f"{self.slug}-1080p.mp4", make)
        return self._cached(f"{self.slug}-1080p.mp4", lambda f: self.with_meta(src, f))

    def v_short16(self) -> Path:
        """본편만(인트로·아웃트로 없이) 가로 1080p — X 같은 짧은 곳."""
        a, z = self.tl["intro"], self.tl["intro"] + self.tl["body"]

        def make(f):
            run("-ss", f"{a:.3f}", "-to", f"{z:.3f}", "-i", str(self.v_1080()), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", *self.meta_args("짧은 버전"), "-movflags", "+faststart", str(f))
        return self._cached(f"{self.slug}-짧은버전.mp4", make)

    LAYOUT = {   # 캔버스, 영상 위치(y), 제목 y, 단계 표시 y, 자막 y, 오른쪽 여백(세로는 버튼 자리)
        "세로": dict(W=1080, H=1920, vy=600, ty=300, sy=528, uy=1260, mr=170),
        "4대5": dict(W=1080, H=1350, vy=270, ty=70, sy=198, uy=905, mr=70),
        "1대1": dict(W=1080, H=1080, vy=190, ty=36, sy=128, uy=820, mr=70),
    }

    def _bg_png(self, w: int, h: int, out: Path, text: str = "") -> Path:
        import cv2
        bg = _background(w, h, ScreenFxSettings(background=tuple(self.sc.brand.background)))
        if text:
            lay = render_svg(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><text x="{w / 2}" y="{h * 0.2}" '
                             f'text-anchor="middle" font-family="{self.sc.brand.font}" font-weight="800" font-size="{int(h * 0.05)}" '
                             f'fill="#ffffff" opacity="0.9">{html.escape(text)}</text></svg>', w, h)
            L = cv2.imdecode(np.frombuffer(lay, np.uint8), cv2.IMREAD_UNCHANGED).astype(np.float32) / 255
            a = L[..., 3:4]
            bg = (bg.astype(np.float32) * (1 - a) + L[..., :3] * 255 * a).astype(np.uint8)
        cv2.imwrite(str(out), bg)
        return out

    def _ass(self, kind: str, lines, steps, bubbles, extra=(), title_from: float = 0) -> Path:
        L = self.LAYOUT[kind]
        W, H = L["W"], L["H"]
        b, F = self.sc.brand, self.sc.brand.font
        hl = ass_color(b.highlight)
        title = html.unescape(self.sc.title).replace("[", "{\\c" + hl + "}").replace("]", "{\\c&H00FFFFFF}")
        ev = [f"Dialogue: 0,{ts(title_from)},{ts(99999)},Title,,0,0,0,,{{\\fad(300,0)}}{title}"]
        ev += [f"Dialogue: 0,{ts(a)},{ts(a + d)},Sub,,0,0,0,,{t}" for a, d, t in lines]
        ev += [f"Dialogue: 1,{ts(a)},{ts(z)},Step,,0,0,0,,{{\\fad(250,200)}}  {i}/{len(self.sc.steps)}  {n}  " for i, (a, z, n) in steps]
        ev += [f"Dialogue: 1,{ts(a)},{ts(a + d)},Bubble,,0,0,0,,{{\\fad(200,200)}}  {t}  " for a, d, t in bubbles]
        ev += [f"Dialogue: 2,{ts(a)},{ts(a + d)},Hook,,0,0,0,,{t}" for a, d, t in extra]
        sub_bg = ass_color("#141B40", 0x30)
        txt = "\n".join([
            "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Title,{F} Black,{68 if kind == '세로' else 54},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,0,3,8,70,{L['mr']},{L['ty']},1",
            f"Style: Sub,{F} ExtraBold,{60 if kind == '세로' else 46},&H00FFFFFF,&H00FFFFFF,{sub_bg},{sub_bg},-1,0,0,0,100,100,0,0,3,14,0,8,70,{L['mr']},{L['uy']},1",
            f"Style: Step,{F} ExtraBold,{38 if kind == '세로' else 32},&H00FFFFFF,&H00FFFFFF,{ass_color(b.point)},{ass_color(b.point)},-1,0,0,0,100,100,0,0,3,10,0,7,40,0,{L['sy']},1",
            f"Style: Bubble,{F} ExtraBold,{50 if kind == '세로' else 40},&H00FFFFFF,&H00FFFFFF,{ass_color(b.accent)},{ass_color(b.accent)},-1,0,0,0,100,100,0,0,3,14,0,8,0,0,{L['vy'] + 470},1",
            f"Style: Hook,{F} Black,{62 if kind == '세로' else 50},&H00FFFFFF,&H00FFFFFF,{ass_color(b.accent)},{ass_color(b.accent)},-1,0,0,0,100,100,0,0,3,18,0,8,70,{L['mr']},{L['uy']},1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *ev, ""])
        p = self.cache / f"{kind}.ass"
        p.write_text(txt, encoding="utf-8")
        return p

    def _canvas(self, kind: str, video: Path, audio_args: list[str], ass: Path, out: Path, total: float):
        L = self.LAYOUT[kind]
        bg = self._bg_png(L["W"], L["H"], self.cache / f"bg_{kind}.png")
        run("-loop", "1", "-i", str(bg), "-i", str(video), *audio_args,
            "-filter_complex", f"[1:v]fps=30,scale=1080:608:flags=lanczos[v];[0:v][v]overlay=0:{L['vy']}:shortest=1,fps=30,"
                               f"ass=filename='{ff_path(ass)}':fontsdir='{ff_path(FONTS)}',format=yuv420p[o]",
            "-map", "[o]", "-map", "2:a", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-g", "60", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", *self.meta_args(kind), "-movflags", "+faststart", str(out))

    def _clean_full(self) -> Path:
        """자막을 새기지 않은 전체(인트로+본편+아웃트로) 30fps — 4:5·1:1 의 재료."""
        def make(f):
            w = self.work
            run("-i", str(w / "intro.mp4"), "-i", str(w / "body.mp4"), "-i", str(w / "outro.mp4"),
                "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,fps=30,scale=1080:608:flags=lanczos[v]",
                "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
                "-t", f"{self.tl['total']:.3f}", str(f))
        return self._cached("clean_full.mp4", make)

    def v_full_canvas(self, kind: str) -> Path:
        def make(f):
            tl = self.tl
            lines = [(x["t"], x["dur"], x["text"]) for x in tl["lines"]]
            steps = [(i + 1, (s["start"], s["end"], s["name"])) for i, s in enumerate(tl["steps"])]
            bubbles = [(x["t"], x["dur"], x["text"]) for x in tl["bubbles"]]
            ass = self._ass(kind, lines, steps, bubbles, title_from=tl["intro"])     # 인트로에는 제목이 이미 있음
            self._canvas(kind, self._clean_full(), ["-i", str(self.work / "narration.wav")], ass, f, tl["total"])
        return self._cached(f"{self.slug}-{kind}.mp4", make)

    def v_vertical(self) -> Path:
        """짧은 세로: 결과 화면 2초 → 본편 → 연결 안내 2초. 끝과 처음이 같은 결과 화면이라 반복 재생이 이어진다."""
        HOOK, END = 2.0, 2.0

        def make(f):
            tl, w = self.tl, self.work
            body_len = tl["body"]
            last = self.frame(w / "body.mp4", body_len - 0.1, self.cache / "result.jpg")
            src = self.cache / "vertical_src.mp4"
            run("-loop", "1", "-t", f"{HOOK}", "-i", str(last), "-i", str(w / "body.mp4"), "-loop", "1", "-t", f"{END}", "-i", str(last),
                "-filter_complex", "[0:v]fps=30,scale=1080:608,setsar=1[a];[1:v]fps=30,scale=1080:608,setsar=1[b];"
                                   "[2:v]fps=30,scale=1080:608,setsar=1[c];[a][b][c]concat=n=3:v=1:a=0[v]",
                "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", str(src))
            i0 = tl["intro"]
            sh = lambda t: t - i0 + HOOK
            lines = [(sh(x["t"]), x["dur"], x["text"]) for x in tl["lines"] if i0 <= x["t"] < i0 + body_len]
            steps = [(i + 1, (sh(s["start"]), sh(s["end"]), s["name"])) for i, s in enumerate(tl["steps"])]
            bubbles = [(sh(x["t"]), x["dur"], x["text"]) for x in tl["bubbles"]]
            total = HOOK + body_len + END
            hook = [(0, HOOK, f"이렇게 끝나요 · {T.count_word(self.n_steps)} 단계로 따라 해 보세요"),
                    (HOOK + body_len, END, "전체 영상은 설명란 링크에서 볼 수 있어요")]
            ass = self._ass("세로", lines, steps, bubbles, hook)
            audio = ["-i", str(w / "narration.wav")]
            # 소리: 본편 구간만 잘라 2초 뒤에 놓는다
            sound = self.cache / "vertical.wav"
            run("-i", str(w / "narration.wav"), "-af", f"atrim={i0:.3f}:{i0 + body_len:.3f},asetpts=PTS-STARTPTS,"
                f"adelay={int(HOOK * 1000)}|{int(HOOK * 1000)},apad=whole_dur={total:.3f}", "-ar", "48000", str(sound))
            self._canvas("세로", src, ["-i", str(sound)], ass, f, total)
        return self._cached(f"{self.slug}-세로.mp4", make)

    def v_web(self) -> tuple[Path, Path]:
        """내 웹사이트: AV1(작고 선명) + H.264(예비). 1080p30."""
        src = self.v_1080()

        def av1(f):
            run("-i", str(src), "-c:v", "libsvtav1", "-preset", "8", "-crf", "35", "-g", "240", "-pix_fmt", "yuv420p",
                "-svtav1-params", "tune=0", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", *self.meta_args(), "-movflags", "+faststart", str(f))

        def h264(f):
            run("-i", str(src), "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p", "-g", "60",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", *self.meta_args(), "-movflags", "+faststart", str(f))
        return self._cached(f"{self.slug}-av1.mp4", av1), self._cached(f"{self.slug}-h264.mp4", h264)

    def scene_times(self) -> list[tuple[int, str, float, float]]:
        """본편 장면들: (번호, 문장, 시작, 끝) — 최종본 시각."""
        tl = self.tl
        body = [x for x in tl["lines"] if tl["intro"] <= x["t"] < tl["intro"] + tl["body"]]
        out = []
        for i, x in enumerate(body):
            z = body[i + 1]["t"] if i + 1 < len(body) else tl["intro"] + tl["body"]
            out.append((i + 1, x["text"], x["t"], z))
        return out

    def scene_shots(self) -> list[tuple[int, str, Path]]:
        """단계별 글·블로그·썸네일용 화면 캡처(1280x720): 장면마다 동작이 보이는 순간. 자막 없는 본편에서 뽑는다."""
        shots, i0 = [], self.tl["intro"]
        for no, text, a, z in self.scene_times():
            f = self.cache / f"장면{no:02d}.jpg"
            kp = self.cache / f"장면{no:02d}.jpg.key"
            if not (f.exists() and kp.exists() and kp.read_text() == self.key):
                self.frame(self.work / "body.mp4", min(z - 0.3, a + 2.2) - i0, f, (1280, 720))
                kp.write_text(self.key)
            shots.append((no, text, f))
        return shots

    def clips(self) -> list[tuple[Path, Path]]:
        out = []
        for no, text, a, z in self.scene_times():
            mp4 = self.cache / f"장면{no:02d}.mp4"
            gif = self.cache / f"장면{no:02d}.gif"
            if not (mp4.exists() and gif.exists() and (self.cache / f"장면{no:02d}.mp4.key").exists()
                    and (self.cache / f"장면{no:02d}.mp4.key").read_text() == self.key):
                d = min(z - a, 20)
                run("-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", str(self.v_1080()), "-vf", "scale=1280:720:flags=lanczos",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
                    "-color_trc", "bt709", "-colorspace", "bt709", "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                    "-movflags", "+faststart", str(mp4))
                run("-ss", f"{a:.3f}", "-t", f"{min(d, 8):.3f}", "-i", str(self.v_1080()), "-filter_complex",
                    "fps=8,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer",
                    str(gif))
                (self.cache / f"장면{no:02d}.mp4.key").write_text(self.key)
            out.append((mp4, gif))
        return out

    # ── 그림 ──
    def _svg_png(self, w, h, inner) -> "np.ndarray":
        import cv2
        png = render_svg(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">{inner}</svg>', w, h)
        return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)

    def _compose_img(self, w, h, shot: Path | None, shot_box, inner_svg: str, out: Path, quality=90):
        """배경(브랜드) + 화면 사진(둥근 모서리) + 글자(SVG)."""
        from PIL import Image, ImageDraw
        bg = Image.open(self._bg_png(w, h, self.cache / f"bg_{w}x{h}.png")).convert("RGB")
        if shot:
            x, y, sw, shh = shot_box
            im = Image.open(shot).convert("RGB").resize((sw, shh), Image.LANCZOS)
            m = Image.new("L", (sw, shh), 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, sw - 1, shh - 1), radius=max(12, sw // 40), fill=255)
            shadow = Image.new("L", (sw, shh), 0)
            ImageDraw.Draw(shadow).rounded_rectangle((0, 0, sw - 1, shh - 1), radius=max(12, sw // 40), fill=90)
            bg.paste((0, 0, 0), (x + 8, y + 12), shadow)
            bg.paste(im, (x, y), m)
        lay = self._svg_png(w, h, inner_svg)
        L = Image.fromarray(lay[..., [2, 1, 0, 3]])
        bg.paste(L, (0, 0), L)
        out.parent.mkdir(parents=True, exist_ok=True)
        bg.save(out, quality=quality, optimize=True)
        return out

    def _title_svg(self, x, y, size, width_chars, anchor="start", color="#ffffff"):
        """제목 두 줄까지. [ ] 안은 강조색."""
        t = self.sc.title
        words, lines, cur = t.split(" "), [], ""
        for wd in words:
            if len((cur + " " + wd).replace("[", "").replace("]", "")) > width_chars and cur:
                lines.append(cur); cur = wd
            else:
                cur = (cur + " " + wd).strip()
        lines.append(cur)
        hl = self.sc.brand.highlight
        out = ""
        for i, ln in enumerate(lines[:3]):
            s = html.escape(ln).replace("[", f'<tspan fill="{hl}">').replace("]", "</tspan>")
            if s.count("<tspan") > s.count("</tspan>"):
                s += "</tspan>"
            out += (f'<text x="{x}" y="{y + i * size * 1.22}" text-anchor="{anchor}" font-family="{self.sc.brand.font}" '
                    f'font-weight="900" font-size="{size}" fill="{color}">{s}</text>')
        return out

    def thumbnails(self) -> list[Path]:
        """유튜브 썸네일 3개(1280x720, 2MB 이하): ① 인트로 제목 화면 ② 제목 + 핵심 화면 ③ 결과 화면 + 'N단계면 끝!'"""
        shots = self.scene_shots()
        mid = shots[len(shots) // 2][2] if shots else None
        res = self.frame(self.work / "body.mp4", self.tl["body"] - 0.1, self.cache / "result.jpg")
        t1 = self.frame(self.final, min(self.tl["intro"] - 0.6, 8.0), self.cache / "썸네일1.jpg", (1280, 720))
        t2 = self._compose_img(1280, 720, mid, (560, 150, 680, 383), self._title_svg(48, 250, 64, 9), self.cache / "썸네일2.jpg")
        band = (f'<rect x="0" y="560" width="1280" height="160" fill="#000" opacity="0.55"/>'
                f'<text x="640" y="668" text-anchor="middle" font-family="{self.sc.brand.font}" font-weight="900" font-size="84" '
                f'fill="#ffffff"><tspan fill="{self.sc.brand.highlight}">{self.n_steps}단계</tspan>면 끝!</text>')
        t3 = self._compose_img(1280, 720, res, (0, 0, 1280, 720), band, self.cache / "썸네일3.jpg")
        return [t1, t2, t3]

    def og_image(self) -> Path:
        shots = self.scene_shots()
        mid = shots[len(shots) // 2][2] if shots else None
        return self._compose_img(1200, 630, mid, (560, 130, 600, 338), self._title_svg(44, 230, 54, 9), self.cache / "대표이미지.jpg")

    def pin_image(self) -> Path:
        shots = self.scene_shots()
        mid = shots[len(shots) // 2][2] if shots else None
        return self._compose_img(1000, 1500, mid, (60, 640, 880, 495), self._title_svg(500, 260, 76, 10, "middle"), self.cache / "핀이미지.jpg")

    def play_thumb(self) -> Path:
        t = self.thumbnails()[2]
        btn = ('<circle cx="640" cy="320" r="92" fill="#000" opacity="0.55"/>'
               '<path d="M610,262 L610,378 L708,320 Z" fill="#ffffff"/>')
        return self._compose_img(1280, 720, t, (0, 0, 1280, 720), btn, self.cache / "재생버튼썸네일.jpg")

    def cover(self) -> Path:
        return self.frame(self.v_vertical(), 0.6, self.cache / "세로커버.jpg")

    def posters(self) -> tuple[Path, Path, Path]:
        jpg = self.frame(self.final, min(self.tl["intro"] - 0.6, 8.0), self.cache / "포스터.jpg", (1920, 1080))
        webp = self.cache / "포스터.webp"
        run("-i", str(jpg), "-c:v", "libwebp", "-quality", "80", str(webp))
        avif = self.cache / "포스터.avif"
        run("-i", str(jpg), "-c:v", "libaom-av1", "-still-picture", "1", "-crf", "32", "-cpu-used", "6", "-pix_fmt", "yuv420p", str(avif))
        return avif, webp, jpg

    # ── 글 ──
    def hashtags(self, limit: int | None = None) -> list[str]:
        b = self.sc.brand
        base = [b.name, self.topic.replace(" ", ""), f"{(b.name or '')}사용법" if b.name else "사용법", "사용법", "따라하기"]
        base += [s.replace(" ", "") for s in self.sc.steps]
        base += list(getattr(b, "hashtags", []) or [])
        out = []
        for h in base:
            h = re.sub(r"[^\w가-힣]", "", h or "")
            if h and h not in out:
                out.append(h)
        out = ["#" + h for h in out]
        return out[:limit] if limit else out

    def steps_text(self) -> str:
        tl, sc = self.tl, self.sc
        out = []
        for i, s in enumerate(tl["steps"]):
            scenes = [x["text"] for x in tl["lines"] if s["start"] - 0.05 <= x["t"] < s["end"]]
            out.append(f"{i + 1}단계 {s['name']}\n" + "\n".join(f"  · {t}" for t in scenes))
        return "\n".join(out)

    def chapters_text(self) -> str:
        return "\n".join(f"{int(c['t'] // 60)}:{int(c['t'] % 60):02d} {c['name']}" for c in self.tl["chapters"])

    def make_texts(self, dest: str) -> dict[str, str]:
        P = self.P["올릴곳"][dest]
        lim = P.get("글", {})
        link = utm(self.site, P.get("utm", dest), self.campaign)
        b = self.sc.brand
        n = T.count_word(self.n_steps)
        tags = self.hashtags(lim.get("해시태그"))
        foot = f"\n\n{b.footer}" if b.footer else ""
        hook = f"{self.topic} 방법을 {n} 단계로 알려 드려요."
        t: dict[str, str] = {}
        if dest == "youtube":
            t["제목"] = f"{self.topic}, 어떻게 하나요? {self.n_steps}단계면 끝! | {b.name}" if b.name else f"{self.topic}, 어떻게 하나요? {self.n_steps}단계면 끝!"
            t["설명"] = (f"{hook}\n\n▶ 따라 하기\n{self.steps_text()}\n\n▶ 챕터\n{self.chapters_text()}\n\n"
                        f"▶ 바로 가기: {link}{foot}\n\n{' '.join(tags[:3])}")
            t["해시태그"] = " ".join(tags)
            t["고정 댓글"] = (f"궁금한 점은 댓글로 남겨 주세요! 바로 가기: {link}"
                           + (f"\n다음 영상: {self.sc.next_episode}" if self.sc.next_episode else ""))
        elif dest in ("shorts", "reels", "tiktok", "naver_clip"):
            t["제목"] = f"{self.topic}, {self.sc.title_plain.split(',')[-1].strip()}"
            cta = "저장해 두고 따라 해 보세요." if dest != "shorts" else "전체 영상은 설명란 링크에서 볼 수 있어요."
            t["설명"] = f"{hook} {cta}\n{link}{foot}\n\n{' '.join(tags)}"
            t["해시태그"] = " ".join(tags)
            if dest in ("reels", "tiktok"):
                t["행동 유도"] = "저장해 두고 따라 해 보세요! 궁금한 점은 댓글로 남겨 주세요."
        elif dest == "naver_blog":
            t["제목"] = f"{self.topic} 방법, {self.n_steps}단계로 쉽게 따라 하기"
            t["해시태그"] = " ".join(tags)
        elif dest in ("ig_feed", "facebook"):
            t["설명"] = f"{hook}\n\n{self.steps_text()}\n\n바로 가기: {link}{foot}\n\n{' '.join(tags)}"
            t["해시태그"] = " ".join(tags)
        elif dest == "linkedin":
            t["설명"] = (f"[{b.name or '사용'} 안내] {self.topic} 방법 ({self.n_steps}단계)\n\n{self.steps_text()}\n\n"
                        f"자세히 보기: {link}{foot}\n\n{' '.join(tags)}")
        elif dest == "x":
            t["설명"] = f"{self.topic}, {self.n_steps}단계면 끝! 영상으로 따라 해 보세요 👉 {link}"
        elif dest == "threads":
            t["설명"] = f"{self.topic}, {self.n_steps}단계면 끝! {hook}\n{link} {tags[0] if tags else ''}"
        elif dest == "pinterest":
            t["제목"] = f"{self.topic} 방법 | {self.n_steps}단계 따라 하기"
            t["설명"] = f"{hook} " + " → ".join(self.sc.steps) + f". 영상으로 따라 해 보세요. {link}"
            t["링크"] = link
        elif dest == "web":
            t["제목"] = f"{self.topic} 방법 ({self.n_steps}단계) | {b.name}" if b.name else f"{self.topic} 방법 ({self.n_steps}단계)"
            t["설명"] = f"{self.topic} 방법을 영상과 단계별 사진으로 알려 드려요. " + " → ".join(self.sc.steps) + "."
        elif dest == "mail":
            t["설명"] = f"{self.topic} 방법을 영상으로 정리했어요. 아래 그림을 누르면 영상이 열려요.\n{link}"
        if "링크" not in t and dest not in ("web",):
            t["링크"] = link
        self.texts[dest] = t
        return t

    def write_texts(self, dest: str, folder: Path):
        t = self.texts.get(dest) or self.make_texts(dest)
        body = "\n\n".join(f"[{k}]\n{v}" for k, v in t.items())
        (folder / "글.txt").write_text(body + "\n", encoding="utf-8")

    # ── 웹 묶음 ──
    def web_bundle(self, folder: Path) -> list[str]:
        """웹: 영상(AV1+H.264), 포스터, VTT, 붙여 넣기 코드, 영상 전용 페이지(단계별 글·대본·FAQ·구조화 데이터·OG), 사이트맵, 제출 안내."""
        made = []
        av1, h264 = self.v_web()
        place(av1, folder / av1.name); place(h264, folder / h264.name)
        avif, webp, jpg = self.posters()
        for p in (avif, webp, jpg):
            place(p, folder / f"{self.slug}-포스터{p.suffix}")
        og = place(self.og_image(), folder / f"{self.slug}-대표이미지.jpg")
        vtt = folder / f"{self.slug}.vtt"
        self.srt_to_vtt(self.work / f"{self.sc.file_name}.srt", vtt)
        shots = self.scene_shots()
        img_dir = folder / "장면"
        for no, text, f in shots:
            place(f, img_dir / f"{self.slug}-{no:02d}.jpg")
        made += ["웹AV1", "웹H264", "웹포스터", "자막VTT", "대체텍스트", "오픈그래프"]
        base_url = self.site.rstrip("/") + "/videos"
        page_url = self.site.rstrip("/") + f"/guide/{self.slug}"
        texts = self.texts.get("web") or self.make_texts("web")
        title, desc = texts["제목"], texts["설명"]
        poster_name = f"{self.slug}-포스터"
        embed = (f'<video controls preload="none" poster="{poster_name}.webp" width="1920" height="1080" '
                 f'style="width:100%;height:auto" aria-label="{html.escape(self.sc.title_plain)}">\n'
                 f'  <source src="{av1.name}" type=\'video/mp4; codecs="av01.0.08M.08"\'>\n'
                 f'  <source src="{h264.name}" type="video/mp4">\n'
                 f'  <track kind="captions" src="{vtt.name}" srclang="ko" label="한국어" default>\n</video>')
        (folder / "붙여넣기코드.html").write_text(
            "<!-- 영상 파일·포스터·자막을 같은 폴더에 올리고 이 코드를 붙여 넣으세요. 누르기 전에는 영상을 내려받지 않아요(preload=none). -->\n"
            + embed + "\n", encoding="utf-8")
        made += ["붙여넣기코드", "누르기전안받기"]
        # 구조화 데이터
        upload = dt.date.today().isoformat()
        chapters = self.tl["chapters"]
        clips = [{"@type": "Clip", "name": c["name"], "startOffset": int(c["t"]),
                  "endOffset": int(chapters[i + 1]["t"] if i + 1 < len(chapters) else self.tl["total"]),
                  "url": f"{page_url}?t={int(c['t'])}"} for i, c in enumerate(chapters)]
        video_ld = {"@context": "https://schema.org", "@type": "VideoObject", "name": title, "description": desc,
                    "thumbnailUrl": [f"{base_url}/{poster_name}.jpg", f"{base_url}/{self.slug}-대표이미지.jpg"],
                    "uploadDate": upload, "duration": iso_dur(self.tl["total"]), "contentUrl": f"{base_url}/{h264.name}",
                    "inLanguage": "ko", "hasPart": clips,
                    "potentialAction": {"@type": "SeekToAction", "target": f"{page_url}?t={{seek_to_second_number}}",
                                        "startOffset-input": "required name=seek_to_second_number"}}
        steps_ld = []
        for i, s in enumerate(self.tl["steps"]):
            scenes = [x for x in self.scene_times() if s["start"] - 0.05 <= x[2] < s["end"]]
            steps_ld.append({"@type": "HowToStep", "position": i + 1, "name": s["name"],
                             "text": " ".join(x[1] for x in scenes),
                             "image": f"{base_url}/장면/{self.slug}-{scenes[0][0]:02d}.jpg" if scenes else None,
                             "url": f"{page_url}?t={int(s['start'])}"})
        howto_ld = {"@context": "https://schema.org", "@type": "HowTo", "name": title, "description": desc,
                    "totalTime": iso_dur(self.tl["body"]), "step": steps_ld,
                    "video": {"@type": "VideoObject", "name": title, "contentUrl": f"{base_url}/{h264.name}",
                              "thumbnailUrl": f"{base_url}/{poster_name}.jpg", "uploadDate": upload}}
        faq = self.faq()
        faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
        (folder / "구조화데이터.json").write_text(json.dumps([video_ld, howto_ld, faq_ld], ensure_ascii=False, indent=1), encoding="utf-8")
        made += ["구조화데이터", "자주묻는질문"]
        # 페이지 틀
        transcript = "\n".join(f"<p>{html.escape(x['text'])}</p>" for x in self.tl["lines"])
        steps_html = ""
        for i, s in enumerate(self.tl["steps"]):
            scenes = [x for x in self.scene_times() if s["start"] - 0.05 <= x[2] < s["end"]]
            items = "".join(f'<li><img src="장면/{self.slug}-{no:02d}.jpg" alt="{i + 1}단계 {html.escape(s["name"])}: {html.escape(t)}" '
                            f'width="1280" height="720" loading="lazy"><p>{html.escape(t)}</p></li>' for no, t, *_ in scenes)
            steps_html += f'<h2 id="step{i + 1}">{i + 1}단계. {html.escape(s["name"])}</h2>\n<ol>{items}</ol>\n'
        faq_html = "".join(f"<h3>{html.escape(q)}</h3><p>{html.escape(a)}</p>" for q, a in faq)
        og_tags = (f'<meta property="og:type" content="video.other">\n<meta property="og:title" content="{html.escape(title)}">\n'
                   f'<meta property="og:description" content="{html.escape(desc)}">\n'
                   f'<meta property="og:image" content="{base_url}/{self.slug}-대표이미지.jpg">\n'
                   f'<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'
                   f'<meta property="og:url" content="{page_url}">\n<meta property="og:video" content="{base_url}/{h264.name}">\n'
                   f'<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="{html.escape(title)}">\n'
                   f'<meta name="twitter:description" content="{html.escape(desc)}">\n'
                   f'<meta name="twitter:image" content="{base_url}/{self.slug}-대표이미지.jpg">')
        ld = "\n".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in (video_ld, howto_ld, faq_ld))
        page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{page_url}">
{og_tags}
{ld}
<style>body{{font-family:system-ui,sans-serif;max-width:860px;margin:0 auto;padding:16px;line-height:1.7}}img{{max-width:100%;height:auto;border-radius:8px}}ol{{padding-left:20px}}</style>
</head><body>
<h1>{html.escape(self.topic)} 방법은? {self.n_steps}단계면 끝!</h1>
<p><strong>요약:</strong> {html.escape(desc)}</p>
{embed}
{steps_html}
<h2>자주 묻는 질문</h2>{faq_html}
<details><summary>대본 전문</summary>{transcript}</details>
</body></html>
"""
        (folder / "영상페이지.html").write_text(page, encoding="utf-8")
        made += ["단계별글", "대본전문"]
        sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">
  <url><loc>{page_url}</loc>
    <video:video>
      <video:thumbnail_loc>{base_url}/{poster_name}.jpg</video:thumbnail_loc>
      <video:title>{html.escape(title)}</video:title>
      <video:description>{html.escape(desc)}</video:description>
      <video:content_loc>{base_url}/{h264.name}</video:content_loc>
      <video:duration>{int(round(self.tl['total']))}</video:duration>
      <video:publication_date>{upload}</video:publication_date>
    </video:video>
  </url>
</urlset>
"""
        (folder / "영상사이트맵.xml").write_text(sitemap, encoding="utf-8")
        made += ["영상사이트맵"]
        (folder / "검색엔진제출안내.txt").write_text(
            f"1. 이 폴더의 영상·포스터·자막·장면 그림을 웹사이트의 /videos/ 에, 영상페이지.html 을 {page_url} 에 올립니다.\n"
            "   (주소가 다르면 영상페이지.html·구조화데이터.json·영상사이트맵.xml 안의 주소를 함께 바꿔 주세요.)\n"
            "2. 구글 서치 콘솔(https://search.google.com/search-console) → 색인 생성 → Sitemaps 에 영상사이트맵.xml 주소를 제출,\n"
            "   'URL 검사'로 영상 페이지를 색인 요청합니다. 동영상 색인 생성 보고서에서 결과를 확인하세요.\n"
            "3. 네이버 서치어드바이저(https://searchadvisor.naver.com) → 요청 → 사이트맵 제출, 웹 페이지 수집 요청.\n"
            "4. 카카오톡 미리보기는 카카오 공유 디버거(https://developers.kakao.com/tool/debugger/sharing)에 페이지 주소를 넣어\n"
            "   새로 읽게 하면 바로 바뀝니다.\n", encoding="utf-8")
        made += ["검색엔진제출", "카카오미리보기"]
        return made

    def faq(self) -> list[tuple[str, str]]:
        steps = ", ".join(f"{i + 1}단계 {s}" for i, s in enumerate(self.sc.steps))
        name = self.sc.brand.name or urlparse(self.site).netloc
        return [(f"{T.josa(self.topic, '은/는')} 어떻게 하나요?", f"{steps} 순서로 하면 됩니다. 영상에서 화면을 보며 그대로 따라 할 수 있어요."),
                (f"{self.topic}에 시간이 얼마나 걸리나요?", f"영상 기준 약 {max(1, round(self.tl['body'] / 60))}분이면 끝나요."),
                (f"{T.josa(self.topic, '은/는')} 어디에서 하나요?", f"{name}({self.site})에서 할 수 있어요.")]

    @staticmethod
    def srt_to_vtt(srt: Path, vtt: Path):
        txt = srt.read_text(encoding="utf-8").strip()
        txt = re.sub(r"(\d\d:\d\d:\d\d),(\d\d\d)", r"\1.\2", txt)
        vtt.write_text("WEBVTT\n\n" + txt + "\n", encoding="utf-8")

    def blog_bundle(self, folder: Path) -> list[str]:
        shots = self.scene_shots()
        img = folder / "사진"
        rows_html, rows_txt = [], []
        for i, s in enumerate(self.tl["steps"]):
            scenes = [x for x in self.scene_times() if s["start"] - 0.05 <= x[2] < s["end"]]
            rows_html.append(f"<h2>{i + 1}단계. {html.escape(s['name'])}</h2>")
            rows_txt.append(f"\n■ {i + 1}단계. {s['name']}")
            for no, t, *_ in scenes:
                f = place(dict((n, p) for n, _, p in shots)[no], img / f"{self.slug}-{no:02d}.jpg")
                alt = f"{i + 1}단계 {s['name']}: {t}"
                rows_html.append(f'<p><img src="사진/{f.name}" alt="{html.escape(alt)}"></p><p>{html.escape(t)}</p>')
                rows_txt.append(f"[사진 {f.name} — 대체 텍스트: {alt}]\n{t}")
        t = self.texts.get("naver_blog") or self.make_texts("naver_blog")
        intro = f"{self.topic} 방법을 {T.count_word(self.n_steps)} 단계로 정리했어요. 영상과 사진을 보며 그대로 따라 해 보세요."
        (folder / "블로그글.html").write_text(f"<h1>{html.escape(t['제목'])}</h1>\n<p>{html.escape(intro)}</p>\n"
                                            + "\n".join(rows_html) + f"\n<p>바로 가기: {t['링크']}</p>\n<p>{t['해시태그']}</p>\n",
                                            encoding="utf-8")
        (folder / "블로그글.txt").write_text(f"{t['제목']}\n\n{intro}\n" + "\n".join(rows_txt) +
                                           f"\n\n바로 가기: {t['링크']}\n\n{t['해시태그']}\n", encoding="utf-8")
        place(self.og_image(), folder / f"{self.slug}-대표이미지.jpg")
        return ["블로그글", "화면캡처", "대표이미지", "대체텍스트"]

    # ── 올릴 곳별 ──
    def export(self, dests: list[str], off: set[str] | None = None, on_stage=None) -> dict:
        off = off or set()
        stage = on_stage or (lambda n: None)
        P = self.P["올릴곳"]
        unknown = [d for d in dests if d not in P]
        if unknown:
            raise ValueError(f"모르는 올릴 곳: {', '.join(unknown)}")
        self.out.mkdir(exist_ok=True)
        for d in dests:
            p = P[d]
            name = p["이름"].replace("·", "_").replace(" ", "_")
            folder = self.out / name
            folder.mkdir(parents=True, exist_ok=True)
            stage(f"{p['이름']} 준비")
            self.say(f"[내보내기] {p['이름']}")
            items = set(p["항목"]) - off
            made: list[str] = []
            kind = p["영상"]["종류"]
            if kind == "가로1440":
                v = self.v_youtube() if "최종화면자리" in items else self.v_1440()
                place(v, folder / f"{self.slug}.mp4"); made += ["가로1440p"] + (["최종화면자리"] if "최종화면자리" in items else [])
            elif kind == "세로":
                place(self.v_vertical(), folder / f"{self.slug}-세로.mp4")
                made += ["세로영상", "첫2초", "반복재생", "자막새김", "안전영역", "본편연결"]
            elif kind in ("4대5", "1대1"):
                place(self.v_full_canvas(kind), folder / f"{self.slug}-{kind}.mp4"); made += [f"{kind}영상", "자막새김"]
            elif kind == "가로1080":
                place(self.v_1080(), folder / f"{self.slug}.mp4"); made += ["가로1080p"]
            elif kind == "짧은가로":
                place(self.v_short16(), folder / f"{self.slug}-짧은버전.mp4"); made += ["짧은가로영상", "짧은버전"]
            elif kind == "웹":
                made += self.web_bundle(folder)
            elif kind == "장면클립":
                for mp4, gif in self.clips():
                    place(mp4, folder / "장면클립" / f"{self.slug}-{mp4.stem}.mp4")
                    place(gif, folder / "장면클립" / f"{self.slug}-{gif.stem}.gif")
                pt = place(self.play_thumb(), folder / f"{self.slug}-재생버튼.jpg")
                link = utm(self.site, p.get("utm", d), self.campaign)
                (folder / "이메일용.html").write_text(
                    f'<a href="{link}"><img src="{pt.name}" alt="{html.escape(self.sc.title_plain)} 영상 보기" width="640" height="360"></a>\n',
                    encoding="utf-8")
                made += ["장면클립", "재생버튼썸네일"]
            if "썸네일" in items:
                for i, t in enumerate(self.thumbnails(), 1):
                    place(t, folder / f"{self.slug}-썸네일{i}.jpg")
                made.append("썸네일")
            if "세로커버" in items:
                place(self.cover(), folder / f"{self.slug}-커버.jpg"); made.append("세로커버")
            if "핀이미지" in items:
                place(self.pin_image(), folder / f"{self.slug}-핀.jpg"); made.append("핀이미지")
            if "자막SRT" in items:
                place(self.work / f"{self.sc.file_name}.srt", folder / f"{self.slug}.ko.srt"); made.append("자막SRT")
            if "블로그글" in items:
                made += self.blog_bundle(folder)
                place(self.v_1080(), folder / f"{self.slug}.mp4")
            self.make_texts(d)
            self.write_texts(d, folder)
            t = self.texts[d]
            made += [k for k, key in (("제목", "제목"), ("설명", "설명"), ("해시태그", "해시태그"), ("고정댓글", "고정 댓글"),
                                      ("행동유도", "행동 유도"), ("링크", "링크")) if key in t]
            if "챕터" in items:
                made.append("챕터")
            for extra in ("업무용설명", "첫문장핵심", "짧은설명", "핀제목설명"):
                if extra in items and "설명" in t:
                    made.append(extra)
            self.made[d] = {"폴더": str(folder), "항목": sorted(set(made) & (items | set(self.P["항상"])) | (set(made) & items))}
        stage("항상 챙기는 것")
        self.always(dests)
        stage("규격 검사")
        return self.check(dests, off)

    def always(self, dests: list[str]):
        P = self.P["올릴곳"]
        common = self.out / "공통"
        common.mkdir(exist_ok=True)
        rows = ["올린 곳,올린 날짜,주소,조회수,클릭 수,메모"] + [f"{P[d]['이름']},,,,," for d in dests]
        (common / "성과기록.csv").write_text("\ufeff" + "\n".join(rows) + "\n", encoding="utf-8")   # 엑셀에서 한글이 안 깨지게
        q = json.loads((self.work / "qa.json").read_text(encoding="utf-8")) if (self.work / "qa.json").exists() else None
        priv = next((i for i in (q or {}).get("항목", []) if i["이름"].startswith("개인정보")), None)
        (common / "개인정보검사.txt").write_text(
            (f"개인정보 최종 검사: {priv['판정']} — {priv['내용']}\n" if priv else "개인정보 최종 검사 결과가 없어요. 만들기를 다시 해 주세요.\n")
            + "세로·4:5·1:1·클립은 같은 최종본에서 만들어 같은 검사 결과를 따릅니다.\n", encoding="utf-8")
        (common / "사용조건.txt").write_text(
            "· 목소리: Microsoft 신경망 음성(edge-tts). 상업적 사용·배포 전에 Microsoft 이용 조건을 확인하세요.\n"
            "· 글꼴: Pretendard (SIL Open Font License 1.1, 영상에 새겨 쓰는 것 가능).\n"
            "· 배경음악: 넣지 않았어요.\n· 화면: 녹화한 사이트가 본인 사이트이거나 사용 허락을 받은 사이트여야 해요.\n", encoding="utf-8")
        tasks = {
            "youtube": ["최종 화면: 마지막 8초에 다음 영상·구독 요소 넣기(유튜브 스튜디오 → 최종 화면)", "카드: 관련 영상 연결",
                        "썸네일 3개로 '테스트 및 비교' 하기", "자막: .ko.srt 올리기", "재생목록에 넣기(시리즈)",
                        "올리는 시각: 유튜브 스튜디오 분석 → '시청자가 YouTube를 이용하는 시간' 보고 정하기"],
            "shorts": ["'관련 동영상'에 본편 연결"], "reels": ["커버: -커버.jpg 선택", "프로필 링크 확인(릴스 설명의 링크는 눌리지 않음)"],
            "tiktok": ["커버 고르기", "프로필 링크 확인"], "naver_clip": ["네이버 TV 앱에서 올리기, 규격은 올리기 전에 공식 안내 확인"],
            "naver_blog": ["블로그글.txt 순서대로 사진·글 붙여 넣기, 영상은 '동영상' 버튼으로"],
            "web": ["검색엔진제출안내.txt 따라 하기"], "x": ["일반 계정 길이 제한(2분 20초) 확인"],
            "pinterest": ["핀 링크에 글.txt 의 링크 넣기"], "linkedin": ["자막이 새겨져 있어 소리 없이도 보여요"],
        }
        lines = [f"# 올리기 체크리스트 ({dt.date.today().isoformat()})", "", "플랫폼 안에서만 되는 설정이에요. 끝내면 [x] 로 바꾸고 성과기록.csv 에 주소를 적어 두세요.", ""]
        for d in dests:
            lines.append(f"## {P[d]['이름']}")
            lines += [f"- [ ] {P[d]['이름']}에 올리기"] + [f"- [ ] {x}" for x in tasks.get(d, [])]
            lines.append("")
        lines.append("노출·검색 인용은 플랫폼이 정합니다. 프로그램은 규격과 조건을 빠짐없이 맞추는 데까지 해요.")
        (common / "올리기체크리스트.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for d in dests:
            self.made[d]["항목"] = sorted(set(self.made[d]["항목"]) | set(self.P["항상"]))

    # ── 규격 자동 검사 ──
    @staticmethod
    def probe(p: Path) -> dict:
        out = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                              "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,color_primaries,sample_rate:format=duration,size:format_tags=title",
                              "-of", "json", str(p)], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    @staticmethod
    def faststart(p: Path) -> bool:
        """moov 상자가 mdat 보다 앞에 있으면 웹에서 내려받는 즉시 재생된다."""
        with p.open("rb") as f:
            while True:
                head = f.read(8)
                if len(head) < 8:
                    return False
                size, kind = int.from_bytes(head[:4], "big"), head[4:8]
                if kind == b"moov":
                    return True
                if kind == b"mdat":
                    return False
                if size == 1:
                    size = int.from_bytes(f.read(8), "big") - 8
                f.seek(size - 8, 1)

    def check_video(self, p: Path, spec: dict, codec: str = "h264") -> list[dict]:
        j = self.probe(p)
        v = next(s for s in j["streams"] if s["codec_type"] == "video")
        a = next((s for s in j["streams"] if s["codec_type"] == "audio"), {})
        dur, size = float(j["format"]["duration"]), int(j["format"]["size"])
        num, den = v["r_frame_rate"].split("/")
        fps = float(num) / float(den)
        W, H = spec["크기"]
        res = []
        add = lambda name, ok, msg, warn=False: res.append({"이름": f"{p.name}: {name}", "판정": "ok" if ok else ("warn" if warn else "fail"), "내용": msg})
        add("크기", (v["width"], v["height"]) == (W, H), f"{v['width']}×{v['height']} (규격 {W}×{H})")
        add("프레임", abs(fps - spec["fps"]) < 0.02, f"{fps:g}fps (규격 {spec['fps']})")
        add("코덱", v["codec_name"] == codec and v.get("pix_fmt") == "yuv420p", f"{v['codec_name']} {v.get('pix_fmt')}")
        add("색", v.get("color_primaries") == "bt709", f"{v.get('color_primaries', '없음')}")
        add("소리", a.get("codec_name") == "aac" and a.get("sample_rate") == "48000", f"{a.get('codec_name', '없음')} {a.get('sample_rate', '')}Hz")
        lim = spec.get("최대초")
        note = " (공식 안내 확인 필요)" if spec.get("확인필요") else ""
        add("길이", not lim or dur <= lim, f"{dur:.1f}초" + (f" (최대 {lim}초){note}" if lim else ""), warn=bool(spec.get("확인필요")))
        add("용량", size <= spec.get("최대MB", 1e9) * 1024 * 1024, f"{size / 1024 / 1024:.1f}MB (최대 {spec.get('최대MB')}MB)")
        add("빠른 재생(faststart)", self.faststart(p), "웹에서 바로 재생" if self.faststart(p) else "moov 가 뒤에 있음")
        add("파일 안 정보", bool(j["format"].get("tags", {}).get("title")), j["format"].get("tags", {}).get("title", "제목 없음"))
        return res

    def check_image(self, p: Path, size=None, max_mb: float = 5) -> dict:
        from PIL import Image
        with Image.open(p) as im:
            w, h = im.size
        mb = p.stat().st_size / 1024 / 1024
        ok = (not size or (w, h) == tuple(size)) and mb <= max_mb
        return {"이름": f"{p.name}", "판정": "ok" if ok else "fail", "내용": f"{w}×{h}, {mb:.2f}MB" + (f" (규격 {size[0]}×{size[1]}, {max_mb}MB 이하)" if size else "")}

    def check(self, dests: list[str], off: set[str]) -> dict:
        P, out = self.P["올릴곳"], {}
        names = self.P["항목이름"]
        for d in dests:
            p, folder = P[d], Path(self.made[d]["폴더"])
            res: list[dict] = []
            spec = p["영상"]
            for f in sorted(folder.rglob("*.mp4")):
                if spec["종류"] == "장면클립":
                    res += [r for r in self.check_video(f, spec) if not r["이름"].endswith("파일 안 정보")]
                else:
                    res += self.check_video(f, spec, "av1" if f.stem.endswith("-av1") else "h264")
            for f in sorted(folder.glob("*썸네일*.jpg")):
                res.append(self.check_image(f, self.P["썸네일"]["크기"], self.P["썸네일"]["최대MB"]))
            for f in sorted(folder.glob("*-커버.jpg")):
                res.append(self.check_image(f, (1080, 1920)))
            for f in sorted(folder.glob("*-대표이미지.jpg")):
                r = self.check_image(f, (1200, 630))
                r["이름"] += " (오픈그래프·카카오톡 미리보기: 800×400 이상, 1.91:1)"
                res.append(r)
            for f in sorted(folder.rglob("*.gif")):
                mb = f.stat().st_size / 1024 / 1024
                res.append({"이름": f.name, "판정": "ok" if mb <= 8 else "warn", "내용": f"{mb:.1f}MB (메일·메신저는 8MB 이하 권장)"})
            lim, t = p.get("글", {}), self.texts.get(d, {})
            for key, field in (("제목", "제목"), ("설명", "설명")):
                if key in lim and field in t:
                    n = len(t[field])
                    res.append({"이름": f"글: {field}", "판정": "ok" if n <= lim[key] else ("warn" if lim.get("확인필요") else "fail"),
                                "내용": f"{n}자 (최대 {lim[key]}자)"})
            if "해시태그" in lim:
                n = len(re.findall(r"#\w+", t.get("해시태그", t.get("설명", ""))))
                res.append({"이름": "글: 해시태그", "판정": "ok" if n <= lim["해시태그"] else "fail", "내용": f"{n}개 (최대 {lim['해시태그']}개)"})
            if "링크" in t:
                res.append({"이름": "글: 링크 꼬리표(UTM)", "판정": "ok" if "utm_source=" in t["링크"] else "fail", "내용": t["링크"]})
            if d == "web":
                res += self.check_web(folder)
            # 빠짐 검사: 연결표의 항목 중 안 만든 것
            want = (set(p["항목"]) | set(self.P["항상"])) - off
            soon = set(self.P.get("준비중", []))
            made = set(self.made[d]["항목"])
            for it in sorted(want - made - soon):
                res.append({"이름": f"빠짐: {names.get(it, it)}", "판정": "fail", "내용": "만들지 못했어요"})
            for it in sorted(want & soon):
                res.append({"이름": f"{names.get(it, it)}", "판정": "soon", "내용": "다음 업데이트에서 열려요"})
            worst = "fail" if any(r["판정"] == "fail" for r in res) else "warn" if any(r["판정"] == "warn" for r in res) else "ok"
            out[d] = {"이름": p["이름"], "폴더": str(folder), "판정": worst, "검사": res,
                      "항목": [names.get(i, i) for i in sorted(made)]}
        ok = all(v["판정"] != "fail" for v in out.values())
        rep = {"판정": "ok" if ok else "fail", "올릴곳": out, "폴더": str(self.out), "날짜": dt.date.today().isoformat()}
        (self.out / "점검.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        md = [f"# 내보내기 규격 검사 — {'통과' if ok else '확인 필요'}", ""]
        for d, v in out.items():
            md.append(f"## {v['이름']} — {v['판정']}")
            md += [f"- {'✓' if r['판정'] == 'ok' else '·' if r['판정'] == 'soon' else '⚠'} {r['이름']}: {r['내용']}" for r in v["검사"]]
            md.append("")
        (self.out / "점검.md").write_text("\n".join(md), encoding="utf-8")
        self.say(f"[내보내기] 규격 검사 {'통과' if ok else '확인 필요'}: {sum(len(v['검사']) for v in out.values())}개 항목")
        return rep

    def check_web(self, folder: Path) -> list[dict]:
        res = []
        page = (folder / "영상페이지.html").read_text(encoding="utf-8") if (folder / "영상페이지.html").exists() else ""
        for tag in ("og:title", "og:description", "og:image", "og:url", "twitter:card"):
            res.append({"이름": f"페이지: {tag}", "판정": "ok" if tag in page else "fail", "내용": "있음" if tag in page else "없음"})
        try:
            data = json.loads((folder / "구조화데이터.json").read_text(encoding="utf-8"))
            kinds = [x["@type"] for x in data]
            need = {"VideoObject", "HowTo", "FAQPage"}
            vo = next(x for x in data if x["@type"] == "VideoObject")
            fields = all(vo.get(k) for k in ("name", "description", "thumbnailUrl", "uploadDate", "contentUrl", "duration"))
            res.append({"이름": "구조화 데이터", "판정": "ok" if need <= set(kinds) and fields and vo.get("hasPart") else "fail",
                        "내용": ", ".join(kinds) + f" · 핵심 구간 {len(vo.get('hasPart', []))}개"})
        except Exception as e:
            res.append({"이름": "구조화 데이터", "판정": "fail", "내용": f"읽지 못함: {type(e).__name__}"})
        code = (folder / "붙여넣기코드.html").read_text(encoding="utf-8") if (folder / "붙여넣기코드.html").exists() else ""
        ok = 'preload="none"' in code and "av01" in code and "<track" in code and "poster=" in code
        res.append({"이름": "붙여 넣기 코드", "판정": "ok" if ok else "fail", "내용": "AV1 먼저·H.264 예비·자막·포스터·누르기 전엔 안 받기"})
        vtt = next(folder.glob("*.vtt"), None)
        res.append({"이름": "웹용 자막(VTT)", "판정": "ok" if vtt and vtt.read_text(encoding="utf-8").startswith("WEBVTT") else "fail",
                    "내용": vtt.name if vtt else "없음"})
        av1 = next(folder.glob("*-av1.mp4"), None)
        h = next(folder.glob("*-h264.mp4"), None)
        if av1 and h:
            a, b = av1.stat().st_size, h.stat().st_size
            res.append({"이름": "웹 압축", "판정": "ok" if a < b else "warn", "내용": f"AV1 {a / 1048576:.1f}MB · H.264 {b / 1048576:.1f}MB"})
        try:
            ET = __import__("xml.etree.ElementTree", fromlist=["x"])
            ET.parse(folder / "영상사이트맵.xml")
            res.append({"이름": "영상 사이트맵", "판정": "ok", "내용": "형식 맞음"})
        except Exception:
            res.append({"이름": "영상 사이트맵", "판정": "fail", "내용": "형식 오류"})
        return res
