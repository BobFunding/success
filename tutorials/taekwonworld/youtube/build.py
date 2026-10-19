import json, sys
sys.path.insert(0, sys.argv[1])
from content import EP, PARTS, PART_DESC
eps = {e["n"]: e for e in json.load(open(sys.argv[1] + "/eps.json"))}
SITE = "https://taekwonworld.net"
LINKS = [("태권월드 홈페이지", SITE), ("사용자 가이드", SITE + "/guide"),
         ("앱스토어", "https://apps.apple.com/kr/app/id6450205241"),
         ("구글플레이", "https://play.google.com/store/apps/details?id=com.aivill.taekwonworld"),
         ("네이버 블로그", "https://blog.naver.com/taekwon_world"),
         ("인스타그램", "https://instagram.com/taekwonworld"), ("X", "https://x.com/taekwon_world")]
ABOUT = ("태권월드(Taekwon World)는 태권도장 통합관리 플랫폼입니다. 출결(QR 출석), 수련비 청구서와 자동결제, "
         "디지털 승급증, 체력평가·헬스케어, 공지·알림장·일정 학부모 앱, 도장 홈페이지까지 한곳에서 관리합니다.")
BASE_TAGS = ["태권월드", "Taekwon World", "태권도장 관리 프로그램", "태권도장 관리 앱", "태권도장 운영", "도장 관리"]
def mmss(t): return f"{int(t//60)}:{int(t%60):02d}"
def short(n): return EP[n][1].split(" | ")[0]
out = []
for n in range(1, 29):
    part, title, summ, guide, tags, hashtag, q, a = EP[n]
    e = eps[n]
    steps = "\n".join(f"{i}단계 {s}" for i, s in enumerate(e["steps"], 1))
    ch = []                                         # 유튜브 규칙: 챕터마다 10초 이상 → 짧은 단계는 앞 단계와 합침
    for i, (nm, t) in enumerate(e["chapters"]):
        nxt = e["chapters"][i + 1][1] if i + 1 < len(e["chapters"]) else None
        if nxt is not None and int(nxt) - int(t) < 11 and len(ch) > 1:
            pn, pt = ch[-1]
            ch[-1] = (pn.replace("단계 ", "~" + nm.split("단계")[0] + "단계 ", 1) + " · " + nm.split(" ", 1)[1], pt)
            continue
        ch.append((nm, t))
    chap = "\n".join(f"{mmss(t)} {nm}" for nm, t in ch)
    rel = []
    if n > 1: rel.append(f"이전 편: {n-1}편 {short(n-1)}")
    if n < 28: rel.append(f"다음 편: {n+1}편 {short(n+1)}")
    desc = "\n".join([
        summ, "",
        f"▶ 글로 보는 단계별 안내: {guide}",
        f"▶ 태권월드 홈페이지: {SITE}", "",
        "[이 영상의 순서]", steps, "",
        "[챕터]", chap, "",
        f"[태권월드 사용법 시리즈 · {PARTS[part]}]", *rel, "",
        "[태권월드]", ABOUT,
        "· 앱스토어: https://apps.apple.com/kr/app/id6450205241",
        "· 구글플레이: https://play.google.com/store/apps/details?id=com.aivill.taekwonworld",
        "· 네이버 블로그: https://blog.naver.com/taekwon_world",
        "· 문의: 070-7777-5774 · tkw@aivill.co.kr",
        "· 운영: 에이아이빌(AIVILL)", "",
        f"#태권월드 #태권도장관리 #{hashtag}"])
    tagstr = ", ".join(dict.fromkeys(BASE_TAGS + tags + [f"태권월드 {n}편"]))
    pin = f"Q. {q}\nA. {a}\n\n더 자세한 단계별 안내는 여기서 볼 수 있어요: {guide}"
    out.append({"n": n, "part": part, "partName": PARTS[part], "title": title, "desc": desc, "tags": tagstr,
                "pin": pin, "guide": guide, "len": mmss(e["end"]), "steps": e["steps"],
                "check": {"title": len(title), "desc": len(desc), "tags": len(tagstr)}})
playlists = [{"name": f"태권월드 사용법 {PARTS[p]}",
              "desc": f"{PART_DESC[p]} 태권월드(Taekwon World) 태권도장 통합관리 플랫폼 사용법 영상입니다. 단계별 글 안내: {SITE}/guide",
              "eps": [n for n in range(1, 29) if EP[n][0] == p]} for p in range(1, 10)]
playlists.insert(0, {"name": "태권월드 사용법 전체 (1~28편)",
                     "desc": f"태권도장 통합관리 플랫폼 태권월드(Taekwon World)를 처음 가입부터 운영·관리까지 28편, 편마다 3단계로 알려 드려요. 단계별 글 안내: {SITE}/guide",
                     "eps": list(range(1, 29))})
channel = {
  "name": "태권월드 Taekwon World",
  "handle": "@taekwonworld",
  "about": ABOUT + "\n\n이 채널에서는 관장님이 태권월드를 처음 가입하는 날부터 출결, 수련비, 승급, 학부모 소통, 도장 관리까지 따라 할 수 있는 사용법 영상(28편)을 올립니다.\n\n문의: 070-7777-5774 · tkw@aivill.co.kr\n운영: 에이아이빌(AIVILL)",
  "keywords": "태권월드, Taekwon World, 태권도장 관리 프로그램, 태권도장 관리 앱, 태권도 출석 체크, 수련비 자동결제, 디지털 승급증, 학부모 앱",
  "links": LINKS,
}
over = [o for o in out if o["check"]["title"] > 100 or o["check"]["desc"] > 5000 or o["check"]["tags"] > 500]
print("길이 초과:", [(o["n"], o["check"]) for o in over])
json.dump({"eps": out, "playlists": playlists, "channel": channel}, open(sys.argv[1] + "/data.json", "w"), ensure_ascii=False)
print(out[8]["title"]); print(out[8]["desc"]); print(out[8]["tags"]); print(out[8]["pin"])
