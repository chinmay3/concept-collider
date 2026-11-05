# Concept Collider

**See your ad set the way Meta's Andromeda sees it, then let an agent fill the gaps.**

Meta's ad retrieval system (Andromeda) groups look-alike ads into one creative concept. Ads with the
same visual setup and a different headline count as one ad. Advertisers think they are testing 9 ads
when Meta sees 3, and their reach is throttled.

Concept Collider is an agent that:

1. **Reads** every ad with **Muse Spark 1.3** (vision, JSON mode) and tags its angle, format and visual signature.
2. **Groups** the ads into the concepts Andromeda would see, gives a diversity score and maps angle × format coverage.
3. **Finds gaps**: picks 4 angle × format combinations nobody has tried that are most likely to reach new audiences.
4. **Segments** the product out of the hero ad with **SAM 3.1** (Responses API, text prompt → box).
5. **Evolves** 3 candidate ads per gap with **Muse Image** (`/images/edits`, segmented product as reference): 12 images in parallel. Muse Spark then runs a tournament, scoring every candidate on novelty vs. the existing set and brand fit, and keeps one winner per gap.
6. **Checks its own work**: re-scores the full set with Muse Spark to confirm the new ads really are new concepts (e.g. 3 → 8).

Demo result on the fictional brand NORTHBREW: **9 ads → 3 concepts, diversity 18/100**, then 4 generated gap concepts take it to **8 concepts, diversity 28/100**.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
echo "MODEL_API_KEY=<your Meta Model API key>" > .env
.venv/bin/uvicorn app:app --port 8777
```

Open http://localhost:8777 → **Load demo brand** → **Collide** → **Fill the gaps**. Or upload your own ad images.

`seed.py` regenerates the demo ad set with Muse Image.

## Next: Creator Match

> Concept Collider tells you which concepts you're missing. Creator Match finds the creators already making them.

A brand gives its profile (site, product photos, existing ads, audience). The agent then finds creators who
**already make that kind of content**, matching on what is actually in their reels rather than follower count
or self-chosen categories:

1. **Brand fingerprint:** Muse Spark turns the brand profile into category, aesthetic, audience, tone and things the brand won't do.
2. **Creator fingerprint:** for each candidate creator's recent public reels, SAM 3.1 finds products on screen and Muse Spark tags setting, format (tutorial, unboxing, day-in-the-life), aesthetic and competitor products they already feature.
3. **Match with evidence:** a fit score plus the reels that prove it, e.g. *"6 of their last 20 reels are morning-routine coffee content, they already feature 2 competitor brands. See reels #3, #8, #14."*
4. **Outreach + ad idea:** a drafted outreach note and a Partnership Ad concept. Concept Collider checks it adds a genuinely new concept to the brand's set.

Data comes only through official channels: Instagram API Business Discovery for public business/creator accounts,
creators who tag or mention the brand, or creators who opt in. No scraping, no private watch history.

The loop: **find the gap → find the creator → run it as a Partnership Ad.**

## Stack
FastAPI + one HTML page. Meta Model API only: `muse-spark-1.3`, `sam-3.1`, `muse-image-1.0`.

Track: Indie · Theme: Build for Your World (performance marketing).
