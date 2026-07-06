<!-- markdownlint-disable MD033 -->
<div align="center">

# 🚗 GEARHEAD

**A local-first AI assistant that diagnoses car problems and gives the exact fix — grounded in real workshop manuals, with the diagram and the page it came from.**

Python · FastAPI · Retrieval-Augmented Generation · Multimodal LLM · Ollama · ChromaDB · PyMuPDF

<img src="docs/demo.gif" alt="GEARHEAD demo — a diagnosis interview ending in a cited fix with the manual diagram" width="720" />

</div>

---

## What it does

Tell GEARHEAD what's wrong — in plain words (*"my brakes shudder when I slow down"*) or as an OBD fault code — and it interviews you like a mechanic, one question at a time, then returns a **grounded, cited fix**: the steps, the real labelled diagram from the service manual, and the exact page it came from.

It runs locally. In Claude mode the only thing that leaves your machine is the call to the language model — and in **Ollama mode, nothing leaves at all**: the whole pipeline runs offline on your own GPU, for free.

### Why it's built this way
- **Grounded, not guessed.** Every answer is retrieved from real manuals and cites its source page. If the manuals don't cover it, GEARHEAD says so instead of hallucinating — because a wrong car repair is a safety risk.
- **Reads diagrams.** Manual pages are rendered to images and, in Claude mode, passed to a multimodal model that interprets labelled engineering diagrams (e.g. distinguishing a front vs. rear brake caliper schematic). Ollama mode still renders and shows the cited diagram pages — captioned from the manual's own metadata instead of vision.
- **Add a car = drop a PDF.** The ingestion pipeline is car-agnostic; the hero car is the Nissan Patrol (Y61), the most common vehicle across the Gulf region.

---

## How it works

```
        You (browser, car-dashboard UI)
                     │
        ┌────────────▼─────────────┐
        │   FastAPI backend         │   runs the interview loop
        └─────┬───────────────┬─────┘
              │               │
   ┌──────────▼─────┐   ┌─────▼──────────────┐
   │  The Library   │   │   The Brain (LLM)   │
   │  Chroma vector │   │  reasons + reads    │
   │  DB of manuals │   │  diagrams (vision)  │
   └──────────▲─────┘   └─────────────────────┘
              │
        📂 /manuals  ← service-manual PDFs you drop in
```

**Pipeline**
1. **Ingest** — service-manual PDFs are parsed (PyMuPDF), chunked, embedded, and stored in a local Chroma vector database (22 Patrol manuals → ~2,450 indexed chunks).
2. **Retrieve** — a query-expansion step rewrites messy symptoms into focused search phrases, then pulls the most relevant manual pages.
3. **Interview** — the model asks the smartest next question to narrow the diagnosis, looping until it's confident.
4. **Diagnose** — it returns a cited fix: steps + the rendered manual diagram + source page.

**Engineering highlights**
- **Swappable model interface** (`AIProvider`) — the underlying LLM is pluggable behind a clean interface: the cloud Claude API (vision + prompt caching) or a fully local Ollama model, switched with a single env var.
- **Prompt caching** across the system + retrieved-context block cuts repeated per-turn token cost by ~90%.
- **End-to-end tested** via FastAPI's `TestClient` (full flow + diagram serving).

---

## Tech stack

| Layer | Tool |
|---|---|
| Backend / web | Python, FastAPI |
| Retrieval | ChromaDB (local vector store) |
| PDF + image extraction | PyMuPDF |
| Reasoning + vision | Claude API (vision) **or** local Ollama (offline, free) behind a pluggable `AIProvider` |
| Frontend | HTML / CSS / vanilla JS (car-dashboard theme, SVG confidence gauge) |

---

## Project status

**Working end-to-end:** manual ingestion + search, grounded cited diagnosis, the interview loop, diagram rendering, a themed FastAPI web app — and a **fully offline Ollama mode** (no API key, no cost).

**Next:** prove "add a car = drop a PDF" with a second vehicle.

---

## Running it locally

```bash
# 1. create + activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows  (use source .venv/bin/activate on macOS/Linux)

# 2. install dependencies
pip install -r requirements.txt

# 3. add your model API key to a local .env file (see .env.example)
#    — or skip the key entirely and use Ollama mode (below)

# 4. drop service-manual PDFs into /manuals, then build the search index
python ingest_manuals.py

# 5. launch the app
python run_app.py               # → http://127.0.0.1:8000
```

### Running it 100% free & offline (Ollama)

No API key, no cloud, no cost — the brain runs on your own machine:

```bash
ollama pull qwen2.5:7b-instruct   # once (any 7–8B instruct model works)
```

Then in your `.env`:

```ini
GEARHEAD_PROVIDER=ollama
GEARHEAD_OLLAMA_MODEL=qwen2.5:7b-instruct
```

With no `ANTHROPIC_API_KEY` set, GEARHEAD picks Ollama automatically. The UI's engine badge shows which brain is under the hood. Runs comfortably on an 8 GB GPU.

See **BLUEPRINT.md** for the full design rationale and build log.

---

## Project layout

```
gearhead/
├── BLUEPRINT.md          # design + build log
├── requirements.txt
├── ingest_manuals.py     # build the manual search index
├── run_app.py            # launch the web app
├── manuals/              # service-manual PDFs (git-ignored — see note below)
└── src/
    ├── config.py         # keys + paths
    ├── ai/               # swappable AIProvider interface + implementations
    ├── library/          # manual ingestion, search, image rendering
    ├── brain/            # diagnosis + interview engine
    └── web/              # FastAPI server + car-dashboard UI
```

---

## ⚠️ Disclaimer & legal note

GEARHEAD is a personal/educational project. Its output is **not a substitute for a qualified mechanic** — every diagnosis carries a *"always verify with a professional"* warning, and the system is designed to refuse to guess when the manuals don't cover a problem.

Service manuals are copyrighted. **No manuals are included in this repository** — the `manuals/` directory and `.env` are git-ignored. Users supply their own PDFs locally for personal use.
