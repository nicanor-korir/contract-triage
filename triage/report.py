"""Render a result as a one page memo."""
from __future__ import annotations

from .agent import available_checklists
from .pipeline import Result

LABEL = {"sign": "SIGN", "negotiate": "NEGOTIATE", "lawyer": "SEND TO A LAWYER"}
MARK = {"ok": "ok", "concern": "CONCERN", "missing": "missing"}


def memo(result: Result) -> str:
    c, s = result.classification, result.stats
    lines = [f"# Contract triage: {c.get('vendor', 'unknown vendor')}",
             "", f"**Verdict: {LABEL[result.verdict]}**", "",
             f"{c.get('summary', '')} Source: `{result.source}`", ""]
    if result.checklist is None:
        lines += _unsupported(c)
    elif result.reasons:
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
              f"- Time: {s['seconds']} s for {s['pages']} page{'' if s['pages'] == 1 else 's'}",
              f"- Model calls: {s['calls']}, agent steps: {s['agent_steps']}",
              f"- Tokens: {s['input_tokens']} in, {s['output_tokens']} out, "
              f"{s['cache_read_tokens']} read from cache",
              f"- Cost: {cost}"]
    if result.checklist:  # nothing was reviewed otherwise, so these would all read zero
        lines += [f"- Answers sent back for rework after verification: {s['first_pass_failures']} of {s['items']}",
                  f"- Still unverified after rework: {s['unverified_after_rework']}",
                  f"- Referenced documents fetched: {', '.join(s['documents_fetched']) or 'none'}"]
    lines += ["", "_This is triage to decide where your attention goes. It is not legal advice._", ""]
    return "\n".join(lines)


def _unsupported(c: dict) -> list[str]:
    """Why an unsupported document stopped here, and what to do with it."""
    what = (c.get("described_as") or "").strip() or "document of a type this tool does not review"
    supported = "; ".join(v["title"] for v in available_checklists().values())
    return ["## Why", "",
            f"- Detected: {what}. This tool reviews only: {supported}.",
            "- Nothing in the document was checked against a checklist, so there are no findings.",
            "", "## Next step", "",
            "- Have a lawyer who handles this kind of agreement read it before you sign.",
            "- If you think it is one of the supported types, the classifier got it wrong. "
            "Check the first pages, which are what it reads.", ""]


COLOUR = {"sign": "green", "negotiate": "yellow", "lawyer": "red"}
STATUS_STYLE = {"ok": "green", "concern": "bold yellow", "missing": "cyan"}


def show(result: Result, console=None) -> None:
    """Print the memo: coloured in a terminal, the plain Markdown memo anywhere else."""
    from rich.console import Console, Group
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = console or Console()
    text = memo(result)
    if not console.is_terminal:  # piped or redirected: keep the exact memo
        console.file.write(text + "\n")
        return

    header, *sections = text.split("\n## ")
    c, colour = result.classification, COLOUR[result.verdict]
    console.print(Panel(Group(
        Text(f"Verdict: {LABEL[result.verdict]}", style=f"bold {colour}"),
        Text(f"{c.get('vendor', 'unknown vendor')}. {c.get('summary', '')}", style="dim")),
        title="Contract triage", border_style=colour))
    for section in sections:
        console.print()
        name = section.split("\n", 1)[0]
        if name == "Checklist" and result.checklist:
            table = Table(title="Checklist", title_justify="left", expand=True)
            for column in ["Item", "Status", "Page", "Verified"]:
                table.add_column(column)
            for item in result.checklist["items"]:
                f = result.findings.get(item["id"])
                if f is None:
                    table.add_row(item["title"], Text("not answered", style="red"), "", Text("no", style="bold red"))
                    continue
                page = f"{f.page or ''}" + (f" ({f.doc_id})" if f.doc_id != "main" and f.page else "")
                verified = (Text("yes", style="green") if f.verification == "verified"
                            else Text("NO", style="bold red"))
                table.add_row(item["title"], Text(MARK[f.status], style=STATUS_STYLE[f.status]),
                              page, verified)
            console.print(table)
        else:
            console.print(Markdown("## " + section))
