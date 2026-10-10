"""튜토리얼 메이커 7단계: 내보내기 — 연결표, UTM, 파일 이름, 글 길이, 빠른 재생(faststart) 검사."""
import subprocess
from pathlib import Path

import pytest

from autoedit.ffmpeg_utils import FFMPEG
from autoedit.tutorial import export as E


def test_platform_table_complete():
    P = E.load_platforms()
    assert len(P["올릴곳"]) == 14
    names = P["항목이름"]
    for k, p in P["올릴곳"].items():
        assert p["이름"] and p["utm"] and p["영상"]["크기"] and p["영상"]["fps"], k
        for it in p["항목"]:
            assert it in names, f"{k}: {it} 이름 없음"
    for it in P["항상"]:
        assert it in names
    assert [k for k, p in P["올릴곳"].items() if p.get("기본")] == ["youtube", "web"]


def test_utm_and_slug():
    u = E.utm("https://a.com/x?y=1", "youtube", "taekwonworld-관장님-회원가입-방법")
    assert u.startswith("https://a.com/x?y=1&utm_source=youtube&utm_medium=video&utm_campaign=")
    assert E.utm("https://a.com", "x", "c") == "https://a.com/?utm_source=x&utm_medium=video&utm_campaign=c"
    assert E.slugify("taekwonworld 관장님 회원가입, 방법?") == "taekwonworld-관장님-회원가입-방법"
    assert E.iso_dur(75) == "PT1M15S" and E.iso_dur(42.4) == "PT42S"


def test_srt_to_vtt(tmp_path):
    srt = tmp_path / "a.srt"
    srt.write_text("1\n00:00:01,250 --> 00:00:02,000\n안녕하세요\n", encoding="utf-8")
    E.Exporter.srt_to_vtt(srt, tmp_path / "a.vtt")
    v = (tmp_path / "a.vtt").read_text(encoding="utf-8")
    assert v.startswith("WEBVTT") and "00:00:01.250 --> 00:00:02.000" in v


def _clip(p: Path, *extra):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=1",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", *extra, str(p)], check=True)
    return p


def test_faststart_and_video_check(tmp_path):
    fast = _clip(tmp_path / "f.mp4", "-movflags", "+faststart", "-metadata", "title=제목",
                 "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709")
    slow = _clip(tmp_path / "s.mp4")
    assert E.Exporter.faststart(fast) and not E.Exporter.faststart(slow)
    ex = E.Exporter.__new__(E.Exporter)
    res = {r["이름"].split(": ", 1)[1]: r["판정"] for r in
           ex.check_video(fast, {"크기": [320, 180], "fps": 30, "최대초": 60, "최대MB": 1})}
    assert all(v == "ok" for v in res.values()), res
    res = {r["이름"].split(": ", 1)[1]: r["판정"] for r in
           ex.check_video(slow, {"크기": [1080, 1920], "fps": 30, "최대초": 0.5, "최대MB": 1})}
    assert res["크기"] == res["길이"] == res["빠른 재생(faststart)"] == res["파일 안 정보"] == "fail"


@pytest.mark.parametrize("dest", list(E.load_platforms()["올릴곳"]))
def test_texts_within_limits(dest):
    """긴 제목·단계로도 올릴 곳별 글이 길이·해시태그 제한 안에 들어간다."""
    from autoedit.tutorial import scenario as S
    sc = S.load(Path(__file__).resolve().parents[1] / "tutorials" / "ep1" / "scenario.yaml")
    ex = E.Exporter.__new__(E.Exporter)
    ex.sc, ex.P, ex.texts = sc, E.load_platforms(), {}
    ex.campaign = "taekwonworld-20261010"
    ex.topic, ex.site, ex.slug, ex.n_steps = "관장님 회원가입", "https://taekwonworld.net", "taekwonworld-관장님-회원가입-방법", len(sc.steps)
    ex.tl = {"intro": 9, "body": 60, "total": 75, "lines": [{"t": 10 + i, "text": f"문장 {i}"} for i in range(12)],
             "steps": [{"name": s, "start": 9 + i * 15, "end": 24 + i * 15} for i, s in enumerate(sc.steps)],
             "chapters": [{"name": "시작", "t": 0}, {"name": sc.steps[0], "t": 9}]}
    t = ex.make_texts(dest)
    lim = ex.P["올릴곳"][dest].get("글", {})
    for k in ("제목", "설명"):
        if k in lim and k in t:
            assert len(t[k]) <= lim[k], (dest, k, len(t[k]))
    if "해시태그" in lim:
        import re
        assert len(re.findall(r"#\w+", t.get("해시태그", t.get("설명", "")))) <= lim["해시태그"]
    if dest != "web":
        assert "utm_source=" in t["링크"]
