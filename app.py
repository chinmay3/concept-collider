"""Concept Collider: see your ad set the way Meta's Andromeda sees it, then fill the gaps.

Muse Spark (vision) tags + clusters ads into concepts, SAM 3.1 cuts out the product,
Muse Image generates new concepts for the empty cells, Muse Spark re-scores to verify.
"""
import base64, io, json, os, re, glob
from concurrent.futures import ThreadPoolExecutor

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
API = "https://api.meta.ai/v1"
H = {"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}", "Content-Type": "application/json"}

ANGLES = ["Product hero", "Offer / discount", "Problem → solution", "Social proof / UGC",
          "Lifestyle moment", "Comparison / vs", "Ingredient / process", "Founder / story"]
FORMATS = ["Studio product shot", "In-context lifestyle photo", "Person holding product",
           "Text-led graphic", "Split / before-after", "Flat lay"]

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


def chat_json(content, effort="low"):
    r = requests.post(f"{API}/chat/completions", headers=H, timeout=180, json={
        "model": "muse-spark-1.3", "reasoning_effort": effort,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": content}]})
    if r.status_code != 200:
        raise HTTPException(502, f"Muse Spark: {r.text[:300]}")
    txt = r.json()["choices"][0]["message"]["content"]
    return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])


def to_jpeg_dataurl(img: Image.Image, size=768):
    img = img.convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def from_dataurl(u):
    return Image.open(io.BytesIO(base64.b64decode(u.split(",", 1)[1])))


ANALYZE_PROMPT = """You are a senior Meta ads creative strategist.
Meta's Andromeda retrieval system groups ads that look or feel alike into ONE creative concept.
Ads with the same visual setup but a different headline count as the SAME concept. Only a genuinely
different angle + visual format counts as a new concept. Be strict, like Andromeda.

You get {n} ads, indexed 0..{last} in the order given.
Allowed angles: {angles}
Allowed formats: {formats}

Return ONLY JSON:
{{
 "brand": "brand name you see (or best guess)",
 "product": "2-4 word noun phrase for the physical product, e.g. 'black coffee can'",
 "ads": [{{"i": 0, "headline": "...", "angle": "<allowed angle>", "format": "<allowed format>", "visual_signature": "<6-10 words: setting, props, lighting, composition>"}}],
 "concepts": [{{"name": "<short concept name>", "ad_indices": [0,1], "why_same": "<one short sentence>"}}],
 "diversity_score": <0-100, how much of the angle x format space this set covers, strict>,
 "verdict": "<one punchy sentence on what Andromeda will do with this set>",
 "gaps": [{{"angle": "<allowed angle>", "format": "<allowed format>", "name": "<concept name>", "scene": "<one vivid sentence describing the new ad's visual scene and headline>", "why": "<why it should win>"}}]
}}
Every ad index must appear in exactly one concept. Give exactly {k} gaps, each an angle x format combo NOT used by any existing ad, chosen to maximise new-audience reach."""


class AnalyzeReq(BaseModel):
    images: list[str]
    gaps: int = 4


@app.post("/api/analyze")
def analyze(req: AnalyzeReq):
    n = len(req.images)
    content = [{"type": "text", "text": ANALYZE_PROMPT.format(
        n=n, last=n - 1, angles=json.dumps(ANGLES), formats=json.dumps(FORMATS), k=req.gaps)}]
    for i, u in enumerate(req.images):
        content += [{"type": "text", "text": f"Ad {i}:"},
                    {"type": "image_url", "image_url": {"url": to_jpeg_dataurl(from_dataurl(u), 512)}}]
    out = chat_json(content)
    out["angles"], out["formats"] = ANGLES, FORMATS
    return out


def sam_box(dataurl, phrase):
    """Ask SAM 3.1 for the phrase; return the highest-ranked (x1,y1,x2,y2,w,h) box or None."""
    r = requests.post(f"{API}/responses", headers=H, stream=True, timeout=120, json={
        "model": "sam-3.1", "stream": True,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": phrase},
            {"type": "input_image", "image_url": dataurl}]}]})
    if r.status_code != 200:
        raise HTTPException(502, f"SAM: {r.text[:300]}")
    text = ""
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            try:
                ev = json.loads(line[5:])
            except ValueError:
                continue
            if ev.get("type") == "response.output_text.delta":
                text += ev.get("delta", "")
    boxes = re.findall(r"box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)", text)
    if not boxes:
        return None
    return max((tuple(map(int, b)) for b in boxes), key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))


class FillReq(BaseModel):
    hero: str
    product: str
    brand: str
    gaps: list[dict]
    existing: list[str] = []
    variants: int = 3


TWISTS = ["", " Push it further: a bolder, more unexpected composition.",
          " Use a different camera angle and a contrasting color palette."]

JUDGE_PROMPT = """You are Meta's Andromeda retrieval system plus a strict brand creative director.
The first {n} images are the brand's EXISTING ads. After them come CANDIDATE new ads, each labelled with an id like g0v1
(gap 0, variant 1). Score every candidate:
- novelty 0-100: how different a creative concept it is from ALL existing ads (near-duplicates of existing ads score low)
- brand_fit 0-100: product matches the brand's real product, headline legible, looks like a professional ad
Then pick exactly ONE winner per gap (g0, g1, ...), maximising novelty + brand_fit.
Return ONLY JSON: {{"candidates": [{{"id": "g0v0", "novelty": 0, "brand_fit": 0, "note": "<max 10 words>"}}], "winners": {{"g0": "g0v1"}}}}"""


def judge(existing, cands):
    content = [{"type": "text", "text": JUDGE_PROMPT.format(n=len(existing))}]
    for i, u in enumerate(existing):
        content += [{"type": "text", "text": f"Existing ad {i}:"},
                    {"type": "image_url", "image_url": {"url": to_jpeg_dataurl(from_dataurl(u), 384)}}]
    for c in cands:
        content += [{"type": "text", "text": f"Candidate {c['id']}:"},
                    {"type": "image_url", "image_url": {"url": to_jpeg_dataurl(from_dataurl(c['image']), 512)}}]
    return chat_json(content)


def gen_gap(product_url, brand, product, g, twist=""):
    prompt = (f"Square 1:1 social media ad for the brand {brand}. Use the EXACT {product} from the reference image "
              f"(same shape, colors, logo). Creative angle: {g['angle']}. Visual format: {g['format']}. "
              f"Scene: {g['scene']} Clean, scroll-stopping, professional ad photography, one short legible headline.{twist}")
    r = requests.post(f"{API}/images/edits", headers=H, timeout=240, json={
        "model": "muse-image-1.0", "prompt": prompt, "n": 1, "images": [{"image_url": product_url}]})
    if r.status_code != 200:
        return {"error": r.text[:200], **g}
    img = Image.open(io.BytesIO(base64.b64decode(r.json()["data"][0]["b64_json"])))
    return {"image": to_jpeg_dataurl(img), **g}


@app.post("/api/fill")
def fill(req: FillReq):
    hero = from_dataurl(req.hero).convert("RGB")
    hero_url = to_jpeg_dataurl(hero, 1024)
    hero = from_dataurl(hero_url)
    box = sam_box(hero_url, req.product) or sam_box(hero_url, "can")
    if box:
        x1, y1, x2, y2, w, h = box
        sx, sy = hero.width / w, hero.height / h
        pad = 12
        crop = hero.crop((max(0, x1 * sx - pad), max(0, y1 * sy - pad),
                          min(hero.width, x2 * sx + pad), min(hero.height, y2 * sy + pad)))
    else:
        crop = hero
    product_url = to_jpeg_dataurl(crop, 768)
    jobs = [(gi, vi) for gi in range(len(req.gaps)) for vi in range(req.variants)]
    with ThreadPoolExecutor(len(jobs)) as ex:
        out = list(ex.map(lambda j: gen_gap(product_url, req.brand, req.product, req.gaps[j[0]],
                                            TWISTS[j[1] % len(TWISTS)]), jobs))
    cands = [{"id": f"g{gi}v{vi}", "gap": gi, **o} for (gi, vi), o in zip(jobs, out) if o.get("image")]
    if not cands:
        raise HTTPException(502, "Muse Image returned no candidates")
    try:
        verdict = judge(req.existing, cands)
    except Exception:
        verdict = {"candidates": [], "winners": {}}
    scores = {c["id"]: c for c in verdict.get("candidates", [])}
    for c in cands:
        s = scores.get(c["id"], {})
        c.update(novelty=s.get("novelty", 0), brand_fit=s.get("brand_fit", 0), note=s.get("note", ""))
    winners = []
    for gi in range(len(req.gaps)):
        pool = [c for c in cands if c["gap"] == gi]
        if not pool:
            continue
        wid = verdict.get("winners", {}).get(f"g{gi}")
        w = next((c for c in pool if c["id"] == wid), max(pool, key=lambda c: c["novelty"] + c["brand_fit"]))
        w["winner"] = True
        winners.append(w)
    return {"product": product_url, "box": box, "ads": winners, "candidates": cands}


@app.get("/api/seed")
def seed():
    return sorted("/" + p for p in glob.glob("static/seed/*.jpg"))


@app.get("/")
def index():
    return FileResponse("static/index.html")
