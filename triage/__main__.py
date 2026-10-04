"""Usage: python -m triage <file or URL> [--out runs]"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from .pipeline import triage
from .report import memo


def main() -> None:
    parser = argparse.ArgumentParser(description="Triage one contract: sign, negotiate or lawyer.")
    parser.add_argument("source", help="Path to a PDF, HTML or text file, or an https URL")
    parser.add_argument("--out", default="runs", help="Folder for the memo, JSON and run log")
    args = parser.parse_args()

    result = triage(args.source)
    text = memo(result)
    print(text)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = re.sub(r"[^a-z0-9]+", "-", Path(args.source).stem.lower()).strip("-") or "contract"
    (out / f"{stamp}-{name}.md").write_text(text, encoding="utf-8")
    (out / f"{stamp}-{name}.json").write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")
    # One line per run. This log is the record of real use that the weekly numbers come from.
    with (out / "log.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"at": stamp, "source": args.source, "verdict": result.verdict,
                              **result.stats}) + "\n")


if __name__ == "__main__":
    main()
