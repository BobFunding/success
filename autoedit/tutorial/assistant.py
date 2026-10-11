"""AI 도우미 (DESIGN.md 11절): 키가 있을 때만 켜지는 선택 기능. Claude 호출은 모두 autoedit/llm.py 래퍼를 거친다.

- AI에게 맡기기(explore): 한 줄 요청 → AI가 '한 번 해 보이기' 브라우저를 사람 대신 조작한다. 기록·장면 표 만들기는
  사람이 시연할 때와 같은 코드(demo_record)를 그대로 쓴다. 둘러보는 동안 저장(POST 등)은 막고, 비밀번호·인증번호는 사람에게 묻는다.
- 문장 다듬기(polish): 브랜드 말투로 장면 문장을 고친 '제안'을 돌려준다(적용은 사람이).
- 번역(translate): 자막·제목·설명을 다른 언어로.

키가 없으면 LLMUnavailable — 화면은 그 자리에서 키 넣는 3단계 안내를 보여 주고, 나머지 기능은 그대로 돈다.
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Literal

from pydantic import BaseModel, Field

try:                                     # AI 부품(anthropic)이 없는 PC 에서도 화면은 떠야 한다
    from ..llm import LLM, LLMUnavailable
except ImportError:                      # pragma: no cover
    LLM = None

    class LLMUnavailable(RuntimeError):
        pass

MODEL = "claude-opus-5-5"
KEY = "anthropic.com|api_key"           # 보관함 열쇠 (server.KEYS 와 같음)
# 예상 비용(화면 표시용, 대략): Claude Opus 5.5 입력 $4 / 출력 $20 (100만 토큰당), 환율은 어림값
PRICE_IN, PRICE_OUT, USD_KRW = 4.0, 20.0, 1400
MAX_STEPS = 24

from .langs import LANGS  # noqa: E402  (언어 목록은 한 곳에)


def ensure_key() -> bool:
    """보관함에 넣어 둔 키를 이번 실행에서만 환경변수로(파일에 쓰지 않음)."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    from . import secrets as SEC
    k = SEC.get(KEY)
    if k:
        os.environ["ANTHROPIC_API_KEY"] = k
    return bool(k)


def get_llm(log=print) -> LLM:
    if LLM is None:
        raise LLMUnavailable("AI 부품(anthropic)이 없어요. setup 을 다시 실행해 주세요.")
    ensure_key()
    llm = LLM(MODEL, log=lambda *a: None)
    if not llm.available:
        raise LLMUnavailable("AI 도우미 키가 없어요. ⚙ 설정 → 규칙 → 'AI·유료 음성 키'에서 넣으면 켜져요.")
    return llm


def won(usd: float) -> str:
    return f"약 {max(10, round(usd * USD_KRW, -1)):,.0f}원"


def estimate(kind: str, n: int = 0) -> dict:
    """실행 전 예상 비용. explore: 단계마다 화면 사진(약 1.5천 토큰)+누를 곳 목록(약 2천)+기록, 답 약 0.8천(생각 포함)."""
    if kind == "explore":
        usd = MAX_STEPS * (4000 * PRICE_IN + 900 * PRICE_OUT) / 1e6
        return {"usd": round(usd, 2), "text": f"최대 {won(usd)} (단계 {MAX_STEPS}번까지, 보통은 그보다 적게)"}
    usd = (n * 60 + 1500) * PRICE_IN / 1e6 + (n * 80 + 500) * PRICE_OUT / 1e6
    return {"usd": round(usd, 3), "text": won(usd)}


# ── 문장 다듬기 · 번역 ──
class Item(BaseModel):
    key: str
    text: str


class Items(BaseModel):
    items: list[Item]


def _items(llm, system: str, content: str, keys: list[str]) -> dict[str, str]:
    r = llm.parse(system, content, Items, effort="medium", max_tokens=16000)
    got = {i.key: i.text.strip() for i in r.items if i.key in keys and i.text.strip()}
    return {k: got[k] for k in keys if k in got}


def polish(llm, lines: dict[str, str], tone: str = "차분", brand: str = "") -> dict[str, str]:
    """바뀐 문장만 돌려준다(그대로 둔 것은 빠짐)."""
    sys = ("웹사이트 사용법 영상의 나레이션 문장을 다듬는다. 화면을 보며 따라 하는 사람을 위한 문장이다.\n"
           f"- 말투: {tone}. 존댓말. 한 문장에 동작 하나. 화면에 보이는 버튼·칸 이름은 그대로 둔다(따옴표 없이).\n"
           "- 숨 쉬는 자리에 쉼표. 너무 길면 줄인다. 뜻·순서·단계는 바꾸지 않는다. 숫자·이름은 그대로.\n"
           + (f"- 브랜드 이름: {brand} (그대로 쓴다)\n" if brand else "")
           + "- 고칠 필요가 없으면 원문 그대로 돌려준다. key 는 그대로.")
    keys = list(lines)
    out = _items(llm, sys, json.dumps([{"key": k, "text": v} for k, v in lines.items()], ensure_ascii=False), keys)
    return {k: v for k, v in out.items() if v != lines[k]}


def translate(llm, items: dict[str, str], lang: str, brand: str = "") -> dict[str, str]:
    name = LANGS.get(lang, lang)
    sys = (f"웹사이트 사용법 영상의 자막·제목·설명을 {name}로 번역한다.\n"
           "- 화면에 보이는 버튼·메뉴 이름은 원문(한국어)을 괄호로 함께 둔다. 예: Click the Sign up (회원가입) button.\n"
           "- 자막이므로 짧고 자연스럽게. 존댓말 느낌은 그 언어의 정중한 안내체로.\n"
           + (f"- 브랜드 이름 '{brand}' 는 번역하지 않는다.\n" if brand else "")
           + "- 모든 key 를 빠짐없이 그대로 돌려준다.")
    keys = list(items)
    return _items(llm, sys, json.dumps([{"key": k, "text": v} for k, v in items.items()], ensure_ascii=False), keys)


# ── AI에게 맡기기 ──
class Action(BaseModel):
    kind: Literal["click", "type", "select", "hover", "scroll", "ask", "done", "fail"]
    index: int | None = Field(default=None, description="누를 곳 목록의 번호")
    text: str = Field(default="", description="type: 적을 값 / select: 고를 항목 / ask: 사람에게 물을 말 / done·fail: 요약")
    secret: bool = Field(default=False, description="비밀번호·인증번호처럼 사람에게 받아야 하는 값이면 true(이때 text 는 물을 말)")
    reason: str = ""


ELEMENTS_JS = r"""() => {
  const out = []; const clean = s => (s || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const q = 'a, button, input, select, textarea, summary, [role=button], [role=link], [role=checkbox], [role=tab], [role=menuitem], [onclick], label';
  for (const el of document.querySelectorAll(q)) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const st = getComputedStyle(el); if (st.visibility === 'hidden' || st.display === 'none' || +st.opacity === 0) continue;
    if (el.tagName === 'LABEL' && el.control) {       // 칸이 보이면 라벨은 빼고 칸만(라벨을 누르는 것은 칸을 누르는 것과 같음)
      const c = el.control.getBoundingClientRect(), cs = getComputedStyle(el.control);
      if (c.width >= 4 && c.height >= 4 && cs.visibility !== 'hidden' && +cs.opacity !== 0) continue;
    }
    const lab = el.labels && el.labels[0] ? el.labels[0].innerText : '';
    out.push({tag: el.tagName.toLowerCase(), type: el.type || '', text: clean(el.innerText || el.value || ''),
              label: clean(lab || el.getAttribute('aria-label') || ''), ph: clean(el.placeholder || ''),
              opts: el.tagName === 'SELECT' ? [...el.options].slice(0, 12).map(o => clean(o.text)) : undefined,
              x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2)});
    if (out.length >= 120) break;
  }
  return out;
}"""

SYSTEM = """너는 웹사이트 사용법 영상을 만들기 위해, 사람 대신 사이트를 한 번 직접 해 보이는 도우미다.
목표를 이루는 가장 짧고 평범한 순서로, 실제 사람이 하듯 한 번에 동작 하나씩 한다. 매번 지금 화면 사진과 누를 곳 목록을 받는다.
- click/hover/type/select 는 목록 번호(index)로. type 의 text 는 적을 값: 이름·전화·이메일 같은 개인정보는 '홍길동', '01012345678',
  'test@example.com' 같은 테스트용 값만. 비밀번호·인증번호·보안문자처럼 사람만 아는 값은 secret=true 로 하고 text 에 물을 말을 적는다.
- 화면에 없는 곳은 scroll(아래로 한 화면). 팝업·공지는 닫는다.
- 목표의 마지막 버튼(저장·등록·발송 등)까지 눌렀거나 더 할 것이 없으면 done(무엇을 했는지 한 줄). 저장은 프로그램이 막아 두었으니 눌러도 된다.
- 길을 못 찾거나 로그인 정보가 필요한데 없으면 ask 로 사람에게 묻고, 정말 안 되면 fail(이유).
- 결제·탈퇴·삭제·실제 발송처럼 되돌릴 수 없는 일은 목표에 있어도 하지 않고 done 으로 끝낸다."""


def store_secrets(sc: dict, values: list[str]) -> int:
    """장면 표의 '@보관함' 칸에, AI 시연 때 사람이 알려 준 비밀번호를 순서대로 넣어 둔다(확인 단계에서 다시 묻지 않게)."""
    from . import secrets as SEC
    url = sc.get("로그인주소") or sc.get("주소", "")
    n = 0
    for s in list(sc.get("미리하기") or []) + list(sc.get("장면") or []):
        for f in (s.get("칸") or [{"누를곳": s.get("누를곳") or s.get("대상", ""), "값": s.get("값", "")}]):
            if str(f.get("값", "")).startswith("@보관함") and n < len(values):
                SEC.put(SEC.key_for(url, str(f.get("누를곳") or f.get("대상") or ""), str(f["값"])), values[n])
                n += 1
    return n


def explore(llm, url: str, goal: str, ask=None, log=print, headless: bool = True, max_steps: int = MAX_STEPS,
            stop=None, tone: str = "차분", brand: str = "") -> dict:
    """AI가 시연하고 {scenario: 장면 표 dict, steps, cost, date} 를 돌려준다. ask(질문, 사진경로)->답: 사람에게 묻는 함수(없으면 묻는 즉시 멈춤)."""
    from .demo_record import DemoSession
    sess = DemoSession(url, headless=headless)
    pg = sess.page
    allow = {"once": False, "left": 0}     # 비밀번호를 적은 뒤 '다음 동작 하나' 동안만 저장 요청 한 번 허용(로그인)

    def guard(route):        # 둘러보는 동안 저장은 막는다(비밀번호를 넣은 바로 다음 한 번 = 로그인만 허용)
        r = route.request
        if r.method in ("POST", "PUT", "PATCH", "DELETE") and not allow["once"]:
            return route.abort()
        if r.method != "GET":
            allow["once"] = False
        return route.continue_()
    sess.ctx.route("**/*", guard)
    history: list[str] = []
    secrets_given: list[str] = []            # 사람이 알려 준 비밀번호(순서대로) → 끝나면 보관함에
    usage = {"in": 0, "out": 0}
    try:
        for step in range(max_steps):
            if allow["left"] > 0:
                allow["left"] -= 1
                if allow["left"] == 0:
                    allow["once"] = False          # 로그인에 안 쓰였으면 닫는다(다음 저장까지 열려 있지 않게)
            if stop and stop():
                raise RuntimeError("멈췄어요.")
            pg.wait_for_timeout(600)
            els = pg.evaluate(ELEMENTS_JS)
            shot = pg.screenshot(type="jpeg", quality=60)
            listing = "\n".join(f"[{i}] {e['tag']}{'/' + e['type'] if e['type'] else ''} '{e['text'] or e['label'] or e['ph']}'"
                                + (f" 라벨 '{e['label']}'" if e['label'] and e['text'] else "")
                                + (f" 항목 {e['opts']}" if e.get('opts') else "") for i, e in enumerate(els))
            content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": base64.b64encode(shot).decode()}},
                       {"type": "text", "text": f"목표: {goal}\n지금 주소: {pg.url}\n지금까지 한 것:\n" + ("\n".join(history[-12:]) or "(처음)")
                        + f"\n\n누를 곳 목록:\n{listing}\n\n다음 동작 하나를 골라."}]
            a = llm.parse(SYSTEM, content, Action, effort="medium", max_tokens=8000)
            usage["in"] += 4000; usage["out"] += 900
            log(f"[AI] {step + 1}. {a.kind} {a.index if a.index is not None else ''} {a.text if not a.secret else '(물어봄)'} — {a.reason}")
            if a.kind == "done":
                break
            if a.kind == "fail":
                raise RuntimeError(f"AI가 길을 찾지 못했어요: {a.text}")
            if a.kind == "ask" or (a.kind == "type" and a.secret):
                if not ask:
                    raise RuntimeError(f"사람의 도움이 필요해요: {a.text}")
                p = sess.ctx.pages[0]
                path = None
                try:
                    import tempfile
                    path = tempfile.mktemp(suffix=".png")
                    p.screenshot(path=path)
                except Exception:
                    pass
                ans = ask(a.text or "값을 알려 주세요.", path or "")
                if a.kind == "ask":
                    history.append(f"물어봄: {a.text} → 답을 받음")
                    continue
                a = Action(kind="type", index=a.index, text=ans, secret=True)
                if els[a.index]["type"] == "password" if a.index is not None and 0 <= a.index < len(els) else False:
                    secrets_given.append(ans)
            if a.kind == "scroll":
                pg.mouse.wheel(0, 700); history.append("아래로 스크롤"); continue
            if a.index is None or not 0 <= a.index < len(els):
                history.append(f"잘못된 번호 {a.index} — 다시 고름"); continue
            e = els[a.index]
            pg.mouse.move(e["x"], e["y"], steps=8)
            name = e["text"] or e["label"] or e["ph"] or e["tag"]
            if a.kind == "hover":
                history.append(f"'{name}' 위에 마우스"); continue
            if a.kind == "select":
                pg.mouse.click(e["x"], e["y"])
                loc = pg.locator("select").filter(has=pg.locator(f"option:text-is({json.dumps(a.text)})"))
                (loc.first if loc.count() else pg.locator("select").first).select_option(label=a.text)
                history.append(f"'{name}'에서 '{a.text}' 고름"); continue
            pg.mouse.click(e["x"], e["y"])
            if a.kind == "type":
                pg.keyboard.press("Control+A")
                pg.keyboard.type(a.text, delay=30)
                if a.secret and e["type"] == "password":
                    allow["once"], allow["left"] = True, 2            # 비밀번호 다음의 로그인 요청 한 번만(인증번호 칸은 해당 없음)
                history.append(f"'{name}'에 {'(비밀 값)' if a.secret else repr(a.text)} 적음")
            else:
                history.append(f"'{name}' 누름")
        else:
            log(f"[AI] {max_steps}번 안에 끝내지 못해 여기까지로 장면 표를 만들어요.")
        last_url = pg.url
        sc = sess.finish(topic=goal, brand=brand, tone=tone)
        store_secrets(sc, secrets_given)
    except Exception:
        try:
            sess.browser.close(); sess._p.stop()
        except Exception:
            pass
        raise
    usd = (usage["in"] * PRICE_IN + usage["out"] * PRICE_OUT) / 1e6
    return {"scenario": sc, "steps": len(history), "cost": won(usd), "date": time.strftime("%Y-%m-%d"), "last_url": last_url}
