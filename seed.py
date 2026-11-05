import os,requests,base64,io,json
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv; load_dotenv(".env")
from PIL import Image
H={"Authorization":f"Bearer {os.environ['MODEL_API_KEY']}","Content-Type":"application/json"}
CAN="a matte black cold brew coffee can with a bold white 'NORTHBREW' wordmark"
P=[f"Square social ad. Studio product shot of {CAN} on a white marble counter, soft daylight, ice cubes. Big headline text: '{h}'" for h in
   ["SMOOTH. BOLD. COLD.","20% OFF YOUR FIRST CASE","ZERO SUGAR. ALL KICK.","YOUR NEW MORNING RITUAL","BREWED 18 HOURS"]]+[
   f"Square social ad. Product shot of {CAN} on a light wooden table next to coffee beans, warm morning light. Headline text: 'FRESH FROM THE ROASTER'",
   f"Square social ad. Product shot of {CAN} on a white counter with a glass of iced coffee, minimal. Headline text: 'NOW IN 12-PACKS'",
   f"Square social ad. Two {CAN}s side by side on marble with ice, clean studio. Headline text: 'STOCK UP & SAVE'",
   f"Square social ad. Close-up of {CAN} with condensation droplets on dark slate, dramatic lighting. Headline text: 'COLD BREW, PERFECTED'"]
def gen(i):
    r=requests.post("https://api.meta.ai/v1/images/generations",headers=H,json={"model":"muse-image-1.0","prompt":P[i],"n":1},timeout=240)
    r.raise_for_status()
    im=Image.open(io.BytesIO(base64.b64decode(r.json()["data"][0]["b64_json"]))).convert("RGB")
    im.thumbnail((768,768)); im.save(f"static/seed/ad{i+1:02d}.jpg",quality=88); return i
with ThreadPoolExecutor(9) as ex:
    for f in [ex.submit(gen,i) for i in range(len(P))]:
        try: print("ok",f.result())
        except Exception as e: print("ERR",e)
