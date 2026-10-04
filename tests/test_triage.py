import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fake import MISSING, SAMPLE, FakeClient, concern, ok  # noqa: E402

from triage import agent, verify  # noqa: E402
from triage.decide import decide  # noqa: E402
from triage.ingest import Document, Page, load, squash  # noqa: E402
from triage.llm import LLM  # noqa: E402
from triage.pipeline import triage  # noqa: E402
from triage.report import memo  # noqa: E402

SAMPLE_PATH = str(Path(__file__).parent.parent / "examples" / "sample_terms.txt")


def finding(check_id, status, quote="", page=1, verification="pending"):
    return agent.Finding(check_id, status, quote, page, "main", "because", verification)


# ---------------------------------------------------------------- ingest

def test_text_file_is_split_into_pages_and_urls_are_collected():
    doc = load(SAMPLE_PATH)
    assert len(doc.pages) >= 2
    assert "https://nimbusdesk.example/legal/dpa" in doc.urls()


def test_pdf_pages_keep_their_numbers(tmp_path):
    from reportlab.pdfgen import canvas
    path = tmp_path / "c.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(72, 720, "Page one talks about fees.")
    pdf.showPage()
    pdf.drawString(72, 720, "Liability is limited to the fees paid in twelve months.")
    pdf.save()
    doc = load(str(path))
    assert [p.number for p in doc.pages] == [1, 2]
    assert verify.locate("limited to the fees paid in twelve months", doc) == 2


def test_squash_tolerates_layout_but_not_wording():
    assert squash("liabil-\nity  is “capped”") == squash('liability is "capped"')
    assert squash("liability is capped") != squash("liability is not capped")


# ---------------------------------------------------------------- verify

DOC = Document("t", [Page(1, "The vendor may terminate at any time. Fees are due annually and the"),
                     Page(2, "customer may not withhold payment. Liability is capped at fees paid.")])


def test_exact_quote_is_verified_and_wrong_page_is_corrected():
    f = {"a": finding("a", "concern", "Liability is capped at fees paid", page=1)}
    verify.verify_quotes(f, {"main": DOC})
    assert f["a"].verification == "verified" and f["a"].page == 2


def test_paraphrase_is_rejected():
    f = {"a": finding("a", "ok", "The vendor's liability is capped at the fees paid")}
    verify.verify_quotes(f, {"main": DOC})
    assert f["a"].verification == "unsupported"


def test_quote_across_a_page_break_is_found():
    f = {"a": finding("a", "ok", "Fees are due annually and the customer may not withhold payment")}
    verify.verify_quotes(f, {"main": DOC})
    assert f["a"].verification == "verified" and f["a"].page == 1


def test_short_quote_and_unknown_document_are_rejected():
    f = {"a": finding("a", "ok", "Fees are due"), "b": finding("b", "ok", "x" * 40)}
    f["b"].doc_id = "ref9"
    verify.verify_quotes(f, {"main": DOC})
    assert f["a"].verification == f["b"].verification == "unsupported"


def test_missing_claim_is_challenged_when_keywords_appear():
    checklist = {"items": [{"id": "termination", "keywords": ["terminat"]},
                           {"id": "sla", "keywords": ["uptime"]}]}
    f = {"termination": finding("termination", "missing"), "sla": finding("sla", "missing")}
    suspicious = verify.probe_absence(checklist, f, DOC)
    assert list(suspicious) == ["termination"]


# ---------------------------------------------------------------- decide

CHECKLIST = agent.available_checklists()["saas_terms"]


def all_ok():
    return {i["id"]: finding(i["id"], "ok", "q" * 30, verification="verified")
            for i in CHECKLIST["items"]}


def test_clean_contract_is_sign():
    assert decide(CHECKLIST, all_ok())[0] == "sign"


def test_negotiable_concern_is_negotiate():
    f = all_ok()
    f["auto_renewal"].status = "concern"
    assert decide(CHECKLIST, f)[0] == "negotiate"


def test_serious_concern_is_lawyer():
    f = all_ok()
    f["customer_indemnity"].status = "concern"
    assert decide(CHECKLIST, f)[0] == "lawyer"


def test_unverified_critical_item_is_lawyer_and_minor_item_is_negotiate():
    f = all_ok()
    f["sla"].verification = "unsupported"
    assert decide(CHECKLIST, f)[0] == "negotiate"
    f["liability_cap"].verification = "unsupported"
    assert decide(CHECKLIST, f)[0] == "lawyer"


def test_too_many_unverified_items_is_lawyer():
    f = all_ok()
    for check_id in ["sla", "dpa", "auto_renewal", "price_changes"]:
        del f[check_id]
    verdict, reasons = decide(CHECKLIST, f)
    assert verdict == "lawyer" and "too many" in reasons[0]


def test_unsupported_contract_type_is_lawyer():
    assert decide(None, {})[0] == "lawyer"


# -------------------------------------------------------------- pipeline

def test_full_run_on_the_sample_contract():
    client = FakeClient(copy.deepcopy(SAMPLE))
    result = triage(SAMPLE_PATH, LLM(client))
    assert result.verdict == "negotiate"
    assert result.stats["unverified_after_rework"] == 0
    assert all(f.verification == "verified" for f in result.findings.values())
    assert "NEGOTIATE" in memo(result)


def test_fabricated_quote_is_caught_and_fixed_on_rework():
    answers = copy.deepcopy(SAMPLE)
    answers["liability_cap"] = [
        ok("Liability is capped at twelve months of fees for both parties", 2),  # invented
        SAMPLE["liability_cap"][0],
    ]
    client = FakeClient(answers)
    result = triage(SAMPLE_PATH, LLM(client))
    assert result.stats["first_pass_failures"] == 1
    assert result.findings["liability_cap"].status == "concern"
    assert result.findings["liability_cap"].verification == "verified"
    rework_task = client.calls[3]["messages"][0]["content"][1]["text"]
    assert "quote not found in the document" in rework_task
    assert "- sla:" not in rework_task  # only the failed item is redone


def test_quote_that_stays_fabricated_escalates_to_lawyer():
    answers = copy.deepcopy(SAMPLE)
    answers["liability_cap"] = [ok("Liability is capped at twelve months of fees for both parties", 2)]
    result = triage(SAMPLE_PATH, LLM(FakeClient(answers)))
    assert result.verdict == "lawyer"
    assert result.stats["unverified_after_rework"] == 1


def test_second_reader_disagreement_triggers_rework():
    client = FakeClient(copy.deepcopy(SAMPLE), judge_rejects={"sla"})
    result = triage(SAMPLE_PATH, LLM(client))
    assert result.stats["first_pass_failures"] == 1
    assert result.findings["sla"].verification == "verified"


def test_false_missing_is_sent_back_once():
    answers = copy.deepcopy(SAMPLE)
    answers["termination"] = [MISSING, SAMPLE["termination"][0]]
    result = triage(SAMPLE_PATH, LLM(FakeClient(answers)))
    assert result.stats["first_pass_failures"] == 1
    assert result.findings["termination"].status == "ok"


def test_unsupported_type_skips_the_agent():
    client = FakeClient({}, doc_type="employment_contract")
    result = triage(SAMPLE_PATH, LLM(client))
    assert result.verdict == "lawyer" and len(client.calls) == 1


# ------------------------------------------------------------------ fetch

def test_fetch_refuses_urls_that_are_not_in_the_contract():
    doc = load(SAMPLE_PATH)
    assert agent._fetch("https://evil.example/steal", doc, {}).startswith("Refused")
    assert agent._fetch("http://nimbusdesk.example/legal/dpa", doc, {}).startswith("Refused")


def test_fetch_of_a_listed_url_is_attempted(monkeypatch):
    doc = load(SAMPLE_PATH)
    monkeypatch.setattr(agent, "load", lambda url: Document(url, [Page(1, "DPA text")]))
    extra = {}
    out = agent._fetch("https://nimbusdesk.example/legal/dpa", doc, extra)
    assert "doc_id 'ref1'" in out and "ref1" in extra


# -------------------------------------------------------------- llm / loop

def test_thinking_blocks_are_kept_for_the_next_turn():
    from types import SimpleNamespace as NS
    from triage.llm import blocks_to_dicts
    content = [NS(type="thinking", thinking="", signature="sig"),
               NS(type="redacted_thinking", data="opaque"),
               NS(type="tool_use", id="tu_1", name="finish", input={})]
    assert [b["type"] for b in blocks_to_dicts(content)] == ["thinking", "redacted_thinking", "tool_use"]
    assert blocks_to_dicts(content)[0]["signature"] == "sig"


def test_finding_without_a_valid_status_is_refused_not_a_crash():
    answers = copy.deepcopy(SAMPLE)
    answers["sla"] = [{"quote": "makes no commitment regarding availability", "page": 2,
                       "doc_id": "main", "explanation": "No status given."}]
    result = triage(SAMPLE_PATH, LLM(FakeClient(answers)))
    assert "sla" not in result.findings
    assert result.verdict != "sign"


def test_forced_tool_does_not_force_tool_choice_and_asks_again():
    # Sonnet 5.5 rejects tool_choice "tool" or "any" with a 400.
    from types import SimpleNamespace as NS
    from triage.llm import forced_tool

    class TextFirst:
        def __init__(self):
            self.calls, self.messages = [], self

        def create(self, **kwargs):
            self.calls.append(kwargs)
            usage = NS(input_tokens=1, output_tokens=1,
                       cache_creation_input_tokens=0, cache_read_input_tokens=0)
            if len(self.calls) == 1:
                return NS(content=[NS(type="text", text="It is SaaS terms.")], usage=usage)
            return NS(content=[NS(type="tool_use", id="t", name="classify",
                                  input={"doc_type": "saas_terms"})], usage=usage)

    client = TextFirst()
    result = forced_tool(LLM(client), tool=agent.CLASSIFY_TOOL, system="s", user="u")
    assert result == {"doc_type": "saas_terms"} and len(client.calls) == 2
    assert all(c["tool_choice"]["type"] == "auto" for c in client.calls)


def test_finding_the_second_reader_skips_is_not_verified():
    class SkipsSla(FakeClient):
        def create(self, **kwargs):
            response = super().create(**kwargs)
            for block in response.content:
                if block.name == "judge":
                    block.input["verdicts"] = [v for v in block.input["verdicts"]
                                               if v["check_id"] != "sla"]
            return response

    f = {"sla": finding("sla", "concern", "makes no commitment regarding availability",
                        verification="verified")}
    verify.judge_support(LLM(SkipsSla({})), CHECKLIST, f)
    assert f["sla"].verification == "unsupported"


def test_second_reader_is_told_the_acceptable_jurisdictions():
    client = FakeClient({})
    f = {"governing_law": finding(
        "governing_law", "ok", "governed by the laws of Ireland, and the courts of Dublin",
        verification="verified")}
    verify.judge_support(LLM(client), CHECKLIST, f)
    assert "Ireland" in client.calls[0]["messages"][0]["content"].split("check_id:")[0]


# ------------------------------------------------------------ readability

def test_nearly_empty_page_fails_before_any_model_call(tmp_path):
    path = tmp_path / "terms.html"
    path.write_text("<html><body><div id='root'></div><p>Please enable JavaScript.</p>"
                    "<script>render()</script></body></html>")
    client = FakeClient(copy.deepcopy(SAMPLE))
    with pytest.raises(ValueError, match="too little"):
        triage(str(path), LLM(client))
    assert client.calls == []


def test_mostly_scanned_pdf_fails_before_any_model_call(tmp_path):
    from reportlab.pdfgen import canvas
    path = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(path))
    for i, line in enumerate(open(SAMPLE_PATH).read().split("\n")[:60]):
        pdf.drawString(20, 800 - 12 * i, line[:110])
    pdf.showPage()
    for _ in range(3):        # image-only pages: nothing to extract
        pdf.rect(50, 50, 400, 600, fill=1)
        pdf.showPage()
    pdf.save()
    client = FakeClient(copy.deepcopy(SAMPLE))
    with pytest.raises(ValueError, match="scanned"):
        triage(str(path), LLM(client))
    assert client.calls == []


# ----------------------------------------------------------------- report

def test_unsupported_memo_says_what_it_is_and_what_to_do():
    client = FakeClient({}, doc_type="other")
    result = triage(SAMPLE_PATH, LLM(client))
    result.classification["described_as"] = "independent contractor agreement"
    text = memo(result)
    assert "Detected: independent contractor agreement" in text
    assert "SaaS terms or master service agreement" in text and "## Next step" in text
    assert "rework" not in text


def test_unsupported_memo_without_a_label_still_renders():
    result = triage(SAMPLE_PATH, LLM(FakeClient({}, doc_type="other")))
    assert "Detected: document of a type this tool does not review" in memo(result)


def test_pdf_reader_warnings_are_silenced():
    import logging
    assert logging.getLogger("pypdf").getEffectiveLevel() >= logging.ERROR


def test_second_reader_uses_the_reviewers_status_definitions():
    client = FakeClient({})
    f = {"sla": finding("sla", "concern", "makes no commitment regarding availability",
                        verification="verified")}
    verify.judge_support(LLM(client), CHECKLIST, f)
    system = client.calls[0]["system"]
    assert "does not clearly meet ok_when" in system and "ok is supported only when" in system


def test_competent_court_is_not_an_exclusivity_keyword():
    item = next(i for i in CHECKLIST["items"] if i["id"] == "exclusivity")
    doc = Document("t", [Page(1, "The courts of competent jurisdiction decide any dispute.")])
    f = {"exclusivity": finding("exclusivity", "missing")}
    assert verify.probe_absence({"items": [item]}, f, doc) == {}


# ------------------------------------------------------------------- cost

def test_agent_loop_caches_the_whole_conversation():
    client = FakeClient(copy.deepcopy(SAMPLE))
    triage(SAMPLE_PATH, LLM(client))
    loop_calls = [c for c in client.calls if len(c["tools"]) > 1]
    assert loop_calls and all(c["cache_control"] == {"type": "ephemeral"} for c in loop_calls)


def test_effort_is_sent_only_when_configured(monkeypatch):
    from triage import config
    client = FakeClient({}, doc_type="other")
    triage(SAMPLE_PATH, LLM(client))
    assert "output_config" not in client.calls[0]
    monkeypatch.setattr(config, "EFFORT", "medium")
    client = FakeClient({}, doc_type="other")
    triage(SAMPLE_PATH, LLM(client))
    assert client.calls[0]["output_config"] == {"effort": "medium"}


# ------------------------------------------------------------- checklists

@pytest.mark.parametrize("doc_type", sorted(agent.available_checklists()))
def test_every_checklist_item_is_complete(doc_type):
    from triage.decide import EFFECT
    items = agent.available_checklists()[doc_type]["items"]
    assert len({i["id"] for i in items}) == len(items)
    for item in items:
        for key in ["id", "title", "question", "ok_when", "concern_when", "keywords"]:
            assert item.get(key), (item.get("id"), key)
        assert item["if_concern"] in EFFECT and item["if_missing"] in EFFECT
        assert isinstance(item["critical"], bool)


def test_contractor_checklist_is_read_from_the_contractors_side():
    checklist = agent.available_checklists()["contractor_agreement"]
    text = agent._checklist_text(checklist, checklist["items"])
    assert "Review for: the contractor" in text
    saas = agent.available_checklists()["saas_terms"]
    assert "Review for: the customer" in agent._checklist_text(saas, saas["items"])
