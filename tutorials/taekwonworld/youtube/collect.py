import json, re, sys, glob, os
from pathlib import Path
sys.path.insert(0, "/home/user/success")
import yaml
S = Path(sys.argv[1]); R = Path("/home/user/success/tutorials")
def srt(p):
    out=[]
    for b in re.split(r"\n\s*\n", Path(p).read_text(encoding="utf-8").strip()):
        L=b.strip().splitlines()
        if len(L)<3: continue
        m=re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", L[1]); t=int(m[1])*3600+int(m[2])*60+int(m[3])+int(m[4])/1000
        out.append((t," ".join(L[2:])))
    return out
def norm(s): return re.sub(r"[^가-힣A-Za-z0-9]","",s)
eps=[]
for n in range(1,29):
    sc = R/("ep1/scenario.yaml" if n==1 else f"taekwonworld/ep{n}/scenario.yaml")
    d = yaml.safe_load(sc.read_text(encoding="utf-8"))
    cands = sorted(glob.glob(str(S/f"태권월드_{n}편_*.srt"))+glob.glob(str(S/f"ep{n}/*.srt"))+glob.glob(str(S/f"ep{n}/out/*.srt"))+glob.glob(str(S/f"ep{n}/*/태권월드_*.srt")), key=os.path.getmtime, reverse=True)
    cues = srt(cands[0])
    steps = d.get("단계이름") or []
    scenes = d.get("장면") or []
    def find(text):
        k = norm(text)[:10]
        for t,c in cues:
            if norm(c).startswith(k[:8]) or k[:8] in norm(c): return t
        return None
    ch=[("인트로",0.0)]
    for i,name in enumerate(steps, start=1):
        first = next((s for s in scenes if s.get("단계")==i), None)
        t = find(first.get("말","")) if first else None
        ch.append((f"{i}단계 {name}", t))
    o = (d.get("아웃트로") or [{}])[0].get("말","")
    ch.append(("마무리", find(o)))
    eps.append({"n":n,"title":re.sub(r"[\[\]]","",d.get("제목","")),"steps":steps,"srt":cands[0],"chapters":ch,
                "intro":[x.get("말") for x in d.get("인트로",[])],
                "scenes":[(s.get("단계"),s.get("말")) for s in scenes],"end":cues[-1][0]})
json.dump(eps, open(S/"yt/eps.json","w"), ensure_ascii=False, indent=1)
for e in eps:
    bad=[c for c in e["chapters"] if c[1] is None]
    print(e["n"], e["title"], "|", " / ".join(f"{int(t//60)}:{int(t%60):02d} {nm}" if t is not None else f"?? {nm}" for nm,t in e["chapters"]))
