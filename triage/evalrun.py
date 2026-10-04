"""Run the test set and write the scoreboard.

Usage: python -m triage.evalrun eval/manifest.csv
The manifest has three columns: file, expected_verdict, notes.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from .pipeline import triage


def main(manifest_path: str = "eval/manifest.csv") -> None:
    manifest = Path(manifest_path)
    rows = [r for r in csv.DictReader(manifest.open(encoding="utf-8"))
            if r.get("file") and not r["file"].startswith("#")]
    if not rows:
        sys.exit("The manifest has no contracts yet. Add rows to eval/manifest.csv first.")

    results = []
    for row in rows:
        source = row["file"]
        if not source.startswith("http"):
            source = str(manifest.parent / source)
        expected = row["expected_verdict"].strip().lower()
        print(f"Running {row['file']} ...", flush=True)
        try:
            result = triage(source)
            results.append({"file": row["file"], "expected": expected, "got": result.verdict,
                            "match": result.verdict == expected, **result.stats})
            (manifest.parent / "results").mkdir(exist_ok=True)
            out = manifest.parent / "results" / (Path(row["file"]).stem + ".json")
            out.write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")
        except Exception as error:
            results.append({"file": row["file"], "expected": expected, "got": f"error: {error}",
                            "match": False})

    done = [r for r in results if "seconds" in r]
    n = len(results)
    matches = sum(r["match"] for r in results)
    false_signs = sum(1 for r in results if r["expected"] == "lawyer" and r["got"] == "sign")
    items = sum(r["items"] for r in done)
    first_fail = sum(r["first_pass_failures"] for r in done)
    unverified = sum(r["unverified_after_rework"] for r in done)
    costs = [r["cost_usd"] for r in done if r.get("cost_usd") is not None]

    def avg(values):
        return round(sum(values) / len(values), 2) if values else None

    lines = ["# Scoreboard", "",
             "| Measure | Result |", "| --- | --- |",
             f"| Contracts run | {n} |",
             f"| Verdict matches my label | {matches} of {n} |",
             f"| Labelled lawyer, agent said sign | {false_signs} |",
             f"| Answers sent back for rework after verification | {first_fail} of {items} |",
             f"| Answers still unverified after rework | {unverified} of {items} |",
             f"| Average time per contract | {avg([r['seconds'] for r in done])} s |",
             f"| Average cost per contract | {('$' + str(avg(costs))) if costs else 'prices not configured'} |",
             "", "| Contract | Expected | Got | Match | Seconds |", "| --- | --- | --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r['file']} | {r['expected']} | {r['got']} | "
                     f"{'yes' if r['match'] else 'NO'} | {r.get('seconds', '')} |")
    text = "\n".join(lines) + "\n"
    (manifest.parent / "scoreboard.md").write_text(text, encoding="utf-8")
    print("\n" + text)


if __name__ == "__main__":
    main(*sys.argv[1:2])
