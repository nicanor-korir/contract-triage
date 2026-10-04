# Contract triage agent

Reads one vendor agreement and returns one of three verdicts with cited reasons: **sign**, **negotiate** or **send to a lawyer**.
It is built for a technical founder with no legal team, and it is triage, not legal advice.

## Quick start

    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...            # see .env.example for the optional settings
    python -m pytest tests -q               # 22 tests, no API key needed
    python -m triage examples/sample_terms.txt
    python -m triage https://vendor.example/terms
    python -m triage path/to/contract.pdf

Each run prints a memo and saves it with the full JSON to `runs/`, and appends one line to `runs/log.jsonl`.

## How it works

1. **Ingest** (`ingest.py`). PDF, HTML, text or URL becomes numbered pages.
2. **Classify** (`agent.py`). One model call picks the checklist. Anything unsupported goes straight to "lawyer".
3. **Review** (`agent.py`). A tool loop works through the checklist. The agent records one finding per item with a word for word quote and a page, and it can fetch documents the contract links to, such as a DPA. It can only fetch URLs that appear in the contract.
4. **Verify** (`verify.py`). Three checks, two of them with no model:
   - every quote must exist word for word in the source,
   - any item reported missing is challenged if its keywords appear in the text,
   - a second model call that sees only the quotes judges whether each one supports the claimed status.
5. **Rework** (`pipeline.py`). Failed items go back to the agent once, with the reason.
6. **Decide** (`decide.py`). Plain rules compute the verdict from the findings. No model is involved, so every verdict can be traced to a line in the checklist.
7. **Report** (`report.py`). A memo with the verdict, reasons, clauses, time, tokens and cost.

The checklists in `triage/checklists/` are the product. Edit them until they match how you would review a contract yourself.

## What has and has not been tested

The 22 tests cover ingestion, quote verification, the absence check, the verdict rules, the fetch allow list and the full pipeline including rework.
They use a scripted stand in for the model (`tests/fake.py`), so the plumbing is proven and the model's judgement is not.
The first live run is where the prompts and checklist wording will need tuning, and `eval/LABELING.md` explains how to measure that.

## Measuring it

    python -m triage.evalrun eval/manifest.csv

See `eval/LABELING.md` for how to build and label the test set.

## Limits in this version

- English contracts only, and two types: SaaS terms or MSAs, and DPAs.
- Scanned PDFs need OCR first.
- Contracts over about 400,000 characters are truncated (`TRIAGE_MAX_DOC_CHARS`).
- One rework round. Anything still unverified pushes the verdict towards "lawyer".
- The contract text is treated as data and the agent is told to ignore instructions inside it, but this has not been tested against a hostile document yet.
