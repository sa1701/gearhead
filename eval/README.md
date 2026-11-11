# GEARHEAD evaluation

GEARHEAD gives repair advice, so "it looked right on five queries" is not good enough.
This harness measures three things on a fixed question set:

1. **Retrieval.** Does the right manual page reach the model?
2. **Citations.** Does every page the answer cites exist in what the model was given?
3. **Refusals.** When the manual has no answer, does the system say so and stop?

Everything runs locally and costs nothing: Chroma for search, Ollama for the model.

## The question set

`gold/nissan-patrol-y61.jsonl` holds 142 questions for the Nissan Patrol Y61.

- **112 answerable.** Each started as a symptom in the Fix DB, which records the
  manual section and page it was extracted from. Those are the gold labels.
- **30 unanswerable.** Features this car does not have (TPMS, CarPlay, AdBlue, radar
  cruise), other vehicles, and questions no workshop manual answers. Each was checked
  against the indexed manual text: none of the key terms appear anywhere in it.

How the answerable set was built (`build_gold.py`):

| Step | Why |
|---|---|
| Drop duplicate symptoms and entries with no page | 329 Fix DB entries include 23 repeats |
| Keep an entry only if at least half of its symptom words appear on its gold page | The Fix DB was extracted by a model, so its page labels need a sanity check |
| At most 3 questions per page group, at most 40 per section | One transmission chart would otherwise supply a third of the set |
| Reword every symptom in owner language with a different model (Claude Haiku) | The manual's own wording is an easy test. A different model also means the model under test never searches for its own phrasing |
| Drop symptoms an owner could not notice (internal signals, scan-tool-only messages) | 61 of 173 candidates were dropped here |

The manual wording stays in the git-ignored `fixes/` folder and is looked up by hash,
so the committed gold file contains no manual text.

`python -m eval.build_gold review` writes a 30-question sheet for checking labels by hand.

## Retrieval results

112 answerable questions. A hit means a chunk from a gold page is in the top k.

| Search | page@1 | page@3 | page@6 | page@20 | section@6 |
|---|---|---|---|---|---|
| Owner question as typed | 26% | 43% | 59% | 76% | 96% |
| Query expansion (the first pipeline) | 17% | 29% | 41% | 63% | 91% |
| **Search wide, then rerank (the current pipeline)** | **37%** | **56%** | **69%** | **79%** | **97%** |
| Manual wording, no reranker (reference) | 40% | 62% | 70% | 84% | 94% |

The one-shot diagnosis passes 6 chunks to the model and the interview passes 20.

### What the first measurement showed

- **Finding the right section was already solved** (96% in the top 6). Finding the
  right page was not (59%).
- **Query expansion made page retrieval worse**, 59% down to 41% at k = 6. The local
  model turns a specific complaint ("will not shift from third to fourth") into
  generic phrases ("transmission shift issues"), and those phrases pull generic pages.
  Replaying the stored phrases offline confirmed it is the phrases, not the merge
  step: reciprocal rank fusion only brings the result back level with no expansion.
  (The expansion row used the interview settings. With the one-shot settings the same
  stored phrases give 43%, so the conclusion is the same.)
- **The right page was nearly always among the candidates.** It is in the top 50 of
  vector plus keyword search for 91% of questions. The problem was the order.

### What was tried, and what was kept

| Change | page@6 | Kept? |
|---|---|---|
| Keyword search (BM25) alone | 39% | No |
| Vector and keyword fused by rank | 60% to 63% | No. Within noise of 59%, and it adds an index to maintain |
| Rerank the top 30 vector hits with a cross-encoder | 70% | Yes |
| Rerank the top 50 | 70% | No gain over a smaller pool |
| Rerank vector plus keyword candidates | 69% to 70% | No gain |

The kept design is the simplest one that worked: take the top 40 vector hits for the
owner's own words, then let a small local cross-encoder (`ms-marco-MiniLM-L-12-v2`,
ONNX, CPU only) read the question against each chunk and re-order them. No model call
is spent on rewriting the question.

Scored through the same function the app calls, the right page is in the top 6 for
69% of questions, up from 59%. On the same 112 questions that is 16 gained and 5 lost
(exact sign test, p = 0.027). The first hit is right 37% of the time, up from 26%.
The gain was the same size on both halves of the set when it was split in two before
choosing the design (70% and 70%).

The old path is still there: set `GEARHEAD_RETRIEVAL=expand`.

## Coverage gate results

The first answer runs showed the local model (qwen2.5 7B) does not hold the safety
rule in its prompt. Asked about parts this car does not have, it wrote repair steps
anyway: a hybrid battery check, an AdBlue refill, a CVT fluid change. Of the first
15 unanswerable questions it gave steps for 13.

The reranker already scores how well each chunk answers the question, so the gate
uses that score: if the best chunk scores under 0.1, the brain declines and asks for
more detail, before any model call. Scored on all 142 questions through the same
function the app calls (`python -m eval.gate_eval`):

| Measure | Result | 95% interval | n |
|---|---|---|---|
| No answer in manual: stopped before the model | 93% | 79% to 98% | 30 |
| Answer in manual: stopped anyway | 15% | 10% to 23% | 112 |

Putting the gate in front of the answers the model had already given: repair steps
for an unanswerable question drop from 13 of 15 to 1 of 15.

What the numbers hide:

- **The 17 answerable questions it stops are mostly too vague to answer.** Eleven are
  one-line complaints such as "My Patrol won't start" or "A fault code shows up on
  the dash". Asking for more detail is the right reply to those. Six are specific
  questions the reranker scored badly, and those are real losses.
- **The two it misses are near neighbours of real content.** "The engine auto
  start-stop system has stopped working" scores 0.91 because the manual is full of
  engine starting and stopping. A different vehicle's engine ("1HZ valve clearances")
  scores 0.33. A score cannot catch these. They need a check on the model's answer.
- **The threshold was chosen on these same questions.** It blocked the same share of
  answerable questions in each half of the set (9 of 56 and 8 of 56), but it has not
  been tested on a second car or a fresh question set.

Set `GEARHEAD_GATE_MIN_SCORE=0` to switch the gate off.

## Vague complaints

Real owners rarely type a specific symptom. `gold/vague-nissan-patrol-y61.jsonl` holds
48 short, messy complaints ("turn key and just a click then nothing"), four for each
of 12 systems. There is no single right page for these, so a chunk counts as right
if it comes from a manual section that covers that system.

**The section labels are provisional.** They were assigned per system from where the
manual's own terms appear, and have not yet been confirmed by someone who works on
these cars. Treat the numbers below as a first reading.

| Search | First chunk right | Any of 6 right |
|---|---|---|
| Owner complaint as typed | 58% | 83% |
| Search wide, then rerank | 58% | 88% |

Reranking does not help here. It fixes page order for specific questions, and a
vague complaint has no specific page to find. The coverage gate asks for more
detail on 60% of these complaints.

### An idea that failed its safety check

The obvious fix for the interview: when the first search finds no good match, ask
the owner for more detail once, search again with the detail added, and only then
decline. `gold/followups-nissan-patrol-y61.json` holds a simulated owner reply for
every vague and unanswerable question, and `python -m eval.gate_eval followup` replays
that flow.

| Measure | Result | n |
|---|---|---|
| Vague complaint gets a good match straight away | 40% | 48 |
| Vague complaint gets a good match after one round of detail | 48% | 48 |
| Vague complaint still declined | 12% | 48 |
| Unanswerable question still declined after the owner adds detail | 10% | 30 |

It lets 88% of vague complaints through, and it lets 27 of 30 unanswerable questions
through as well, including one about a different make of car. A longer question
always finds some chunk that scores well. The change was reverted before release.

Two cheaper rules were tested on the same data and neither separates the two cases:

- **A stricter score on the second round.** Scoring the question, the detail, or both
  together gives an AUC between 0.39 and 0.60, which is no better than chance.
- **Words the manual never uses.** 25 of 30 unanswerable questions contain one
  ("tpms", "carplay", "adblue"), but so do 22 of 48 vague complaints ("clunk",
  "aircon", "speedo"). A word list cannot tell a missing feature from everyday slang.

What this means: the reranker score measures whether the text matches a page. It
does not measure whether the car has the part. Telling "vague but covered" from
"not on this car" needs a reader that understands the question.

### The subject check

The local model is poor at judging whether the manual covers a question, so it is
not asked to. It is asked one small thing: name the part or feature the question is
about, in workshop wording ("turn key and just a click" becomes "starting system").
That name is then looked up in the manual with the same search and reranker. If the
part has a good match (0.5 or more), the question goes ahead. The model names the
part; the manual lookup makes the decision.

This runs only for questions the score would decline, and takes about 2 seconds on
a laptop CPU. `python -m eval.gate_eval subject` runs it on all 190 questions:

| Question type | Declined by score alone | Declined with the subject check |
|---|---|---|
| No answer in manual (should be declined) | 27 of 30 | 26 of 30 |
| Specific symptom, answer in manual | 17 of 112 | 5 of 112 |
| Vague complaint | 29 of 48 | 3 of 48 |

Wrongly declined questions drop from 46 to 8. The cost is one more unanswerable
question getting through: "rear parking sensors", because the manual has pages that
mention sensors and parking. The three vague complaints still declined are ones
where the model could not name a part ("shudder through floor").

Read these numbers with care:

- The 0.5 threshold was chosen on these same 190 questions. In the first pass three
  unanswerable subjects scored 0.44 to 0.47, just under it. A fresh set of questions
  would be a fairer test.
- The two questions that already beat the score gate (auto start-stop, and valve
  clearances for a different make of car) are not caught by this check either. The
  model was asked to name a different vehicle in the subject and did not.
- One question sits on the score threshold: it scored 0.090 in the earlier gate run
  and 0.108 in this one, so "declined by score alone" is 27 here and 28 above. The
  cause of the change has not been found.
- An owner can get past the gate by naming a real part. The answer they then get is
  still built only from manual pages.

### The held-out test, and what it showed

Both thresholds were chosen on the 190 questions above, so those numbers flatter the
gate. `gold/holdout-nissan-patrol-y61.jsonl` holds 37 questions written afterwards by
a separate model that had seen no scores. 44 were drafted. Seven were removed before
any run: four repeated a topic from the subject prompt's examples, one repeated an
existing question, and two were about parts the car partly has. Each remaining label
was checked against the manual text. `python -m eval.gate_eval subject holdout` runs it:

| Question type | Declined by score alone | Declined with the subject check |
|---|---|---|
| No answer in manual (should be declined) | 10 of 17 | 10 of 17 |
| Specific symptom, answer in manual | 0 of 9 | 0 of 9 |
| Vague complaint | 8 of 11 | 6 of 11 |

The gate is much weaker on fresh questions than the first set suggested:

- **7 of 17 unanswerable questions get through, all at the score gate.** Four of the
  five questions about a different make of car pass ("timing belt on a Honda Civic"
  scores 0.80), because the manual has pages on the same job for the Patrol. The first
  set had only two such questions, which hid this. Three questions about parts the car
  lacks also pass, because their wording overlaps real pages ("electric parking brake"
  matches the parking brake pages).
- **The subject check let no extra unanswerable question through,** but it rescued only
  2 of 8 declined vague complaints, against 26 of 29 on the first set. The model named
  a symptom instead of a part ("engine tapping", "cold start smoke"), or a part under a
  name the manual does not use ("handbrake", "headlights").
- With 17, 9 and 11 questions these counts are rough, but the direction is clear.

The next fix to test is a check for another make or model named in the question,
before the score is read at all. The held-out set must not be used to tune it.

## Grounding and refusal results

See `results/REPORT.md`. It is regenerated by `python -m eval.report`.

An answer is scored as one of three outcomes:

- **refused**: says the manual does not cover it and gives no repair steps
- **hedged**: says the manual does not cover it, then gives repair steps anyway
- **answered**: gives steps with no warning

For a repair tool, "hedged" on an unanswerable question is a failure, not a pass.
A phrase match alone would have counted it as a refusal.

## Limits

- One car, one manual set, one local model (qwen2.5 7B). The numbers describe this
  setup, not GEARHEAD in general.
- The vague-complaint labels are provisional and the follow-up replies are simulated
  by a model, not collected from owners.
- Gold page labels come from a model-extracted Fix DB. They passed an automatic
  word-overlap check, and a hand check of 30 is still to do.
- Faults often span neighbouring pages. Counting a hit within one page either side
  raises page@6 from 59% to 67%.
- Query expansion is sampled at temperature 0.3 and was run once.
- Every question came from a Fix DB entry, and the Fix DB is also fed to the model at
  answer time. Retrieval is scored on the raw manual index only, so it is not affected.
  The grounding numbers are, so the report shows "correct page among the retrieved
  chunks" separately from "correct page in context", and `grounding_eval.py` has a
  `--no-fixdb` switch.
- Grounding uses 30 of the 112 answerable questions plus all 30 unanswerable ones,
  because one answer takes about three minutes on this laptop's CPU.
- The outcome classifier is a rule, not a judge. Read `results/grounding.jsonl` before
  trusting an edge case.

## Running it

```bash
python -m eval.retrieval_eval          # plain, expanded and manual wording. About 12 minutes
python -m eval.retrieval_eval rerank   # the rerank pipeline. No model call
python -m eval.gate_eval               # the coverage gate. No model call
python -m eval.retrieval_eval vague    # vague complaints, scored by system. No model call
python -m eval.gate_eval followup      # ask-once-then-search-again replay. No model call
python -m eval.gate_eval subject       # the subject check. One short model call per declined question
python -m eval.gate_eval subject holdout   # the same, on 37 questions never used for tuning
python -m eval.grounding_eval          # hours on a laptop CPU, resumes if stopped
python -m eval.report              # writes results/summary.json and results/REPORT.md
pytest                             # unit tests for the scoring code
```

Set `GEARHEAD_OLLAMA_NUM_GPU=0` to force the model onto the CPU.

`grounding_eval` tests whichever pipeline `GEARHEAD_RETRIEVAL` selects and writes one
file per pipeline (`grounding.jsonl` for `expand`, `grounding_rerank.jsonl` for
`rerank`), so a baseline run and a rerank run never mix.
