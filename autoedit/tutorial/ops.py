"""운영 기능 (DESIGN.md 13절): 오류 보고 묶음, 프로젝트 공유 파일, 시리즈.

- 오류 보고: [오류 정보 복사] 한 번으로 AI·개발자에게 물어볼 글. 개인정보·키·비밀번호는 넣지 않는다
  (장면 표의 적는 값은 빼고, 로그의 전화·메일·키 모양은 가린다).
- 공유 파일(.tutorial.zip): 장면 표·브랜드(로고)·규칙·선택·번역. 비밀번호(보관함)·영상·녹음·키는 넣지 않는다.
  개인정보 칸에 적은 값도 비운다(받는 사람이 자기 테스트 값을 넣음).
- 시리즈: 장면 표의 '시리즈'(이름)·'편'(번호). 같은 시리즈의 다음 편 주제를 '다음편'에 자동으로 잇고,
  아웃트로 끝 문장의 다음 편 안내를 맞춘다(사람이 고친 문장은 건드리지 않음).
"""
from __future__ import annotations

import io
import json
import platform
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml

from . import scenario as S
from . import sentences as T

ROOT = Path(__file__).resolve().parents[2]
_MASK = [(re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***"), (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "***@***"),
         (re.compile(r"01[016789]-?\d{3,4}-?\d{4}"), "010-****-****"), (re.compile(r"\b\d{6}\b"), "******")]


def mask(text: str) -> str:
    for rx, rep in _MASK:
        text = rx.sub(rep, text)
    return text


def _ver() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%h %cs"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or "알 수 없음"
    except Exception:
        return "알 수 없음"


def report(job: dict | None, path: Path | None = None) -> str:
    """오류 정보(복사해 붙여 넣는 글)."""
    from ..ffmpeg_utils import FFMPEG
    from .capture import capture_method
    try:
        ff = subprocess.run([FFMPEG, "-version"], capture_output=True, text=True, timeout=5).stdout.split("\n")[0]
    except Exception:
        ff = "ffmpeg 없음"
    lines = ["[튜토리얼 메이커 오류 정보]", f"- 버전: {_ver()}", f"- 컴퓨터: {platform.system()} {platform.release()} · Python {sys.version.split()[0]}",
             f"- {ff[:60]}", f"- 녹화 방식: {capture_method()}"]
    if job:
        lines += [f"- 작업: {job.get('kind', '')} · 단계 '{job.get('stage', '')}' · {'진행 중' if job.get('running') else '끝남'}",
                  f"- 오류: {mask(str(job.get('error') or '없음'))}"]
    if path and path.exists():
        try:
            d = yaml.safe_load(path.read_text(encoding="utf-8"))
            acts = [f"{s.get('키', '')}:{s.get('동작', '')}" for s in d.get("장면") or []]
            lines += [f"- 장면 표: 장면 {len(acts)}개, 시작상태 {d.get('시작상태', '')}, 주소 {re.sub(r'[?#].*', '', str(d.get('주소', '')))}",
                      f"  동작: {' '.join(acts)}"]
        except Exception as e:
            lines.append(f"- 장면 표를 읽지 못함: {type(e).__name__}")
    log = (job or {}).get("log") or []
    if log:
        lines += ["- 마지막 기록:"] + [f"  {mask(str(x))[:200]}" for x in log[-30:]]
    lines.append("(개인정보·비밀번호·키는 빼고 모았어요. 이 글을 AI 채팅이나 개발자에게 그대로 붙여 넣으세요.)")
    return "\n".join(lines)


# ── 공유 파일 ──
def _clean_scenario(d: dict) -> dict:
    d = json.loads(json.dumps(d, ensure_ascii=False))
    priv = set(d.get("개인정보칸") or [])
    for s in list(d.get("미리하기") or []) + list(d.get("장면") or []):
        for f in s.get("칸") or []:
            v = str(f.get("값", ""))
            if f.get("누를곳") in priv and not v.startswith("@"):
                f["값"] = ""                                # 받는 사람이 자기 테스트 값을 적음
    return d


def pack(path: Path, work: Path) -> Path:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = work / "공유" / f"{d.get('파일이름') or path.parent.name}.tutorial.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("scenario.yaml", yaml.safe_dump(_clean_scenario(d), allow_unicode=True, sort_keys=False))
        b = d.get("브랜드") or "basic"
        try:
            bp = S.brand_path(b)
            z.write(bp, f"brand/{bp.name}")
            bd = yaml.safe_load(bp.read_text(encoding="utf-8")) or {}
            if bd.get("로고") and (bp.parent / bd["로고"]).exists():
                z.write(bp.parent / bd["로고"], f"brand/{bd['로고']}")
        except Exception:
            pass
        for name in ("choices.json", "translations.json"):
            if (work / name).exists():
                z.write(work / name, name)
        from . import rules as R
        z.writestr("rules.yaml", yaml.safe_dump(R.load_user(), allow_unicode=True, sort_keys=False))
        z.writestr("읽어주세요.txt", "튜토리얼 메이커 공유 파일이에요. 시작 화면 '지난 작업'의 [가져오기]로 여세요.\n"
                   "비밀번호·영상·녹음·키는 들어 있지 않아요. 개인정보 칸의 값도 비워 두었어요.\n")
    return out


def unpack(data: bytes, projects: Path) -> Path:
    """공유 파일 열기 → 새 프로젝트 폴더. 브랜드는 내 브랜드에 없을 때만 추가(내 것을 덮지 않음). 규칙은 덮지 않는다."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if "scenario.yaml" not in names:
            raise ValueError("튜토리얼 메이커 공유 파일이 아니에요.")
        for n in names:
            if n.startswith("/") or ".." in Path(n).parts:
                raise ValueError("이상한 파일이 들어 있어 열지 않았어요.")
        d = yaml.safe_load(z.read("scenario.yaml").decode("utf-8"))
        base = re.sub(r"[^\w가-힣-]+", "_", str(d.get("파일이름") or "가져온_작업")).strip("_") or "가져온_작업"
        folder, i = projects / base, 2
        while folder.exists():
            folder, i = projects / f"{base}_{i}", i + 1
        folder.mkdir(parents=True)
        d["파일이름"] = folder.name
        (folder / "scenario.yaml").write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
        for n in ("choices.json", "translations.json"):
            if n in names:
                (folder / n).write_bytes(z.read(n))
        S.USER_BRANDS.mkdir(parents=True, exist_ok=True)
        for n in names:
            if n.startswith("brand/") and not n.endswith("/"):
                dst = S.USER_BRANDS / Path(n).name
                if not dst.exists() and not (S.PRESETS / "brands" / Path(n).name).exists():
                    dst.write_bytes(z.read(n))
    S.load(folder / "scenario.yaml")
    return folder / "scenario.yaml"


# ── 시리즈 ──
def series_list(projects: list[Path]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for p in projects:
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("시리즈"):
            out.setdefault(str(d["시리즈"]), []).append({"path": str(p), "편": int(d.get("편") or 0),
                                                          "제목": str(d["제목"]).replace("[", "").replace("]", "")})
    for v in out.values():
        v.sort(key=lambda x: x["편"])
    return out


def _topic(d: dict) -> str:
    return T.topic_words(str(d["제목"]).replace("[", "").replace("]", "").split(",")[0])


def link_series(name: str, projects: list[Path]) -> int:
    """같은 시리즈를 편 번호 순으로 잇는다: '다음편' = 다음 편 주제, 아웃트로 끝 문장의 안내도 맞춤. 고친 장면 표 수."""
    from .demo_record import save
    eps = series_list(projects).get(name, [])
    n = 0
    for i, e in enumerate(eps):
        p = Path(e["path"])
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        nxt = _topic(yaml.safe_load(Path(eps[i + 1]["path"]).read_text(encoding="utf-8"))) if i + 1 < len(eps) else ""
        if (d.get("다음편") or "") == nxt:
            continue
        old = d.get("다음편") or ""
        d["다음편"] = nxt
        if not nxt:
            d.pop("다음편")
        out = d.get("아웃트로") or []
        if out:
            last = out[-1]
            say = str(last.get("말", ""))
            ann = re.compile(r"^다음 영상에서는 .+? 방법을 알려 드릴게요\. ")
            if ann.match(say) or (not old and not say.startswith("다음 영상")):
                rest = ann.sub("", say)
                last["말"] = (f"다음 영상에서는 {nxt} 방법을 알려 드릴게요. " if nxt else "") + rest
        save(d, p)
        n += 1
    return n


def set_series(path: Path, name: str, no: int, projects: list[Path]) -> int:
    from .demo_record import save
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    old = d.get("시리즈")
    if name:
        d["시리즈"], d["편"] = name, int(no)
    else:
        d.pop("시리즈", None); d.pop("편", None)
    save(d, path)
    n = link_series(name, projects) if name else 0
    if old and old != name:
        n += link_series(old, projects)
    return n
