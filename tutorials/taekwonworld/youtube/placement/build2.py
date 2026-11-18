import json, base64, io
from PIL import Image
def crop(name, box, width=1000):
    im = Image.open(name + ".png").convert("RGB"); x, y, w, h = box
    c = im.crop((x, y, x + w, y + h))
    if c.width > width: c = c.resize((width, round(c.height * width / c.width)), Image.LANCZOS)
    buf = io.BytesIO(); c.save(buf, "JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), box
def pct(cr, x, y, w=0, h=0):
    cx, cy, cw, ch = cr
    return f"left:{(x-cx)/cw*100:.2f}%;top:{(y-cy)/ch*100:.2f}%;" + (f"width:{w/cw*100:.2f}%;height:{h/ch*100:.2f}%;" if w else "")
F = {}
img, cr = crop("p_sched_guide", (300, 110, 1320, 820))
F["r1"] = (img, [("bracket", pct(cr, 438, 174, 1044, 678), ""), ("btn", pct(cr, 660, 196), "▶ 영상으로 보기 · 14편 1:57")])
img, cr = crop("p_sched", (900, 120, 1020, 760))
F["r2a"] = (img, [("btn", pct(cr, 1330, 600), "처음이세요? ▶ 영상으로 따라 하기")])
img, cr = crop("p_bill", (240, 0, 1680, 600))
F["r2b"] = (img, [("btn", pct(cr, 1262, 220), "▶ 결제서비스 가입부터 보내기까지 · 10편")])
img, cr = crop("p_menu", (0, 0, 820, 320), 820)
F["r3a"] = (img, [("bracket", pct(cr, 16, 46, 240, 182), ""), ("tag", pct(cr, 270, 170), "▶ 내 정보 25편 · 로그아웃 28편")])
img, cr = crop("p_dots", (0, 0, 820, 320), 820)
F["r3b"] = (img, [("tag", pct(cr, 330, 88), "▶ 도장 바꾸기·삭제 24편")])
json.dump(F, open("figs2.json", "w")); print("ok")
