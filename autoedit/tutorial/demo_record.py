"""한 번 해 보이기: 사람이 브라우저에서 평소처럼 한 번 하면, 화면은 찍지 않고 동작만 기록해 장면 표를 만든다 (DESIGN.md 4·5.1절).

- 누른 것의 보이는 글자·라벨·역할(버튼/링크/입력칸/체크/목록)과 누를 곳 후보(선택자)를 함께 저장한다.
- 정리: 같은 칸의 연속 입력은 마지막 값 하나로, 입력칸을 누른 클릭은 입력에 합침, 입력 바로 옆 버튼은 한 장면으로,
  잘못 누른 뒤 뒤로 가기, 두 번 누르기, 아무 일도 없는 곳 누르기는 버림.
- 비밀번호 칸 값은 기록하지 않는다(🔒, 녹화 때 보관함에서 꺼냄 — 6단계).
- 개인정보로 보이는 칸(이름·전화·생년월일·주소·이메일)은 자동으로 흐림 목록에 넣는다.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse

import yaml

from . import sentences as T

# 페이지에 넣는 기록 스크립트. 사람이 한 동작을 window.__tmRecord(이벤트) 로 파이썬에 넘긴다.
RECORDER_JS = r"""(() => {
  if (window.__tmInstalled) return; window.__tmInstalled = true;
  const send = e => { try { window.__tmRecord(e); } catch (_) {} };
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const short = s => { s = clean(s); return s.length > 40 ? s.slice(0, 40) : s; };
  const ACT = 'button, a, input, select, textarea, label, summary, [role=button], [role=link], [role=checkbox], [role=combobox], [role=option], [role=tab], [role=menuitem], [onclick], [tabindex]';
  function actionable(el) {
    let a = el.closest(ACT);
    if (a) return a;
    for (let e = el, i = 0; e && e !== document.body && i < 6; e = e.parentElement, i++)
      if (getComputedStyle(e).cursor === 'pointer') return e;      // 카드처럼 생긴 버튼
    return null;
  }
  function labelOf(el) {
    if (el.labels && el.labels[0]) return short(el.labels[0].innerText);
    const by = el.getAttribute('aria-labelledby');
    if (by) { const l = document.getElementById(by); if (l) return short(l.innerText); }
    if (el.getAttribute('aria-label')) return short(el.getAttribute('aria-label'));
    // 칸 위·앞에 붙은 글자 (라벨 태그 없이 만든 양식)
    let p = el.parentElement;
    for (let i = 0; p && i < 4; p = p.parentElement, i++) {
      const lab = p.querySelector('label, .label, legend, h3, h4, span, p');
      if (lab && !lab.contains(el) && clean(lab.innerText) && clean(lab.innerText).length < 30) return short(lab.innerText);
    }
    return '';
  }
  const uniq = s => { try { return document.querySelectorAll(s).length === 1; } catch (_) { return false; } };
  const q = s => s.replace(/'/g, "\\'");
  function selectors(el) {
    const out = [], tag = el.tagName.toLowerCase(), text = short(el.innerText);
    if (el.id && !/\d{3,}|:|^[0-9]/.test(el.id) && uniq('#' + CSS.escape(el.id))) out.push('#' + CSS.escape(el.id));
    const name = el.getAttribute('name');
    if (name && uniq(`${tag}[name="${name}"]`)) out.push(`${tag}[name=${/^[\w-]+$/.test(name) ? name : '"' + name + '"'}]`);
    const ph = el.getAttribute('placeholder');
    if (ph && uniq(`${tag}[placeholder="${ph}"]`)) out.push(`${tag}[placeholder="${ph}"]`);
    const al = el.getAttribute('aria-label');
    if (al && uniq(`[aria-label="${al}"]`)) out.push(`[aria-label="${al}"]`);
    if (text && ['button', 'a'].includes(tag)) out.push(`${tag}:has-text('${q(text)}')`);
    if (text && text.length <= 20) out.push(`text="${text.replace(/"/g, '\\"')}"`);
    // 마지막 수단: 문서 안 위치
    let path = [], e = el;
    while (e && e.nodeType === 1 && e !== document.documentElement && path.length < 8) {
      let i = 1, s = e; while ((s = s.previousElementSibling)) if (s.tagName === e.tagName) i++;
      path.unshift(`${e.tagName.toLowerCase()}:nth-of-type(${i})`); e = e.parentElement;
    }
    out.push('css=' + path.join(' > '));
    return out;
  }
  function info(el) {
    const r = el.getBoundingClientRect(), tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || '';
    const h = document.querySelector('h1, h2');
    const combos = [...document.querySelectorAll('div[role=combobox]')];
    const opts = [...document.querySelectorAll('[role=option]')];
    return { tag, role, type: (el.getAttribute('type') || '').toLowerCase(), name: el.getAttribute('name') || '',
      text: tag === 'input' ? (['submit', 'button'].includes((el.type || '').toLowerCase()) ? short(el.value) : '') : ['textarea', 'select'].includes(tag) ? '' : short(el.innerText), label: labelOf(el),
      placeholder: el.getAttribute('placeholder') || '', aria: el.getAttribute('aria-label') || '',
      sel: selectors(el), box: { x: r.x, y: r.y, w: r.width, h: r.height },
      combo: combos.indexOf(el.closest('div[role=combobox]')), option: opts.indexOf(el.closest('[role=option]')),
      url: location.href, heading: h ? short(h.innerText) : '', title: document.title, t: performance.timeOrigin + performance.now() };
  }
  document.addEventListener('click', ev => {
    const el = actionable(ev.target);
    const d = Object.assign({ ev: 'click', hit: !!el }, info(el || ev.target));
    // 체크 칸에 붙은 글자(label)를 누른 것: change 이벤트로 받으므로 표시만
    if (el && el.tagName === 'LABEL' && el.control && ['checkbox', 'radio'].includes(el.control.type)) d.forCheck = true;
    send(d);
  }, true);
  document.addEventListener('input', ev => {
    const el = ev.target; if (!el.matches || !el.matches('input, textarea')) return;
    if (['checkbox', 'radio'].includes((el.type || '').toLowerCase())) return;
    const d = info(el); d.ev = 'input'; d.value = el.type === 'password' ? '' : el.value; d.secret = el.type === 'password';
    send(d);
  }, true);
  document.addEventListener('change', ev => {
    const el = ev.target;
    if (el.tagName === 'SELECT') { const d = info(el); d.ev = 'select'; d.value = el.selectedOptions[0] ? clean(el.selectedOptions[0].text) : ''; send(d); }
    else if (['checkbox', 'radio'].includes((el.type || '').toLowerCase())) { const d = info(el); d.ev = 'check'; d.checked = el.checked; send(d); }
  }, true);
})()"""

PRIVATE = re.compile(r"이름|성명|성\b|name|전화|휴대|phone|mobile|tel|생년|생일|birth|dob|주소|address|이메일|e-?mail|인증번호|성별|gender|sex", re.I)


class DemoSession:
    """브라우저를 띄우고 동작을 모은다. finish() 로 장면 표(dict)를 돌려준다."""

    def __init__(self, url: str, headless: bool = False, viewport=(1920, 1080)):
        from playwright.sync_api import sync_playwright
        from .recorder import CHROME
        self.url = url
        self.events: list[dict] = []
        self.navs: list[tuple[float, str]] = []
        self._p = sync_playwright().start()
        self.browser = self._p.chromium.launch(executable_path=CHROME, headless=headless)
        self.ctx = self.browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
        self.ctx.expose_binding("__tmRecord", lambda src, e: self.events.append(e))
        self.ctx.add_init_script(RECORDER_JS)
        self.page = self.ctx.new_page()
        self.page.on("framenavigated", lambda f: f == self.page.main_frame and self.navs.append((time.time() * 1000, f.url)))
        self.page.goto(url, wait_until="networkidle", timeout=60000)

    def finish(self, topic: str = "", brand: str = "", tone: str = "차분", next_topic: str = "") -> dict:
        try:
            self.page.wait_for_timeout(300)
        except Exception:
            pass
        evs = list(self.events)
        self.browser.close()
        self._p.stop()
        return build_scenario(self.url, evs, self.navs, topic=topic, brand=brand, tone=tone, next_topic=next_topic)


# ── 정리 ──
def _target_name(e: dict) -> str:
    """사람이 부르는 이름: 버튼 글자 > 라벨 > 안내 글씨 > aria."""
    if e["ev"] == "check":
        # '이용 약관에 동의합니다' → '이용 약관 동의' (문장에 넣기 좋게)
        return re.sub(r"에\s*동의(합니다|함|해요)\.?$", " 동의", e["label"] or e["text"] or "체크 칸")
    if e["tag"] in ("input", "textarea", "select") or e["ev"] in ("input", "select"):
        return e["label"] or e["placeholder"] or e["aria"] or e["name"] or "입력칸"
    return e["text"] or e["aria"] or e["label"] or "이곳"


def _best_selector(e: dict) -> str:
    return e["sel"][0] if e["sel"] else ""


def clean_events(evs: list[dict], navs: list[tuple[float, str]]) -> list[dict]:
    """사람 동작을 장면 후보 목록으로 정리한다."""
    out: list[dict] = []
    for e in evs:
        kind = e["ev"]
        if kind == "click":
            if not e.get("hit"):
                continue                                     # 아무 일도 없는 곳 누르기
            if e["tag"] in ("input", "textarea") and e["type"] not in ("checkbox", "radio", "submit", "button"):
                continue                                     # 입력칸 누르기는 입력에 합침
            if e["tag"] == "select" or (e["tag"] == "input" and e["type"] in ("checkbox", "radio")):
                continue                                     # change 이벤트로 받음
            if e.get("forCheck"):
                continue                                     # 체크 칸 글자 누르기 = 체크(change 로 받음)
            if e["option"] >= 0 and out and out[-1]["action"] == "목록열기":
                prev = out.pop()                             # 선택 상자 열기 + 항목 고르기 = 선택
                out.append(dict(action="선택", t=e["t"], url=e["url"], heading=e["heading"], name=prev["name"],
                                picks=[{"상자": prev["combo"], "항목번호": e["option"]}], box=prev["box"]))
                continue
            if e["role"] == "combobox" or e["combo"] >= 0:
                out.append(dict(action="목록열기", t=e["t"], url=e["url"], heading=e["heading"], combo=e["combo"],
                                name=_target_name(dict(e, ev="select")), box=e["box"]))
                continue
            if out and out[-1]["action"] == "클릭" and out[-1]["sel"] == _best_selector(e) and e["t"] - out[-1]["t"] < 600:
                continue                                     # 두 번 누르기
            out.append(dict(action="클릭", t=e["t"], url=e["url"], heading=e["heading"], sel=_best_selector(e),
                            cands=e["sel"], name=_target_name(e), kind="링크" if e["tag"] == "a" else "버튼", box=e["box"]))
        elif kind == "input":
            sel = _best_selector(e)
            if out and out[-1]["action"] == "입력" and out[-1]["sel"] == sel:
                out[-1].update(value=e["value"], t=e["t"])     # 같은 칸 연속 입력 → 마지막 값
                continue
            out.append(dict(action="입력", t=e["t"], url=e["url"], heading=e["heading"], sel=sel, cands=e["sel"],
                            name=_target_name(e), value=e["value"], secret=e.get("secret", False), box=e["box"],
                            private=bool(PRIVATE.search(" ".join([e["label"], e["name"], e["placeholder"], e["type"]])))))
        elif kind == "select":
            out.append(dict(action="선택", t=e["t"], url=e["url"], heading=e["heading"], name=_target_name(e),
                            picks=[{"누를곳": _best_selector(e), "항목": e["value"]}], box=e["box"],
                            private=bool(PRIVATE.search(" ".join([e["label"], e["name"]])))))
        elif kind == "check":
            if out and out[-1]["action"] == "체크" and out[-1]["sel"] == _best_selector(e):
                out.pop()                                    # 켰다 껐다 → 마지막 상태만
                if not e.get("checked"):
                    continue
            if not e.get("checked"):
                continue
            out.append(dict(action="체크", t=e["t"], url=e["url"], heading=e["heading"], sel=_best_selector(e),
                            cands=e["sel"], name=_target_name(e), box=e["box"]))
    out = [o for o in out if o["action"] != "목록열기" and not (o["action"] == "입력" and not o["value"] and not o["secret"])]
    out = _drop_backtracks(out, navs)
    return _merge_buttons(out)


def _drop_backtracks(out: list[dict], navs: list[tuple[float, str]]) -> list[dict]:
    """잘못 누른 뒤 뒤로 가기: 클릭으로 A→B 로 갔다가 다른 동작 없이 A 로 돌아오면 그 클릭을 버린다."""
    keep = []
    for i, o in enumerate(out):
        if o["action"] == "클릭":
            nxt_t = out[i + 1]["t"] if i + 1 < len(out) else float("inf")
            after = [u for t, u in navs if o["t"] <= t < nxt_t]
            if len(after) >= 2 and _same_page(after[-1], o["url"]) and not _same_page(after[0], o["url"]):
                continue
        keep.append(o)
    return keep


def _same_page(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.netloc, pa.path.rstrip("/")) == (pb.netloc, pb.path.rstrip("/"))


def _merge_buttons(out: list[dict]) -> list[dict]:
    """입력 바로 뒤, 같은 줄의 버튼(중복확인·인증요청 등)은 한 장면으로: '아이디를 적고, 중복확인을 눌러 주세요.'"""
    res = []
    for o in out:
        p = res[-1] if res else None
        if (o["action"] == "클릭" and p and p["action"] == "입력" and "button" not in p and _same_page(o["url"], p["url"])
                and abs((o["box"]["y"] + o["box"]["h"] / 2) - (p["box"]["y"] + p["box"]["h"] / 2)) < max(p["box"]["h"], 20)
                and o["box"]["x"] > p["box"]["x"]):
            p["button"], p["button_name"] = o["sel"], o["name"]
            continue
        res.append(o)
    return res


def group_steps(scenes: list[dict]) -> tuple[list[int], list[str]]:
    """화면(주소)별로 단계를 나눈다. 장면 하나뿐인 화면(이동만 하는 곳)은 이어 붙여 '○○ 화면 찾기' 로, 최대 4단계."""
    groups: list[list[int]] = []
    for i, s in enumerate(scenes):
        if groups and _same_page(scenes[groups[-1][-1]]["url"], s["url"]):
            groups[-1].append(i)
        else:
            groups.append([i])
    merged: list[list[int]] = []
    for g in groups:
        if merged and len(g) == 1 and len(merged[-1]) >= 1 and all(scenes[j]["action"] == "클릭" for j in merged[-1] + g) \
                and (len(merged) < 2 or len(merged[-1]) <= 3):
            merged[-1] += g
        else:
            merged.append(g)
    last = merged[-1]
    k = max((i for i, j in enumerate(last) if scenes[j]["action"] in ("입력", "선택")), default=-1)
    if len(last) >= 5 and 0 <= k < len(last) - 1 and len(merged) < 4:
        merged[-1:] = [last[:k + 1], last[k + 1:]]         # 정보 입력 / 동의하고 누르기 (1편처럼)
    while len(merged) > 4:                                  # 가장 작은 이웃끼리 합침
        k = min(range(len(merged) - 1), key=lambda i: len(merged[i]) + len(merged[i + 1]))
        merged[k:k + 2] = [merged[k] + merged[k + 1]]
    step_of = [0] * len(scenes)
    names = []
    for n, g in enumerate(merged, 1):
        for j in g:
            step_of[j] = n
        names.append(_step_name(scenes, g, merged, n))
    return step_of, names


def _step_name(scenes, g, merged, n) -> str:
    acts = {scenes[j]["action"] for j in g}
    if acts == {"클릭"} and n < len(merged):                 # 이동만 하는 단계: 다음 화면 이름 + 찾기
        nxt = scenes[merged[n][0]]
        return f"{_short(nxt['heading']) or _short(scenes[g[-1]]['name'])} 화면 찾기"
    if "입력" in acts or "선택" in acts:
        h = _short(scenes[g[0]]["heading"]) or "정보"
        return f"{h}하기" if h.endswith(("입력", "작성")) else f"{h} 입력하기"
    if n == len(merged) and scenes[g[-1]]["action"] == "클릭":
        last = _short(scenes[g[-1]]["name"], 8)
        return f"동의하고 {last}" if "체크" in acts else f"{last} 누르기"
    return f"{n}단계"


def _short(s: str, n: int = 12) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n].rstrip()


def build_scenario(url: str, evs: list[dict], navs, topic: str = "", brand: str = "", tone: str = "차분",
                   next_topic: str = "") -> dict:
    scenes = clean_events(evs, navs)
    if not scenes:
        raise ValueError("기록된 동작이 없어요. 브라우저에서 한 번 해 보신 뒤 [■ 끝]을 눌러 주세요.")
    step_of, step_names = group_steps(scenes)
    host = urlparse(url).netloc
    from .scenario import load_brand
    b = load_brand(brand or "basic")
    spoken = b.spoken or b.name
    if not topic:
        topic = f"{_short(scenes[-1]['heading'], 20) or host} 방법"
    intro, outro = T.intro_outro(topic, len(step_names), spoken, next_topic)
    out_scenes = []
    privacy, block_from = [], ""
    for i, s in enumerate(scenes):
        key = f"S{i + 1}"
        d = {"키": key, "단계": step_of[i]}
        act = s["action"]
        if act in ("클릭", "체크"):
            d.update(동작=act, 대상=s["name"], 누를곳=s["sel"])
            line = T.scene_line(act, s["name"], kind=s.get("kind", ""), first=i == 0, last=i == len(scenes) - 1, tone=tone)
            nxt = scenes[i + 1] if i + 1 < len(scenes) else None
            if nxt and not _same_page(nxt["url"], s["url"]):
                d["다음주소"] = "**" + (urlparse(nxt["url"]).path or "/")
        elif act == "입력":
            val = "@보관함" if s["secret"] else s["value"]
            d.update(동작="입력", 대상=s["name"], 칸=[{"누를곳": s["sel"], "값": val}])
            if s.get("button"):
                d["버튼"] = s["button"]
            line = T.scene_line("입력", s["name"], button=s.get("button_name", ""), first=i == 0, tone=tone)
            if s.get("private") or s["secret"]:
                privacy.append(s["sel"])
            if not block_from:
                block_from = urlparse(s["url"]).path
        else:   # 선택
            d.update(동작="선택", 대상=s["name"], 목록=s["picks"])
            line = T.scene_line("선택", s["name"], first=i == 0, tone=tone)
            if s.get("private"):
                privacy += [p["누를곳"] for p in s["picks"] if "누를곳" in p]
        d["말"] = line
        out_scenes.append(d)
    sc = {"제목": T.title(topic, len(step_names)), "주소": url, "브랜드": brand or "basic", "시작상태": "로그아웃",
          "단계이름": step_names, "인트로": [{"키": "I1", "말": intro[0]}, {"키": "I2", "말": intro[1]}],
          "아웃트로": [{"키": "O1", "말": outro[0]}, {"키": "O2", "말": outro[1]}], "장면": out_scenes,
          "파일이름": re.sub(r"[^\w가-힣-]+", "_", f"{host.split('.')[0]}_{T.topic_words(topic)}").strip("_")}
    if next_topic:
        sc["다음편"] = next_topic
    if privacy:
        sc["개인정보칸"] = sorted(set(privacy), key=privacy.index)
    if block_from and block_from != "/":
        sc["요청차단"] = block_from                          # 입력이 시작되는 화면부터 저장·발송 요청 차단
    return sc


def save(sc: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "# 한 번 해 보이기로 만든 장면 표. '말'만 다듬으면 됩니다(누를 곳·동작은 그대로 두세요).\n"
    path.write_text(head + yaml.safe_dump(sc, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
    return path
