# GitHub Actions 에서 2편 나레이션(현수 목소리)을 만든다. 결과: tutorials/ep2_voice/<키>.mp3
import asyncio, json, sys
from pathlib import Path
import edge_tts
D = json.loads('{"voice": "ko-KR-HyunsuMultilingualNeural", "lines": [{"key": "I1", "text": "안녕하세요, 태권 월드입니다.", "rate": -6, "pitch": 3}, {"key": "I2", "text": "오늘은 로그인하고, 내 도장을 등록하는 방법을, 세 단계로 알려 드릴게요.", "rate": -8, "pitch": 1}, {"key": "L1", "text": "먼저, 첫 화면 오른쪽 위에 있는, 로그인 관장 버튼을 눌러 주세요.", "rate": -9, "pitch": 0}, {"key": "L2", "text": "가입할 때 만든 아이디와 비밀번호를 적고, 로그인 버튼을 눌러 주세요.", "rate": -8, "pitch": 0}, {"key": "L3", "text": "로그인하면 도장 목록이 나와요. 아래에 있는, 도장 추가를 눌러 주세요.", "rate": -8, "pitch": 1}, {"key": "R1", "text": "먼저, 파일 업로드를 눌러, 사업자 등록증을 올려 주세요.", "rate": -8, "pitch": 0}, {"key": "R2", "text": "사진 올리기를 눌러, 도장 로고도 올려 주세요.", "rate": -8, "pitch": 0}, {"key": "R3", "text": "도장 직인은, 사각이나 원형을 고르고, 들어갈 글자를 적으면 돼요.", "rate": -8, "pitch": 0}, {"key": "F1", "text": "이제, 도장 이름과 전화번호를 적어 주세요.", "rate": -8, "pitch": 0}, {"key": "F2", "text": "사업자 등록번호는, 빼기 표시 없이 숫자만 적어 주세요.", "rate": -8, "pitch": 0}, {"key": "A1", "text": "도장 주소 칸을 누르고, 주소를 검색해서 골라 주세요.", "rate": -8, "pitch": 0}, {"key": "D1", "text": "상세 주소도 적어 주세요.", "rate": -8, "pitch": 0}, {"key": "G1", "text": "다 적었으면, 오른쪽 위 등록 버튼을 눌러 주세요.", "rate": -8, "pitch": 0}, {"key": "H1", "text": "도장 목록에서, 관리하러 가기를 눌러 주세요.", "rate": -8, "pitch": 0}, {"key": "H2", "text": "처음 들어오면, 시작 순서를 알려 주는 안내 창이 떠요.", "rate": -8, "pitch": 0}, {"key": "H3", "text": "반 만들기부터 차량 등록까지, 이 순서대로 하시면 돼요.", "rate": -8, "pitch": 0}, {"key": "H4", "text": "창 닫기를 누르면, 첫 화면이 보여요.", "rate": -8, "pitch": 0}, {"key": "H5", "text": "왼쪽 메뉴에서, 수련생, 출결, 납부 같은 기능을 고를 수 있어요.", "rate": -8, "pitch": 0}, {"key": "O1", "text": "오늘 배운 세 단계, 기억하시죠?", "rate": -7, "pitch": 2}, {"key": "O2", "text": "다음 영상에서는, 반 만드는 방법을 알려 드릴게요. 태권 월드였습니다.", "rate": -8, "pitch": 1}]}')
import edge_tts.constants as C, edge_tts.drm as DRM, edge_tts.communicate as M
ORIG = C.CHROMIUM_FULL_VERSION
def set_ver(full):
    """edge-tts 가 보내는 브라우저 버전을 바꾼다(오래된 버전은 403으로 거절될 수 있음)."""
    major = full.split(".")[0]; om = ORIG.split(".")[0]
    fix = lambda v: v.replace(ORIG, full).replace(f"v=\"{om}\"", f"v=\"{major}\"").replace(f"/{om}.0.0.0", f"/{major}.0.0.0")
    for mod in (C, DRM, M):
        for k in dir(mod):
            v = getattr(mod, k)
            if isinstance(v, str) and k.isupper():
                setattr(mod, k, fix(v))
            elif isinstance(v, dict) and k.isupper():
                setattr(mod, k, {a: (fix(b) if isinstance(b, str) else b) for a, b in v.items()})
async def probe():
    for full in [ORIG, "155.0.4283.45", "156.0.4314.15", "154.0.4252.82"]:
        set_ver(full)
        try:
            await edge_tts.Communicate("안녕하세요.", D["voice"]).save("/tmp/probe.mp3")
            print("열림:", full); return True
        except Exception as e:
            print("막힘:", full, str(e)[:60])
    return False
if not asyncio.run(probe()):
    sys.exit("모든 버전이 막힘")
out = Path("tutorials/ep2_voice"); out.mkdir(parents=True, exist_ok=True)
async def run():
    for ln in D["lines"]:
        for t in range(4):
            try:
                await edge_tts.Communicate(ln["text"], D["voice"], rate=f"{ln['rate']:+d}%", pitch=f"{ln['pitch']:+d}Hz").save(str(out / f"{ln['key']}.mp3"))
                print("ok", ln["key"]); break
            except Exception as e:
                print("retry", ln["key"], e); await asyncio.sleep(3)
        else:
            sys.exit(f"fail {ln['key']}")
asyncio.run(run())
