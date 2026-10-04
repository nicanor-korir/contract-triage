"""The verdict is computed by rules, never by a model, so it can be audited line by line."""
from __future__ import annotations

from . import config
from .agent import Finding

RANK = {"sign": 0, "negotiate": 1, "lawyer": 2}
EFFECT = {"ok": "sign", "negotiate": "negotiate", "lawyer": "lawyer"}


def decide(checklist: dict | None, findings: dict[str, Finding]) -> tuple[str, list[str]]:
    """Return the verdict and the reasons behind it."""
    if checklist is None:
        return "lawyer", ["This type of contract is not supported, so it goes to a person."]

    verdict, reasons, unverified = "sign", [], 0
    for item in checklist["items"]:
        finding = findings.get(item["id"])
        if finding is None or finding.verification != "verified":
            unverified += 1
            effect = "lawyer" if item.get("critical") else "negotiate"
            reasons.append(f"{item['title']}: the agent could not verify its answer ({effect}).")
        elif finding.status == "concern":
            effect = EFFECT[item["if_concern"]]
            reasons.append(f"{item['title']}: {finding.explanation} ({effect}).")
        elif finding.status == "missing":
            effect = EFFECT[item["if_missing"]]
            if effect != "sign":
                reasons.append(f"{item['title']}: not addressed in the contract ({effect}).")
        else:
            effect = "sign"
        if RANK[effect] > RANK[verdict]:
            verdict = effect

    if unverified / len(checklist["items"]) > config.UNVERIFIED_LIMIT:
        verdict = "lawyer"
        reasons.insert(0, f"{unverified} of {len(checklist['items'])} items could not be verified, "
                          "which is too many to trust this review.")
    return verdict, reasons
