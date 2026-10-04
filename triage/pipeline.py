"""Ingest, classify, review, verify, rework once, decide."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import agent, decide as rules, verify
from .ingest import Document, load
from .llm import LLM


@dataclass
class Result:
    source: str
    classification: dict
    checklist: dict | None
    findings: dict[str, agent.Finding]
    verdict: str
    reasons: list[str]
    stats: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"source": self.source, "classification": self.classification,
                "verdict": self.verdict, "reasons": self.reasons,
                "findings": [f.as_dict() for f in self.findings.values()],
                "stats": self.stats}


def _verify_all(llm: LLM, checklist: dict, findings: dict, docs: dict[str, Document],
                main: Document, probe: bool) -> dict[str, str]:
    verify.verify_quotes(findings, docs)
    verify.judge_support(llm, checklist, findings)
    failed = verify.failures(checklist, findings)
    if probe:
        for check_id, reason in verify.probe_absence(checklist, findings, main).items():
            failed.setdefault(check_id, reason)
    return failed


def triage(source: str, llm: LLM | None = None) -> Result:
    started = time.time()
    llm = llm or LLM()
    doc = load(source)
    checklists = agent.available_checklists()
    classification = agent.classify(llm, doc, checklists)
    checklist = checklists.get(classification["doc_type"])

    findings, extra, steps, first_pass_failed = {}, {}, 0, {}
    if checklist is not None:
        findings, extra, steps = agent.run_checks(llm, doc, checklist)
        docs = {"main": doc, **extra}
        first_pass_failed = _verify_all(llm, checklist, findings, docs, doc, probe=True)
        if first_pass_failed:
            # One rework round. The agent gets the reasons and answers only the failed items.
            redo, extra, more = agent.run_checks(
                llm, doc, checklist, only=set(first_pass_failed),
                feedback=first_pass_failed, extra=extra)
            steps += more
            docs = {"main": doc, **extra}
            _verify_all(llm, checklist, redo, docs, doc, probe=False)
            for check_id, finding in redo.items():
                if check_id in first_pass_failed:
                    finding.note = (finding.note + " " if finding.note else "") + "(second attempt)"
                findings[check_id] = finding

    verdict, reasons = rules.decide(checklist, findings)
    stats = {
        "seconds": round(time.time() - started, 1),
        "pages": len(doc.pages),
        "agent_steps": steps,
        "documents_fetched": [d.source for d in extra.values()],
        "items": len(checklist["items"]) if checklist else 0,
        "first_pass_failures": len(first_pass_failed),
        "first_pass_reasons": first_pass_failed,
        "unverified_after_rework": sum(
            1 for i in (checklist["items"] if checklist else [])
            if i["id"] not in findings or findings[i["id"]].verification != "verified"),
        **llm.usage.as_dict(),
    }
    return Result(source, classification, checklist, findings, verdict, reasons, stats)
