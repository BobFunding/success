// 튜토리얼 메이커 화면 (시안: tutorials/mock/tutorial-maker-mock.html)
// 원칙(DESIGN.md 0.1): 한 화면에 주 버튼 하나, 추천값이 다 골라져 있음, 사람이 볼 것만 알림, 쉬운 말.
const STEPS = [
  { t: "시작", d: "주소 넣고 방법 고르기" },
  { t: "확인", d: "자동으로 만든 문장 보기" },
  { t: "선택", d: "목소리·꾸미기 고르기" },
  { t: "만들기", d: "알아서 녹화·편집" },
  { t: "결과·내보내기", d: "영상과 파일 받기" },
];
const MAKE_STAGES = ["목소리 만들기", "발음 검사", "리허설", "자동 녹화", "화면 연출", "인트로·아웃트로·자막", "출력", "자동 검수"];
const PREVIEW_STAGES = ["목소리 만들기", "발음 검사", "리허설", "자동 녹화", "화면 연출", "인트로·아웃트로·자막", "출력"];
const QA_CHIP = { ok: "ok", warn: "warn", fail: "warn" };
function qaCard(q, title) {
  if (!q) return "";
  const bad = q["항목"].filter(i => i["판정"] !== "ok");
  return `<section class="card"><h2>${title}</h2><p class="lead">1편 때 사람이 하던 확인을 프로그램이 했어요.</p>
    <div class="${bad.length ? "verdict has-warn" : "summary"}" style="margin-bottom:var(--s2)">${bad.length ? `⚠ ${bad.length}개 확인 필요` : `✓ ${q["항목"].length}개 모두 통과`}</div>
    <div class="qa">${q["항목"].map(i => `<div><span>${esc(i["이름"])}</span><span class="chip ${QA_CHIP[i["판정"]]}">${i["판정"] === "ok" ? "✓ " : "⚠ "}${esc(i["내용"])}</span></div>`).join("")}</div>
    ${q["사진"] ? `<details style="margin-top:var(--s2)"><summary>장면별 사진<span>클릭 순간마다 한 장</span></summary><img src="${fileUrl(q["사진"])}" alt="장면별 사진" style="width:100%;border-radius:8px"></details>` : ""}</section>`;
}
const S = { cur: 0, st: null, proj: null, removed: [], choices: { voice: "현수 · 차분", deco: "brand", speed: 0, subtitles: true },
            job: null, url: "https://taekwonworld.net", title: "", poll: null, dirty: false, brandSel: "", tab: "B" };
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fileUrl = p => "/file?path=" + encodeURIComponent(p);
const mins = s => s < 90 ? "1분 안쪽" : `약 ${Math.round(s / 60)}분`;
const store = { get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d } catch (_) { return d } },
                set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)) } catch (_) {} } };

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({ error: "응답을 읽지 못했어요." }));
  return j;
}
async function loadState() { S.st = await api("/api/state"); S.job = S.st.job; }
async function openProject(path, step = 1) {
  S.proj = await api("/api/project?path=" + encodeURIComponent(path));
  S.removed = [];
  S.choices = Object.assign({ voice: S.st.voices[0], deco: "brand", speed: 0, subtitles: true }, S.proj.choices || {});
  go(step);
}

// ── 단계 메뉴 ──
function reachable(i) { return i === 0 || (S.proj && (i <= 3 || !!S.proj.video)); }
function nav() {
  $("#nav").innerHTML = STEPS.map((s, i) => `<button type="button" class="step ${i === S.cur ? "on" : ""} ${i < S.cur ? "done" : ""}" data-i="${i}" ${reachable(i) ? "" : "disabled"}>
    <span class="n">${i < S.cur ? "✓" : i + 1}</span><span><b>${s.t}</b><small>${s.d}</small></span></button>`).join("");
  $("#nav").querySelectorAll(".step").forEach(b => b.onclick = () => reachable(+b.dataset.i) && go(+b.dataset.i));
}
async function go(i) {
  if (S.cur === 1 && i !== 1 && S.dirty) { if (!(await saveScenario())) return; }
  S.cur = i; nav(); render(); window.scrollTo({ top: 0, behavior: "smooth" });
}
function foot(prev, nextLabel, nextId = "next", disabled = false) {
  return `<div class="foot">${prev ? '<button class="ghost" type="button" id="prev">← 이전</button>' : "<span></span>"}
    ${nextLabel ? `<button class="primary" type="button" id="${nextId}" ${disabled ? "disabled" : ""}>${nextLabel}</button>` : ""}</div>`;
}

// ── 1. 시작 ──
function viewStart() {
  const j = S.job || {};
  const rec = j.kind === "demo" && j.running;
  const tip = store.get("tipDone", false) ? "" : `<div class="tip"><span>처음이세요? ① 사이트 주소 넣기 → ② [한 번 해 보이기] → ③ [다음]만 누르면 영상이 완성돼요.</span><button class="x" id="tipX" type="button">알겠어요</button></div>`;
  const projects = (S.st.projects || []).map(p => `<div class="pitem"><span>${esc(p.title)} ${p.example ? '<span class="chip">예시 · 1편</span>' : ""}
      <small>장면 ${p.scenes}개${p.video ? " · 영상 있음" : ""}</small></span><button class="ghost" type="button" data-open="${esc(p.path)}">열기</button></div>`).join("");
  const demo = rec ? `
    <div class="browser"><div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span>${esc(S.url)}</span>
      <span class="live"><i></i>기록 중 · 동작 ${j.count || 0}개</span></div>
      <div class="site"><div class="fake" style="width:40%"></div><div class="fake" style="width:70%"></div><div class="fake" style="width:55%"></div></div></div>
    <div class="foot"><span class="hint">따로 뜬 브라우저 창에서 평소처럼 한 번 해 보세요. 화면은 찍지 않고 동작만 기록합니다. 실수해도 괜찮아요.</span>
      <button class="primary rec" type="button" id="stop">■ 끝</button></div>`
    : `${j.kind === "demo" && j.error ? `<div class="err">${esc(j.error)}</div>` : ""}
    <p class="lead">[한 번 해 보이기]를 누르면 브라우저 창이 따로 뜹니다. 평소처럼 한 번 하고 [■ 끝]을 누르세요. 비밀번호는 기록하지 않아요.</p>
    ${foot(false, "🖱 한 번 해 보이기", "demoGo")}`;
  return `${tip}
<section class="card"><h2>어떤 사이트의 사용법을 만들까요?</h2>
  <p class="lead">주소를 넣고 방법을 고르세요. 제목은 비워 두면 자동으로 제안합니다.</p>
  <div class="row"><label class="f" for="url">사이트 주소<input type="text" id="url" value="${esc(S.url)}" placeholder="https://"></label>
    <label class="f" for="ttl">영상 주제 (선택)<input type="text" id="ttl" value="${esc(S.title)}" placeholder="예: 관장님 회원가입 — 비워 두면 자동 제안"></label></div>
</section>
<section class="modes">
  <button type="button" class="mode on" id="mDemo"><b>🖱 한 번 해 보이기</b><span>내가 직접 한 번 보여 주기. AI 없이, 비용 없이</span></button>
  <button type="button" class="mode" disabled title="AI 도우미는 다음 업데이트에서 열려요"><b>✨ AI에게 맡기기 <em class="soon">준비 중</em></b><span>한 줄로 부탁하면 AI가 사이트를 둘러보고 채움</span></button>
</section>
<section class="card"><h2>한 번 해 보이기</h2>${demo}</section>
<section class="card"><h2>지난 작업</h2><p class="lead">열어서 문장 하나만 고치고 다시 만들 수 있어요.</p><div class="plist">${projects || '<p class="hint">아직 없어요.</p>'}</div></section>`;
}

// ── 2. 확인 ──
const ACT_NAME = { "클릭": "클릭", "체크": "체크", "입력": "입력", "선택": "고르기", "스크롤": "스크롤", "보여주기": "보여 주기", "대기": "기다리기" };
function targetCell(s, priv) {
  const vals = (s["칸"] || []).map(f => {
    const v = String(f["값"] ?? "");
    if (v.startsWith("@보관함") || /pass(word)?|passwd|\bpw\d?\b|비밀번호/i.test(String(f["누를곳"]) + " " + (s["대상"] || "")))
      return '<span class="chip blur">🔒 비밀번호</span>';             // 비밀번호는 화면에 절대 보이지 않게
    if (priv.has(f["누를곳"])) return '<span class="chip blur">흐림 처리</span>';
    return `<span class="chip">${esc(v)}</span>`;
  }).join(" ");
  const btn = s["버튼"] ? ` → <span class="chip">${esc(s["버튼이름"] || String(s["버튼"]).replace(/^.*has-text\('(.+)'\).*$/, "$1"))}</span>` : "";
  return `${esc(s["대상"] || "")} ${vals}${btn}`;
}
function viewCheck() {
  const p = S.proj, d = p.scenario, reh = p.rehearsal, priv = new Set(d["개인정보칸"] || []);
  const pron = {}; ((p.pronunciation || {}).items || []).forEach(i => { if (!i.ok) pron[i["키"]] = i; });
  const scenes = d["장면"] || [];
  const blk = d["요청차단"] || "";
  const rows = scenes.map((s, i) => {
    const bad = reh && !reh.ok && reh["장면"] === i + 1;
    const ok = reh && (reh.ok || reh["장면"] > i + 1);
    const guard = blk && i === scenes.length - 1 && s["동작"] === "클릭";
    const status = bad ? '<span class="chip warn">✗ 못 찾음</span>' : guard ? '<span class="chip warn">저장 차단</span>' : ok ? '<span class="chip ok">✓ 찾음</span>' : '<span class="hint">—</span>';
    return `<tr class="${bad ? "bad" : ""}"><td class="num">${String(i + 1).padStart(2, "0")}</td>
      <td class="say"><div contenteditable="true" data-say="${i}">${esc(s["말"])}</div>${s["말풍선"] ? `<div style="margin-top:4px"><span class="chip warn">말풍선 · ${esc(s["말풍선"])}</span></div>` : ""}
        ${bad ? `<div class="hint" style="color:var(--red)">${esc(reh["메시지"])}</div>` : ""}
        ${pron[s["키"]] ? `<div class="hint" style="color:var(--warn)">⚠ 발음: '${esc(pron[s["키"]]["다르게"].map(w => w["단어"]).join("', '"))}' 이(가) 다르게 들려요 — "${esc(pron[s["키"]]["들림"])}". ${esc(pron[s["키"]]["다르게"][0]["제안"])}</div>` : ""}</td>
      <td>${ACT_NAME[s["동작"]] || esc(s["동작"])}</td><td>${targetCell(s, priv)}</td><td>${status}</td>
      <td><button class="x" type="button" data-del="${i}" title="이 장면 지우기">✕</button></td></tr>`;
  }).join("");
  const steps = (d["단계이름"] || []).map((n, i) => `<label class="chip" style="gap:6px">${i + 1} <input class="stepname" data-step="${i}" value="${esc(n)}" aria-label="${i + 1}단계 이름"></label>`).join("");
  const privChips = [...priv].map(x => `<span class="chip blur">${esc(nameOfField(scenes, x))}</span>`).join("") || '<span class="hint">없음</span>';
  const warn = (p.warnings || []).map(w => `<div class="verdict has-warn">⚠ ${esc(w)}</div>`).join("")
    + (((p.pronunciation || {}).items || []).filter(i => !i.ok && !(d["장면"] || []).some(s => s["키"] === i["키"])).map(i => `<div class="verdict has-warn">⚠ 발음(${esc(i["키"])}): "${esc(i["말"])}" 이 "${esc(i["들림"])}" 로 들려요. 인트로·아웃트로 문장은 브랜드 인사말에서 고칠 수 있어요.</div>`).join(""));
  const rehBox = reh ? (reh.ok ? `<div class="summary"><span>✓ 리허설 통과 · 누를 곳 ${scenes.length}곳 모두 찾음</span></div>`
    : `<div class="err"><b>${reh["장면"]}번 장면에서 멈췄어요.</b><span>${esc(reh["메시지"])}</span></div>`) : "";
  const running = S.job && S.job.running && S.job.kind === "rehearse";
  return `${p.error ? `<div class="err">${esc(p.error)}</div>` : ""}
<section class="card"><h2>이렇게 말하고, 이렇게 누릅니다</h2>
  <p class="lead">누른 버튼 글자를 보고 문장을 자동으로 만들었어요. 문장을 눌러 바로 고칠 수 있어요. 누를 곳·동작은 그대로 두세요.${p.example ? " (1편 예시 — 고치면 사본으로 저장돼요)" : ""}</p>
  <div class="scroll"><table><thead><tr><th>#</th><th>할 말</th><th>동작</th><th>누른 곳</th><th>리허설</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
  ${S.removed.length ? `<div class="foot"><span class="hint">지운 장면 ${S.removed.length}개</span><button class="ghost" type="button" id="undo">↶ 지운 장면 되살리기</button></div>` : ""}
</section>
${warn}${rehBox}
<section class="row">
  <div class="card"><h2>단계 묶음</h2><p class="lead">영상 왼쪽 위에 표시됩니다. 눌러서 이름을 고칠 수 있어요.</p><div class="opts">${steps}</div></div>
  <div class="card"><h2>개인정보</h2><p class="lead">녹화할 때부터 글자를 흐리게 합니다.</p><div class="opts">${privChips}</div></div>
</section>
<section class="card"><h2>시작 화면</h2><p class="lead">로그인 과정을 영상에 넣을지 고르세요.</p>
  <div class="opts"><label class="opt"><input type="radio" name="st" checked><span>로그아웃 상태에서 (로그인도 보여 주기)</span></label>
  <label class="opt"><input type="radio" name="st" disabled><span>로그인한 상태에서 <em class="soon">준비 중</em></span></label></div></section>
<div class="foot"><button class="ghost" type="button" id="prev">← 이전</button>
  <span style="display:flex;gap:8px;flex-wrap:wrap"><button class="ghost" type="button" id="reh" ${running ? "disabled" : ""}>${running ? "리허설 중…" : "리허설 해 보기"}</button>
  <button class="primary" type="button" id="next">다음 →</button></span></div>`;
}
function nameOfField(scenes, sel) {
  // 칸 이름: 잘 알려진 이름표(name=...) 먼저, 없으면 그 칸이 있는 장면의 대상
  const n = String(sel).replace(/^.*name=["']?([\w-]+).*$/, "$1").replace(/^#/, "");
  const KNOWN = { dob: "생년월일", birth: "생년월일", birthday: "생년월일", sex_code: "성별", sex: "성별", gender: "성별",
                  last_name: "성", first_name: "이름", user_name: "이름", name: "이름", phone: "휴대전화", phone_number: "휴대전화",
                  mobile: "휴대전화", email: "이메일", number_by_user: "인증번호", address: "주소", pw: "비밀번호", pw2: "비밀번호 확인" };
  if (KNOWN[n]) return KNOWN[n];
  for (const s of scenes) for (const f of (s["칸"] || [])) if (f["누를곳"] === sel) return s["대상"] || n;
  for (const s of scenes) for (const f of (s["목록"] || [])) if (f["누를곳"] === sel) return s["대상"] || n;
  return n;
}
async function saveScenario() {
  const r = await api("/api/project/save", { path: S.proj.path, scenario: S.proj.scenario });
  if (!r.ok) { alert(r.error || "저장하지 못했어요."); return false; }
  S.dirty = false;
  if (r.path !== S.proj.path) S.proj.path = r.path;
  const fresh = await api("/api/project?path=" + encodeURIComponent(S.proj.path));
  S.proj = Object.assign(S.proj, fresh);
  return true;
}

// ── 3. 선택 ──
function radios(name, list, checked, disabled = []) {
  return list.map((t, i) => `<label class="opt"><input type="radio" name="${name}" value="${esc(t)}" ${t === checked ? "checked" : ""} ${disabled.includes(t) ? "disabled" : ""}><span>${esc(t)}${disabled.includes(t) ? ' <em class="soon">준비 중</em>' : ""}</span></label>`).join("");
}
function viewChoose() {
  const c = S.choices;
  const saved = store.get("brand", "");
  const brand = c.brand || (saved && S.st.brands.includes(saved) ? saved : (S.proj.scenario["브랜드"] || "basic"));
  c.brand = brand;
  const brandName = brand === "taekwonworld" ? "태권월드" : brand;
  const voices = S.st.voices.map(v => `<label class="opt"><input type="radio" name="v" value="${esc(v)}" ${v === c.voice ? "checked" : ""}><span>${esc(v)} <em class="play" data-play="${esc(v)}">▶ 첫 문장 듣기</em></span></label>`).join("")
    + `<label class="opt"><input type="radio" name="v" disabled><span>내 목소리로 녹음 <em class="soon">준비 중</em></span></label>`
    + `<label class="opt"><input type="radio" name="v" disabled><span>목소리 없이 자막만 <em class="soon">준비 중</em></span></label>`;
  return `<section class="card"><h2>만들기 전에 골라 주세요</h2>
  <p class="lead">추천값이 이미 골라져 있어요. 그대로 [만들기]를 눌러도 됩니다.</p>
  <div class="group"><div class="k">목소리</div><div><div class="opts">${voices}</div><audio id="aud" hidden></audio><div class="hint" id="playHint"></div></div></div>
  <div class="group"><div class="k">영상 모양</div><div class="opts">${radios("sh", ["가로 · 유튜브", "세로 · 쇼츠", "둘 다"], "가로 · 유튜브", ["세로 · 쇼츠", "둘 다"])}</div></div>
  <div class="group"><div class="k">꾸미기</div><div><div class="opts">
    ${brand === "basic" ? "" : `<label class="opt"><input type="radio" name="dc" value="brand" ${c.deco !== "basic" ? "checked" : ""}><span>우리 브랜드 · ${esc(brandName)}</span></label>`}
    <label class="opt"><input type="radio" name="dc" value="basic" ${c.deco === "basic" || brand === "basic" ? "checked" : ""}><span>기본</span></label>
    <label class="opt"><input type="radio" name="dc" disabled><span>＋ 참고 영상 스타일 <em class="soon">준비 중</em></span></label></div>
    ${brand === "basic" ? '<div class="hint" style="margin-top:6px">⚙ 설정에서 우리 브랜드(로고·색·목소리)를 만들어 두면 여기서 고를 수 있어요.</div>' : ""}</div></div></div>
  <details style="margin-top:var(--s2)"><summary>더 고르기<span>말 빠르기 · 자막 (안 건드려도 됨)</span></summary>
    <div style="padding:0 14px 8px">
      <div class="group"><div class="k">말 빠르기</div><div><input type="range" id="spd" min="-10" max="10" step="2" value="${c.speed}" aria-label="말 빠르기"><div class="scale"><span>천천히</span><span>보통</span><span>빠르게</span></div></div></div>
      <div class="group"><div class="k">자막</div><div class="opts">${radios("sb", ["켜기", "끄기"], c.subtitles ? "켜기" : "끄기")}</div></div>
    </div></details>
</section>
<div class="foot"><button class="ghost" type="button" id="prev">← 이전</button>
  <span style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button class="ghost" type="button" id="quick" title="저화질로 먼저 빠르게 봅니다. 녹화는 최종본에서 그대로 다시 써요.">빠른 미리보기</button>
  <button class="primary" type="button" id="next">만들기 →</button></span></div>`;
}

// ── 4. 만들기 ──
function viewMake() {
  const j = S.job || {};
  const mine = j.kind === "make";
  const done = new Set(mine ? j.done || [] : []);
  const pv = mine && j.preview;
  const items = (pv ? PREVIEW_STAGES : MAKE_STAGES).map(n => {
    const st = !mine ? "" : (done.has(n) || (j.ok && !j.running)) ? "done" : j.stage === n && j.running ? "run" : "";
    const note = st === "run" ? (n === "자동 녹화" ? "보이지 않는 창에서 녹화 중" : "진행 중") : st === "done" ? "✓" : "";
    return `<div class="pi ${st}"><span class="ic">${st === "done" ? "✓" : ""}</span><span>${n}</span><small>${note}</small></div>`;
  }).join("");
  const pct = !mine ? 0 : j.ok ? 100 : Math.round(100 * (done.size + 0.5) / (pv ? PREVIEW_STAGES : MAKE_STAGES).length);
  const slow = S.st.capture === "frames" ? "이 컴퓨터에서는 화면을 한 장씩 찍어서 녹화가 조금 오래 걸려요. " : "";
  const eta = mine && j.running && j.eta != null ? `<div class="summary"><span>⏱ ${mins(j.eta)} 남았어요</span><small>${slow}다른 일을 하셔도 됩니다.</small></div>` : "";
  const err = mine && j.ok === false ? `<div class="err"><b>멈췄어요.</b><span>${esc(j.error)}</span>${j.scene ? '<button class="ghost" type="button" id="fix">장면 표에서 고치기</button>' : ""}</div>` : "";
  const warn = mine && j.ok && j.result && (j.result.warnings || []).length ? j.result.warnings.map(w => `<div class="verdict has-warn">⚠ ${esc(w)}</div>`).join("") : "";
  if (pv && j.ok) return `<section class="card"><h2>빠른 미리보기</h2>
    <p class="lead">저화질 미리보기예요. 괜찮으면 최종본을 만드세요 — 이미 찍은 녹화를 그대로 써서 녹화는 다시 안 해요.</p>
    <video controls autoplay preload="metadata" src="${fileUrl(j.result.final)}"></video></section>${warn}
    <div class="foot"><button class="ghost" type="button" id="toCheck">← 문장 고치기</button><button class="primary" type="button" id="final">이대로 최종본 만들기 →</button></div>`;
  return `<section class="card"><h2>${mine && j.ok ? "다 만들었어요" : pv ? "빠른 미리보기를 만들고 있어요" : "만들고 있어요"}</h2>
  <p class="lead">녹화는 보이지 않는 브라우저 창에서 프로그램이 직접 조작합니다. 마우스를 건드려도 괜찮아요. 저장·발송 요청은 막혀 있어요.</p>
  <div class="bar-out" aria-hidden="true"><div class="bar-fill" style="width:${pct}%"></div></div>
  <div class="prog" style="margin-top:var(--s2)">${items}</div>
  ${eta ? `<div style="margin-top:var(--s2)">${eta}</div>` : ""}
</section>${err}${warn}${mine && j.ok && j.result ? qaCard(j.result.qa, "자동 검수 결과") : ""}
${foot(true, "결과 보기 →", "next", !(mine && j.ok))}`;
}

// ── 5. 결과 ──
function viewResult() {
  const r = (S.job && S.job.kind === "make" && S.job.ok && S.job.result && !S.job.result.preview && S.job.result) || null;
  const video = r ? r.final : S.proj.video;
  const files = r ? r.files : (S.proj.files || [video]);
  const chap = r ? r.chapters : (S.proj.chapters || []);
  const label = f => f.endsWith("_1440p60.mp4") ? ["영상 (유튜브용)", "1440p"] : f.endsWith("_1080p30.mp4") ? ["영상 사본", "1080p"]
    : f.endsWith(".srt") ? ["자막", ".srt"] : f.endsWith(".txt") ? ["유튜브 챕터", ".txt"] : [f.split(/[\\/]/).pop(), ""];
  return `<section class="card"><h2>완성됐어요</h2>
  <p class="lead">${r ? `${Math.floor(r.total / 60)}분 ${Math.round(r.total % 60)}초 · 1440p 60fps · 챕터 ${chap.length}개` : "지난번에 만든 영상"}</p>
  <div class="row3" style="grid-template-columns:minmax(0,2fr) minmax(0,1fr)">
    <video controls preload="metadata" src="${fileUrl(video)}" poster="${fileUrl(video.replace(/_1440p60\.mp4$/, "_poster.jpg"))}"></video>
    <div class="files">${files.filter(Boolean).map(f => { const [a, b] = label(f); return `<div class="file"><span>${esc(a)}</span><small>${b}</small></div>`; }).join("")}
      <button class="ghost" type="button" id="folder">📁 폴더 열기</button></div>
  </div>
  ${chap.length ? `<details style="margin-top:var(--s2)"><summary>유튜브 챕터<span>설명란에 붙여 넣기</span></summary><div class="checks" style="flex-direction:column;align-items:flex-start"><pre style="margin:0;font-family:var(--body);line-height:1.7">${esc(chap.join("\n"))}</pre><button class="ghost" type="button" id="copyChap">복사</button></div></details>` : ""}
</section>
${qaCard((r && r.qa) || S.proj.qa, "자동 검수")}
<section class="card"><h2>어디에 올릴까요?</h2>
  <p class="lead">올릴 곳을 고르면 파일과 글이 자동으로 준비되는 기능은 다음 업데이트에서 열려요. 지금은 위 파일을 그대로 올리시면 됩니다.</p>
  <div class="verdict">✓ 유튜브에 바로 올릴 수 있는 규격(1440p 60fps, H.264, 자막 .srt, 챕터)으로 만들었어요.</div>
</section>
<div class="foot"><button class="ghost" type="button" id="prev">← 이전</button><button class="ghost" type="button" id="again">문장 고치고 다시 만들기</button></div>`;
}

// ── 그리기 ──
function render() {
  const V = [viewStart, viewCheck, viewChoose, viewMake, viewResult];
  $("#main").innerHTML = V[S.cur]();
  const on = (id, fn) => { const e = $(id); if (e) e.onclick = fn; };
  on("#prev", () => go(S.cur - 1));
  if (S.cur === 0) {
    on("#tipX", () => { store.set("tipDone", true); render(); });
    $("#url").oninput = e => S.url = e.target.value.trim();
    $("#ttl").oninput = e => S.title = e.target.value;
    on("#demoGo", async () => {
      if (!/^https?:\/\//.test(S.url)) { alert("사이트 주소를 http:// 또는 https:// 로 시작하게 적어 주세요."); return; }
      const r = await api("/api/demo/start", { url: S.url, topic: S.title, brand: S.st.brands.includes(store.get("brand", "")) ? store.get("brand", "") : "" });
      if (!r.ok) { alert(r.error); return; }
      startPoll();
    });
    on("#stop", async () => { await api("/api/demo/stop", {}); });
    document.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openProject(b.dataset.open));
  }
  if (S.cur === 1) {
    document.querySelectorAll("[data-say]").forEach(el => el.oninput = () => { S.proj.scenario["장면"][+el.dataset.say]["말"] = el.innerText.trim(); S.dirty = true; });
    document.querySelectorAll("[data-step]").forEach(el => el.oninput = () => { S.proj.scenario["단계이름"][+el.dataset.step] = el.value; S.dirty = true; });
    document.querySelectorAll("[data-del]").forEach(b => b.onclick = () => {
      const i = +b.dataset.del, sc = S.proj.scenario["장면"];
      S.removed.push({ i, s: sc.splice(i, 1)[0] }); S.dirty = true; render();
    });
    on("#undo", () => { const x = S.removed.pop(); S.proj.scenario["장면"].splice(x.i, 0, x.s); S.dirty = true; render(); });
    on("#reh", async () => { if (S.dirty && !(await saveScenario())) return; await api("/api/rehearse", { path: S.proj.path, choices: S.choices }); startPoll(); render(); });
    on("#next", () => go(2));
  }
  if (S.cur === 2) {
    document.querySelectorAll('input[name=v]').forEach(r => r.onchange = () => S.choices.voice = r.value);
    document.querySelectorAll('input[name=dc]').forEach(r => r.onchange = () => S.choices.deco = r.value);
    document.querySelectorAll('input[name=sb]').forEach(r => r.onchange = () => S.choices.subtitles = r.value === "켜기");
    $("#spd").oninput = e => S.choices.speed = +e.target.value;
    document.querySelectorAll("[data-play]").forEach(b => b.onclick = async ev => {
      ev.preventDefault(); ev.stopPropagation();
      $("#playHint").textContent = "목소리를 만드는 중…";
      const r = await api("/api/voice", { path: S.proj.path, voice: b.dataset.play, speed: S.choices.speed });
      if (!r.wav) { $("#playHint").textContent = r.error || "목소리를 만들지 못했어요(인터넷 연결 확인)."; return; }
      $("#playHint").textContent = ""; const a = $("#aud"); a.src = fileUrl(r.wav); a.play();
    });
    const start = async preview => {
      const r = await api("/api/make", { path: S.proj.path, choices: S.choices, preview });
      if (!r.ok) { alert(r.error || "시작하지 못했어요."); return; }
      S.job = { kind: "make", running: true, done: [], preview }; go(3); startPoll();
    };
    on("#next", () => start(false));
    on("#quick", () => start(true));
  }
  if (S.cur === 3) {
    on("#next", () => go(4));
    on("#toCheck", () => go(1));
    on("#final", async () => {
      const r = await api("/api/make", { path: S.proj.path, choices: S.choices, preview: false });
      if (!r.ok) { alert(r.error || "시작하지 못했어요."); return; }
      S.job = { kind: "make", running: true, done: [], preview: false }; render(); startPoll();
    });
    on("#fix", async () => { await openProject(S.proj.path, 1); });
  }
  if (S.cur === 4) {
    on("#folder", () => api("/api/open", { path: S.proj.work }));
    on("#again", () => go(1));
    on("#copyChap", () => navigator.clipboard && navigator.clipboard.writeText($("pre").innerText));
  }
}

// ── 진행 상황 ──
function startPoll() {
  clearInterval(S.poll);
  S.poll = setInterval(async () => {
    const j = await api("/api/job");
    const was = S.job;
    S.job = j;
    if (j.kind === "demo" && !j.running && was && was.running) {
      clearInterval(S.poll);
      if (j.ok) { await loadState(); await openProject(j.result.path, 1); return; }
    }
    if (j.kind === "rehearse" && !j.running && was && was.running) {
      clearInterval(S.poll);
      S.proj = Object.assign(S.proj, await api("/api/project?path=" + encodeURIComponent(S.proj.path)));
      if (j.ok === false && !S.proj.rehearsal) alert(j.error);
    }
    if (j.kind === "make" && !j.running) {
      clearInterval(S.poll);
      if (j.ok) { S.proj = Object.assign(S.proj, await api("/api/project?path=" + encodeURIComponent(S.proj.path))); }
    }
    if ((S.cur === 0 && j.kind === "demo") || (S.cur === 1 && j.kind === "rehearse") || (S.cur === 3 && j.kind === "make")) {
      const focus = document.activeElement && document.activeElement.isContentEditable;
      if (!focus) render();
    }
  }, 1000);
}

// ── ⚙ 설정: 브랜드 · 규칙 ──
function lum(h) { const c = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255).map(x => x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; }
function contrast(a, b) { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); }
async function renderBrand(name) {
  name = name || S.brandSel || store.get("brand", "") || "taekwonworld";
  if (!S.st.brands.includes(name)) name = S.st.brands[0];
  S.brandSel = name;
  const b = await api("/api/brand?name=" + encodeURIComponent(name));
  const d = b.data || {};
  const bg = d["배경"] || ["#1B2559", "#405BEA"];
  const tones = ["차분", "친근", "전문"];
  const brandRadios = S.st.brands.map(n => `<label class="opt"><input type="radio" name="bl" value="${esc(n)}" ${n === name ? "checked" : ""}><span>${esc(n === "basic" ? "기본" : n === "taekwonworld" ? "태권월드" : n)}</span></label>`).join("")
    + `<label class="opt"><input type="radio" name="bl" value="__new"><span>＋ 새 브랜드</span></label>`;
  $("#tabBrand").innerHTML = `<div class="opts">${brandRadios}</div>
    <div class="inline"><label class="ghost" style="display:inline-flex;align-items:center;gap:6px">로고 올리기<input type="file" id="logoF" accept="image/png" hidden></label>
      ${b.logo ? `<img src="${fileUrl(b.logo)}" alt="로고" style="height:32px;background:#fff;border-radius:6px;padding:4px">` : '<span class="hint">로고 없음 · 이름 글자로 대신해요</span>'}</div>
    <div class="row"><label class="f" for="bn">표기 이름<input type="text" id="bn" value="${esc(d["이름"] || "")}" placeholder="예: 태권월드"></label>
      <label class="f" for="br">읽는 이름 (발음)<input type="text" id="br" value="${esc(d["읽는이름"] || "")}" placeholder="예: 태권 월드"></label></div>
    <div><div class="hint" style="margin-bottom:6px">색 (역할별로만 사용)</div><div class="swatches">
      <label class="sw"><input type="color" id="c1" value="${bg[0]}"><input type="color" id="c2" value="${bg[1]}">주 색 · 배경</label>
      <label class="sw"><input type="color" id="c3" value="${d["강조색"] || "#CC1424"}">강조 · 클릭 효과</label>
      <label class="sw"><input type="color" id="c4" value="${d["포인트색"] || "#54B4CC"}">포인트 · 단계 번호</label></div></div>
    <div class="row"><label class="f" for="bv">기본 목소리<select id="bv">${S.st.voices.map(v => `<option>${esc(v)}</option>`).join("")}</select></label>
      <label class="f" for="bt">말투<select id="bt">${tones.map(t => `<option ${t === (d["말투"] || "차분") ? "selected" : ""}>${t}</option>`).join("")}</select></label></div>
    <label class="f" for="bh">인사말<input type="text" id="bh" value="${esc(d["인사말"] || "")}" placeholder="비우면: 안녕하세요, (읽는 이름)입니다."></label>
    <label class="f" for="be">설명 끝 고정 문구<input type="text" id="be" value="${esc(d["고정문구"] || "")}" placeholder="예: 태권월드 · taekwonworld.net"></label>
    <details><summary>고급 설정<span>확대</span></summary><div class="checks" style="flex-direction:column;align-items:stretch">
      <label class="f" for="bz">확대 배율 (1.0~2.0)<input type="number" id="bz" min="1" max="2" step="0.1" value="${(d["규칙"] || {})["확대"] || 1.6}"></label></div></details>
    <div id="readable"></div>
    <div class="foot"><span class="hint">${b.builtin ? "기본 제공 브랜드를 고치면 이 PC에 사본으로 저장돼요." : ""}</span><button class="primary" type="button" id="saveBrand">저장</button></div>`;
  const voiceName = { "ko-KR-HyunsuMultilingualNeural": "현수 · 차분", "ko-KR-SunHiNeural": "선희 · 밝게", "ko-KR-InJoonNeural": "인준 · 또박또박" }[d["목소리"]];
  if (voiceName) $("#bv").value = voiceName;
  const check = () => {
    const c1 = $("#c1").value, c2 = $("#c2").value, p = $("#c4").value;
    const m = [];
    if (Math.min(contrast("#ffffff", c1), contrast("#ffffff", c2)) < 4.5) m.push("배경색이 밝아서 흰 제목이 잘 안 읽혀요. 배경을 조금 어둡게 해 주세요.");
    if (contrast("#ffffff", p) < 2.2) m.push("포인트색이 밝아서 단계 번호가 잘 안 보여요.");
    $("#readable").innerHTML = m.length ? m.map(x => `<div class="verdict has-warn">⚠ ${x}</div>`).join("") : '<div class="verdict">✓ 글자 읽힘 검사 통과</div>';
  };
  ["#c1", "#c2", "#c3", "#c4"].forEach(id => $(id).oninput = check); check();
  let logo = "";
  $("#logoF").onchange = e => { const f = e.target.files[0]; if (!f) return; const r = new FileReader(); r.onload = () => logo = r.result; r.readAsDataURL(f); };
  document.querySelectorAll("input[name=bl]").forEach(r => r.onchange = () => {
    if (r.value === "__new") { const n = prompt("새 브랜드 이름을 적어 주세요."); if (n) { S.st.brands.push(n); renderBrandBlank(n); } else renderBrand(name); }
    else renderBrand(r.value);
  });
  $("#saveBrand").onclick = async () => {
    const VO = { "현수 · 차분": ["ko-KR-HyunsuMultilingualNeural", -8], "선희 · 밝게": ["ko-KR-SunHiNeural", 0], "인준 · 또박또박": ["ko-KR-InJoonNeural", -4] }[$("#bv").value];
    const nd = Object.assign({}, d, { "이름": $("#bn").value, "읽는이름": $("#br").value || $("#bn").value, "배경": [$("#c1").value, $("#c2").value],
      "강조색": $("#c3").value, "포인트색": $("#c4").value, "목소리": VO[0], "목소리빠르기": VO[1], "말투": $("#bt").value,
      "인사말": $("#bh").value, "고정문구": $("#be").value, "규칙": Object.assign({}, d["규칙"] || {}, { "확대": Math.min(2, Math.max(1, +$("#bz").value || 1.6)) }) });
    if (!nd["글꼴"]) nd["글꼴"] = "Pretendard";
    const r = await api("/api/brand/save", { name, data: nd, logo });
    if (!r.ok) { alert(r.error); return; }
    store.set("brand", r.name); await loadState(); S.brandSel = r.name; renderBrand(r.name);
  };
}
function renderBrandBlank(n) { S.brandSel = n; api("/api/brand/save", { name: n, data: { "이름": n, "읽는이름": n, "글꼴": "Pretendard" } }).then(async r => { await loadState(); renderBrand(r.name); }); }
function renderRules() {
  const r = S.st.rules, D = S.st.default_rules;
  const reps = Object.entries(r["표현바꾸기"] || {});
  $("#tabRules").innerHTML = `
    <div class="row"><label class="f" for="rl1">목표 길이<select id="rl1">${[[60, "1분"], [90, "1분 30초 (추천)"], [120, "2분"]].map(([v, t]) => `<option value="${v}" ${v === r["목표길이"] ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      <label class="f" for="rl2">한 문장 최대 글자<input type="number" id="rl2" min="15" max="80" value="${r["문장최대글자"]}"></label></div>
    <div class="row"><label class="f" for="rl3">문장 사이 쉼 (초)<input type="number" id="rl3" min="0.2" max="2" step="0.05" value="${r["문장사이쉼"]}"></label>
      <label class="f" for="rl4">"눌러 주세요" 뒤 쉼 (초)<input type="number" id="rl4" min="0.2" max="3" step="0.05" value="${r["눌러주세요뒤쉼"]}"></label></div>
    <div><div class="hint" style="margin-bottom:6px">표현 바꾸기 (대본에서 저절로 바꿔요)</div><div class="reps" id="reps">
      ${reps.map(([a, b], i) => `<div><input type="text" value="${esc(a)}" data-ra="${i}"><span>→</span><input type="text" value="${esc(b)}" data-rb="${i}"><button class="x" type="button" data-rx="${i}">✕</button></div>`).join("")}
      </div><button class="ghost" type="button" id="repAdd" style="margin-top:6px">＋ 추가</button></div>
    <label class="f" for="rl5">확대 배율 (1.0~2.0)<input type="number" id="rl5" min="1" max="2" step="0.1" value="${r["확대"]}"></label>
    <div class="verdict">🔒 개인정보 흐림 · 저장·발송 차단은 항상 켜져 있어요</div>
    <div class="foot"><button class="ghost" type="button" id="resetRules">1편 기준으로 되돌리기</button><button class="primary" type="button" id="saveRules">저장</button></div>`;
  const collect = () => {
    const rp = {};
    document.querySelectorAll("[data-ra]").forEach(a => { const b = document.querySelector(`[data-rb="${a.dataset.ra}"]`); if (a.value.trim()) rp[a.value.trim()] = b.value.trim(); });
    return { "목표길이": +$("#rl1").value, "문장최대글자": +$("#rl2").value, "문장사이쉼": +$("#rl3").value, "눌러주세요뒤쉼": +$("#rl4").value, "확대": Math.min(2, Math.max(1, +$("#rl5").value || D["확대"])), "표현바꾸기": rp };
  };
  $("#repAdd").onclick = () => { S.st.rules = Object.assign(collect(), {}); S.st.rules["표현바꾸기"][""] = ""; renderRules(); };
  document.querySelectorAll("[data-rx]").forEach(x => x.onclick = () => { const c = collect(); delete c["표현바꾸기"][Object.keys(c["표현바꾸기"])[+x.dataset.rx]]; S.st.rules = c; renderRules(); });
  $("#saveRules").onclick = async () => { const res = await api("/api/rules/save", { rules: collect() }); S.st.rules = res.rules; $("#drawer").hidden = true; };
  $("#resetRules").onclick = async () => { const res = await api("/api/rules/reset", {}); S.st.rules = res.rules; renderRules(); };
}
$("#settingsBtn").onclick = () => { $("#drawer").hidden = false; renderBrand(); renderRules(); };
$("#closeDrawer").onclick = () => $("#drawer").hidden = true;
$("#drawer").onclick = e => { if (e.target.id === "drawer") $("#drawer").hidden = true; };
$("#tbB").onchange = () => { $("#tabBrand").hidden = false; $("#tabRules").hidden = true; };
$("#tbR").onchange = () => { $("#tabBrand").hidden = true; $("#tabRules").hidden = false; };
document.addEventListener("keydown", e => { if (e.key === "Escape") $("#drawer").hidden = true; });

(async () => {
  await loadState();
  if (S.job && S.job.running) {               // 화면을 새로 열어도 하던 작업을 이어서 보여 줌
    if (S.job.kind === "make" && S.job.path) await openProject(S.job.path, 3);
    startPoll();
  }
  nav(); render();
})();
