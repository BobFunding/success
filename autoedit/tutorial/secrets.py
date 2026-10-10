"""비밀번호 보관함 (DESIGN.md 5.4).

- 장면 표에는 값 대신 '@보관함'(또는 '@보관함:이름')만 적는다. 장면 표·영상·로그·내보내기 어디에도 값이 남지 않는다.
- 저장 위치: 운영체제 보관함(Windows 자격 증명 관리자, Mac 키체인, Linux 비밀 서비스 — keyring 라이브러리).
  보관함을 쓸 수 없는 PC 면 PC 안 파일(~/.tutorial_maker/secrets.json, 나만 읽기).
- 이름(열쇠): '사이트주소|칸' (예: 'taekwonworld.net|input[name=password]'). 같은 사이트·같은 칸이면 다시 묻지 않는다.
- 검사·자동 실행용: 환경변수 TUTORIAL_SECRET 이 있으면 그 값을 쓴다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

SERVICE = "tutorial-maker"
STORE = Path.home() / ".tutorial_maker" / "secrets.json"


def key_for(url: str, target: str, value: str = "@보관함") -> str:
    name = value.split(":", 1)[1].strip() if ":" in value else target
    return f"{urlparse(url).netloc or url}|{name}"


def _kr():
    try:
        import keyring
        from keyring.backends import fail
        k = keyring.get_keyring()
        return None if isinstance(k, fail.Keyring) else keyring
    except Exception:
        return None


def _file() -> dict:
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(key: str) -> str | None:
    if os.environ.get("TUTORIAL_SECRET"):
        return os.environ["TUTORIAL_SECRET"]
    kr = _kr()
    if kr:
        try:
            v = kr.get_password(SERVICE, key)
            if v:
                return v
        except Exception:
            pass
    return _file().get(key)


def has(key: str) -> bool:
    return bool(get(key))


def put(key: str, value: str) -> str:
    """저장하고 어디에 저장했는지 돌려준다."""
    kr = _kr()
    if kr:
        try:
            kr.set_password(SERVICE, key, value)
            return "운영체제 보관함"
        except Exception:
            pass
    STORE.parent.mkdir(parents=True, exist_ok=True)
    d = _file()
    d[key] = value
    STORE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(STORE, 0o600)
    except OSError:
        pass
    return "이 PC 안 파일"


def needed(sc) -> list[dict]:
    """장면 표에서 보관함 값이 필요한 칸들 (미리하기 포함)."""
    out, seen = [], set()
    for s in list(getattr(sc, "pre_scenes", [])) + list(sc.scenes):
        for f in s.fields:
            if f.value.startswith("@보관함"):
                k = key_for(sc.login_url or sc.url, f.target, f.value)
                if k not in seen:
                    seen.add(k)
                    out.append({"키": k, "칸": s.label or f.target, "있음": has(k)})
    return out
