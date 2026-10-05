"""최종 합성: 컷 편집본 + 모자이크 + 삐- 처리 + 설명 일러스트."""
from __future__ import annotations

from pathlib import Path

from .ffmpeg_utils import VideoInfo, filter_script_args, run_ffmpeg, video_encoder_args

FADE = 0.25


def _even(n: float) -> int:
    return max(2, int(n) // 2 * 2)


def render_final(cut_video: Path, dst: Path, info: VideoInfo, mosaics: list[dict], beeps: list[dict],
                 inserts: list[dict], block: int, cq: int, work_dir: Path, log=print) -> None:
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

    # 2) 설명 일러스트
    for k, ins in enumerate(inserts):
        png = ins.get("png_path")
        if not png or not Path(png).exists():
            continue
        start, end = float(ins["start"]), float(ins["end"])
        dur = end - start
        inputs += ["-loop", "1", "-t", f"{dur + 0.1:.3f}", "-i", png]
        idx = inputs.count("-i") - 1  # 방금 추가한 입력의 번호
        if ins["placement"] == "side":
            if W >= H:
                cw = _even(W * 0.42)
                px, py = W - cw - _even(W * 0.03), (H - cw) // 2
            else:
                cw = _even(W * 0.80)
                px, py = (W - cw) // 2, _even(H * 0.10)
            size, pos = f"{cw}:{cw}", f"{px}:{py}"
        else:
            size, pos = f"{W}:{H}", "0:0"
        img, out = f"[im{k}]", nxt()
        parts.append(
            f"[{idx}:v]format=rgba,scale={size}:flags=lanczos,"
            f"fade=t=in:st=0:d={FADE}:alpha=1,fade=t=out:st={max(0.0, dur - FADE):.3f}:d={FADE}:alpha=1,"
            f"setpts=PTS-STARTPTS+{start:.3f}/TB{img}")
        parts.append(f"{cur}{img}overlay={pos}:eof_action=pass:enable='between(t,{start:.3f},{end:.3f})'{out}")
        cur = out

    if cur == "[0:v]":
        parts.append("[0:v]null[vout]")
    else:
        parts[-1] = parts[-1][: -len(cur)] + "[vout]"

    # 3) 말로 나온 개인정보: 원래 소리를 끄고 1kHz 삐- 소리를 얹는다
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
    log(f"[합성] 모자이크 {len(mosaics)}건 · 삐- {len(beeps)}건 · 일러스트 {len(inserts)}장 합성 중...")
    run_ffmpeg([*inputs, *filter_script_args(script), "-map", "[vout]", *audio_map,
                *video_encoder_args(cq), "-movflags", "+faststart", str(dst)], log)
