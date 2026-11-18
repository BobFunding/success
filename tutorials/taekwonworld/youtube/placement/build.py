import json, base64, io
from PIL import Image
B = json.load(open("boxes.json"))
def crop(name, box, width=1100):
    im = Image.open(name + ".png").convert("RGB")
    x, y, w, h = box
    c = im.crop((x, y, x + w, y + h))
    if c.width > width: c = c.resize((width, round(c.height * width / c.width)), Image.LANCZOS)
    buf = io.BytesIO(); c.save(buf, "JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), (x, y, w, h)
def pct(cr, x, y, w=0, h=0):
    cx, cy, cw, ch = cr
    return f"left:{(x-cx)/cw*100:.2f}%;top:{(y-cy)/ch*100:.2f}%;" + (f"width:{w/cw*100:.2f}%;height:{h/ch*100:.2f}%;" if w else "")
figs = {}
# 1 기능 화면 제목 옆 (반 관리)
img, cr = crop("class", (240, 0, 1000, 160))
l = B["class"]["link"]
figs["class"] = (img, [("btn", pct(cr, l[0] + l[2] + 18, l[1] - 4), "▶ 영상으로 보기 · 3편")])
# 2 부분부터 (수련생 조회)
img2, cr2 = crop("rest", (240, 0, 1000, 160))
l = B["rest"]["link"]
figs["rest"] = (img2, [("btn", pct(cr2, l[0] + l[2] + 18, l[1] - 4), "▶ 영상으로 보기 · 20편 0:12부터")])
# 3 첫 화면 안내 창
m = B["home"]["modal"]
img3, cr3 = crop("home", (m[0] - 260, m[1] - 20, m[2] + 520, m[3] + 40), 900)
figs["home"] = (img3, [("bracket", pct(cr3, 812, 318, 300, 404), ""), ("tag", pct(cr3, 1122, 500), "순서마다 ▶ 영상 3~8편")])
# 4 사용 가이드 창
t = B["classguide"]["title"]
img4, cr4 = crop("classguide", (430, 150, 1060, 420), 1000)
figs["classguide"] = (img4, [("btn", pct(cr4, t[0] + t[2] + 24, t[1] - 2), "▶ 영상으로 보기 · 3편")])
# 5 로그인
j, f = B["login"]["join"], B["login"]["find"]
img5, cr5 = crop("login", (1080, 300, 840, 520), 900)
figs["login"] = (img5, [("btn", pct(cr5, j[0], j[1] + j[2] * 0 + j[3] + 14), "▶ 회원가입 영상 · 1편"),
                       ("tag", pct(cr5, f[0] + f[2] + 12, f[1] - 3), "▶ 26편")])
# 6 공개 가이드 페이지
h = B["guide"]["h"]
img6, cr6 = crop("guide", (300, 90, 1320, 700), 1000)
figs["guide"] = (img6, [("video", pct(cr6, h[0] + 120, h[1] + 50, 760, 300), "3편 영상 (반 만들기)<br><small>바로 아래에 단계 글 · 대본 · 자주 묻는 질문</small>")])
# 7 메인
img7, cr7 = crop("main", (0, 0, 1920, 1080), 1000)
figs["main"] = (img7, [])
json.dump(figs, open("figs.json", "w"))
print({k: len(v[0]) // 1024 for k, v in figs.items()})
