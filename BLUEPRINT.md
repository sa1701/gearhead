# 🚗 GEARHEAD — Project Blueprint

> A local-first AI tool that diagnoses car problems and gives the exact fix,
> grounded in real workshop manuals (with diagrams). GCC-focused.
> Built by Seif Ali — car guy, CS student.

**Status:** ⏸️ PARKED 2026-06-11 — Steps 1–5 done and working; API credit ran out, Seif chose to pause rather than top up or switch to Ollama.

**To resume:** (1) add Anthropic credit OR build the free `OllamaProvider` (Phase 2, designed-for swap); (2) `python run_app.py` → http://127.0.0.1:8000; (3) finish the Fix Database: `python build_fixdb.py` (~$0.40 on Haiku, checkpoints every batch, resumes automatically). Next-level order locked by Seif: Fix DB → diagram cropping → hybrid routing → garage log → voice mode.
**Hero car:** Nissan Patrol (most common GCC vehicle; global model = clean English manuals available)

---

## The Idea (one line)
Tell it what's wrong (plain words *or* an OBD fault code), it interviews you like a
real mechanic, then gives the exact fix — with the real diagram and the manual page
it came from.

---

## Locked-In Decisions

| Decision | Choice |
|---|---|
| How you start a diagnosis | **Guided wizard** — symptom OR fault code → decision-tree interview → fix |
| Where answers come from | **Grounded in real manuals** — every fix cites the page + shows the diagram |
| Getting manuals in | **Hybrid** — hand-curate the hero car's top failures + auto-search (RAG) the rest |
| Who supplies PDFs | **Seif** drops PDFs into `/manuals` (e.g. from lemon-manuals.la). Tool ingests whatever's there. |
| Scope | **1 car first (Nissan Patrol)**, architected so "add a car = drop a PDF" |
| The brain | **Claude API (`claude-opus-4-8`)** — multimodal, reads diagrams |
| Brain swappability | Behind an **`AIProvider` interface**; **Ollama** = future free/offline text-only mode |
| Platform | **Local-first** app, runs on Seif's C:\ drive |
| UI | **Car-dashboard themed** web app |
| Risk to manage | Manual sourcing = the **moat AND legal risk** → personal/educational use, manuals stay local, safety disclaimer |

---

## The Big Picture

```
        YOU (in the browser)
              │  ▼
   ┌─────────────────────────┐
   │   THE FRONT DESK (UI)    │  ← car-themed screen
   └───────────┬─────────────┘
               ▼
   ┌─────────────────────────┐
   │   THE BRAIN (backend)    │  ← runs the interview, calls Claude
   └─────┬──────────────┬─────┘
         ▼              ▼
 ┌──────────────┐  ┌──────────────────┐
 │  THE LIBRARY │  │   CLAUDE (API)   │
 │  manuals +   │  │  reads + reasons │
 │  search DB   │  └──────────────────┘
 └──────────────┘
         ▲
   📂 /manuals  ← PDFs you drop in
```

---

## The Tools

| Job | Tool |
|---|---|
| App body | Python + FastAPI (local web server) |
| Brain | Claude API — `anthropic` library, model `claude-opus-4-8` |
| Search box | Chroma (local vector DB) |
| Reading PDFs | PyMuPDF (text + image extraction) |
| Screen | HTML + CSS + light JS (car-dashboard look) |

Everything in one C:\ project folder; only Claude is over the internet.

---

## Build Order (each step must WORK before the next)

- [x] **Step 1 — Get one manual in.** ✅ DONE 2026-06-11. Ingested 22 Patrol PDFs → 2,450 chunks in Chroma. Search verified: 5/5 test queries hit the correct section + page (brakes→Brakes p.30, no-start→Engine Control p.149, headlight wiring→Electrical p.71, ATF→Auto Trans p.123, airbag→Restraint p.12). Code: src/library/ingest.py + search.py, runners ingest_manuals.py + test_search.py.
- [x] **Step 2 — Make the brain answer (no UI).** ✅ DONE 2026-06-11. `src/brain/diagnose.py` (+ runner `diagnose.py`). Searches Library → feeds pages to Claude → grounded, cited fix. Safety guardrail verified (refuses to guess when manual lacks the info). Added a **query-expansion step** (Claude rewrites messy symptoms into focused manual search phrases) after the first test pulled wrong sections — now retrieval is reliable. Brake-shudder test produced a correct warped-rotor diagnosis with real specs cited to exact pages. ~2 Claude calls/query, a few cents.
- [x] **Step 3 — Add the interview loop.** ✅ DONE 2026-06-11. `src/brain/interview.py` (+ scripted test `test_interview.py`). QUESTION/DIAGNOSIS protocol: brain asks one clarifying question at a time, stops when confident. Brake-shudder run asked 2 good questions then gave a correct warped-rotor diagnosis citing the NVH chart [Brakes p.4] + specs. **Prompt caching ON** (system+20-chunk context = 7006 tokens cached): turn 1 wrote cache, turns 2-3 each read 7006 from cache (~90% saving on repeated context). Provider gained `cache=True` + `last_usage`.
- [x] **Step 4 — Add the diagrams.** ✅ DONE 2026-06-11. `src/library/images.py` (`render_page` via PyMuPDF → PNG in page_images/; `illustrate()` sends rendered pages to Claude vision for captions). Test rendered FRONT DISC BRAKE page BR-21 (real diagram: caliper, pad-retainer arrow, 12.0/2.0mm specs); Claude read it accurately and correctly distinguished front vs rear caliper pages. Confirmed image is a genuine labeled diagram.
- [x] **Step 5 — Add the car-themed screen.** ✅ DONE 2026-06-11. FastAPI app `src/web/server.py` + `run_app.py` (launch → http://127.0.0.1:8000). UI in src/web/static/ (index.html, styles.css, app.js): night-cockpit aesthetic, SVG tachometer confidence gauge, 3 screens (ignition input → mechanic chat interview → fix screen with cited steps + rendered manual diagram + sources). Endpoints: /api/start, /api/answer, /api/illustrate, /api/cars. `DiagnosisSession` (step-based) added to interview.py. Verified end-to-end via TestClient (test_web.py): full flow + diagram serving works.
- [ ] **Step 6 — Polish + add a 2nd car.** Prove "add a car = drop a PDF."

**Golden rule:** nothing is "done" until tested with a real check.

---

## The Brain — Interview Engine (the secret sauce)

1. User gives a symptom or fault code.
2. Backend pulls matching manual pages from the Library.
3. Asks Claude: "what's the smartest next question to narrow this?"
4. Shows the user that one question → user answers → loop.
5. When confident enough → output the **fix**: steps + real diagram + source page.

**Honesty rules baked in:**
- Always shows its **source page** (can't make stuff up).
- **Admits when unsure** instead of guessing (wrong fix = danger).
- Every answer carries **"⚠️ Always verify with a professional."**

---

## Cost Reality
- Claude API is **pay-as-you-go**, separate from any Claude subscription.
- ~**$0.05–0.15 per full diagnosis** (with prompt caching).
- ~**$2.50–7.50/month** for normal personal use. Prepay ~$5 + set a hard spend cap.
- Phase 2 (Ollama) drives simple text-only diagnoses to **$0**.

---

## To Start Step 1, Seif needs:
1. ✅ Hero car chosen: **Nissan Patrol**
2. ✅ **Manual in** — Patrol Y61 (GU) factory service manual, 22 clean PDFs, virus-scanned, at `manuals\nissan-patrol-y61\` (split by section: em, ec, at, mt, tf, br, st, el wiring, foldout diagrams, etc.)
3. ✅ **Anthropic API key** in `.env`, connection tested — Claude Opus 4.8 replied "GEARHEAD online and ready to wrench."
4. ✅ Python 3.13.7 + venv + all deps installed (anthropic, pymupdf, chromadb, fastapi, uvicorn)

**SETUP COMPLETE — ready to build Step 1.**

---

*Blueprint saved. Built collaboratively, one approved section at a time.*
