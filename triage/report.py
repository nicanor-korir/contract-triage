"""Render a result as a one page memo."""
from __future__ import annotations

from .pipeline import Result

LABEL = {"sign": "SIGN", "negotiate": "NEGOTIATE", "lawyer": "SEND TO A LAWYER"}
MARK = {"ok": "ok", "concern": "CONCERN", "missing": "missing"}


def memo(result: Result) -> str:
    c, s = result.classification, result.stats
    lines = [f"# Contract triage: {c.get('vendor', 'unknown vendor')}",
             "", f"**Verdict: {LABEL[result.verdict]}**", "",
             f"{c.get('summary', '')} Source: `{result.source}`", ""]
    if result.reasons:
        lines += ["## Why", ""] + [f"- {r}" for r in result.reasons] + [""]
    else:
        lines += ["## Why", "", "Every checklist item was answered, verified and acceptable.", ""]

    if result.checklist:
        lines += ["## Checklist", "", "| Item | Status | Page | Verified |", "| --- | --- | --- | --- |"]
        for item in result.checklist["items"]:
            f = result.findings.get(item["id"])
            if f is None:
                lines.append(f"| {item['title']} | not answered | | no |")
            else:
                page = f"{f.page}" if f.page else ""
                if f.doc_id != "main" and page:
                    page += f" ({f.doc_id})"
                lines.append(f"| {item['title']} | {MARK[f.status]} | {page} | "
                             f"{'yes' if f.verification == 'verified' else 'NO'} |")
        lines += ["", "## Clauses", ""]
        for item in result.checklist["items"]:
            f = result.findings.get(item["id"])
            if f is None:
                continue
            lines.append(f"**{item['title']}** ({MARK[f.status]}). {f.explanation}")
            if f.quote:
                lines.append(f"> {f.quote}")
            if f.note:
                lines.append(f"_Note: {f.note}_")
            lines.append("")

    cost = f"${s['cost_usd']:.4f}" if s.get("cost_usd") is not None else "prices not configured"
    lines += ["## Run", "",
              f"- Time: {s['seconds']} s for {s['pages']} pages",
              f"- Model calls: {s['calls']}, agent steps: {s['agent_steps']}",
              f"- Tokens: {s['input_tokens']} in, {s['output_tokens']} out, "
              f"{s['cache_read_tokens']} read from cache",
              f"- Cost: {cost}",
              f"- Answers sent back for rework after verification: {s['first_pass_failures']} of {s['items']}",
              f"- Still unverified after rework: {s['unverified_after_rework']}",
              f"- Referenced documents fetched: {', '.join(s['documents_fetched']) or 'none'}",
              "", "_This is triage to decide where your attention goes. It is not legal advice._", ""]
    return "\n".join(lines)
