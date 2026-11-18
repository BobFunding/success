"""최종 합성: 컷 편집본 + 모자이크 + 삐- 처리 + 설명 일러스트·스티커 + 자막."""
from __future__ import annotations

from pathlib import Path

from .ffmpeg_utils import VideoInfo, filter_script_args, run_ffmpeg, video_encoder_args

FADE = 0.25


def _even(n: float) -> int:
    return max(2, int(n) // 2 * 2)


def render_final(cut_video: Path, dst: Path, info: VideoInfo, mosaics: list[dict], beeps: list[dict],
                 inserts: list[dict], block: int, cq: int, work_dir: Path, log=print, fx: dict | None = None,
                 subtitles: Path | None = None, x264_preset: str = "medium") -> None:
    fx = fx or {}
    W, H = info.width, info.height
    inputs = ["-i", str(cut_video)]
    parts: list[str] = []
    cur = "[0:v]"
    n = 0

    def nxt() -> str:
        nonlocal n
        n += 1
        return f"[v{n}]"

    # 1) 모자이크: 해당 영역을 잘라 작게 줄였다가 다시 키우면 픽셀 모자이크가 된다
    for i, m in enumerate(mosaics):
        x, y = _even(m["x"]), _even(m["y"])
        w, h = _even(min(m["w"], W - x)), _even(min(m["h"], H - y))
        if w < 4 or h < 4:
            continue
        # 글자 높이 기준 세로 3칸 이하로 뭉개야 숫자를 알아볼 수 없다 (고정 블록이면 큰 글자는 읽힘)
        sh = max(1, min(h // block, 3))
        sw = max(1, round(w * sh / h))
        base, src, blk, out = f"[mb{i}]", f"[ms{i}]", f"[mk{i}]", nxt()
        parts.append(f"{cur}split=2{base}{src}")
        parts.append(f"{src}crop={w}:{h}:{x}:{y},scale={sw}:{sh}:flags=area,scale={w}:{h}:flags=neighbor{blk}")
        parts.append(f"{base}{blk}overlay={x}:{y}:enable='between(t,{m['start']:.3f},{m['end']:.3f})'{out}")
        cur = out

    # 2) 설명 일러스트 — 부드러운 전환: 알파 페이드 + (카드) 감속 슬라이드 / (전체 화면) 천천히 확대
    fi, fo = fx.get("fade_in", FADE), fx.get("fade_out", FADE)
    slide = fx.get("card_slide", 60) * max(W, H) / 1280
    zoom = fx.get("full_zoom", 0.04)
    for k, ins in enumerate(inserts):
        png = ins.get("png_path")
        if not png or not Path(png).exists():
            continue
        start, end = float(ins["start"]), float(ins["end"])
        dur = end - start
        a_in, a_out = min(fi, dur / 3), min(fo, dur / 3)
        inputs += ["-loop", "1", "-framerate", f"{info.fps:.5f}", "-t", f"{dur + 0.1:.3f}", "-i", png]
        idx = inputs.count("-i") - 1  # 방금 추가한 입력의 번호
        fades = (f"fade=t=in:st=0:d={a_in:.3f}:alpha=1,"
                 f"fade=t=out:st={max(0.0, dur - a_out):.3f}:d={a_out:.3f}:alpha=1")
        img, out = f"[im{k}]", nxt()
        if ins["placement"] == "sticker":
            # 작은 아이콘: 지정한 자리에서 살짝 아래에서 튀어 오르듯(ease-out) 나타나고, 사라질 땐 그 자리에서 흐려진다
            sw = _even(ins.get("size") or min(W, H) * 0.16)
            px = int(ins.get("x") or W - sw - W * 0.05)
            py = int(ins.get("y") or H * 0.08)
            parts.append(f"[{idx}:v]format=rgba,scale={sw}:{sw}:flags=lanczos,{fades},"
                         f"setpts=PTS-STARTPTS+{start:.3f}/TB{img}")
            rise = f"{sw * 0.25:.1f}*pow(1-clip((t-{start:.3f})/{a_in:.3f},0,1),3)"
            pos = f"x={px}:y='{py}+{rise}'"
        elif ins["placement"] == "side":
            if ins.get("size"):
                cw, px, py = _even(ins["size"]), int(ins["x"]), int(ins["y"])
            elif W >= H:
                cw = _even(W * 0.42)
                px, py = W - cw - _even(W * 0.03), (H - cw) // 2
            else:
                cw = _even(W * 0.80)
                px, py = (W - cw) // 2, _even(H * 0.10)
            parts.append(f"[{idx}:v]format=rgba,scale={cw}:{cw}:flags=lanczos,{fades},"
                         f"setpts=PTS-STARTPTS+{start:.3f}/TB{img}")
            # 들어올 때: 가장자리 쪽에서 감속하며(ease-out cubic) 제자리로 / 나갈 때: 같은 쪽으로 가속하며 빠짐
            p_in = f"pow(1-clip((t-{start:.3f})/{a_in:.3f},0,1),3)"
            p_out = f"pow(clip((t-{end - a_out:.3f})/{a_out:.3f},0,1),2)"
            offset = f"{slide:.1f}*({p_in}+0.6*{p_out})"
            if W >= H:
                sign = 1 if px + cw / 2 >= W / 2 else -1  # 오른쪽 카드는 오른쪽에서, 왼쪽 카드는 왼쪽에서
                pos = f"x='{px}+{sign}*{offset}':y={py}"
            else:
                pos = f"x={px}:y='{py}+{offset}'"
        else:
            # 켄 번즈: 표시되는 동안 1.0 → 1.0+zoom 배로 아주 천천히 확대 (정지 화면 느낌을 없앰)
            parts.append(f"[{idx}:v]format=rgba,scale={W}:{H}:flags=lanczos,"
                         f"scale=w='trunc({W}*(1+{zoom}*t/{dur:.3f})/2)*2':h=-2:eval=frame:flags=bicubic,"
                         f"crop={W}:{H},{fades},setpts=PTS-STARTPTS+{start:.3f}/TB{img}")
            pos = "x=0:y=0"
        parts.append(f"{cur}{img}overlay={pos}:eof_action=pass:enable='between(t,{start:.3f},{end:.3f})'{out}")
        cur = out

    # 3) 자막: 맨 위에 입힌다 (일러스트에 가려지지 않게)
    if subtitles and Path(subtitles).exists():
        # 필터 옵션 안에서는 ':' 가 구분자라서 Windows 드라이브 문자(C:)를 이스케이프해야 한다
        name = Path(subtitles).resolve().as_posix().replace(":", "\\:")
        out = nxt()
        parts.append(f"{cur}ass=filename='{name}'{out}")
        cur = out

    if cur == "[0:v]":
        parts.append("[0:v]null[vout]")
    else:
        parts[-1] = parts[-1][: -len(cur)] + "[vout]"

    # 4) 말로 나온 개인정보: 원래 소리를 끄고 1kHz 삐- 소리를 얹는다
    audio_map: list[str]
    if info.has_audio and beeps:
        cond = "+".join(f"between(t,{b['start']:.3f},{b['end']:.3f})" for b in beeps)
        parts.append(f"[0:a]volume=enable='{cond}':volume=0[amuted]")
        parts.append(f"sine=frequency=1000:sample_rate=48000:duration={info.duration + 1:.3f},"
                     f"volume='0.18*gt({cond},0)':eval=frame[beep]")
        parts.append("[amuted][beep]amix=inputs=2:duration=first:normalize=0[aout]")
        audio_map = ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
    elif info.has_audio:
        audio_map = ["-map", "0:a", "-c:a", "copy"]
    else:
        audio_map = []

    script = work_dir / "final_filter.txt"
    script.write_text(";\n".join(parts), encoding="utf-8")
    log(f"[합성] 모자이크 {len(mosaics)}건 · 삐- {len(beeps)}건 · 일러스트 {len(inserts)}장"
        f"{' · 자막' if subtitles else ''} 합성 중...")
    run_ffmpeg([*inputs, *filter_script_args(script), "-map", "[vout]", *audio_map,
                *video_encoder_args(cq, x264_preset), "-movflags", "+faststart", str(dst)], log)
