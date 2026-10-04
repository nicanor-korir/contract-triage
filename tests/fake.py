"""A scripted stand-in for the Anthropic client, so the whole pipeline runs without a key."""
import re
from types import SimpleNamespace as NS


def _tool_use(name, payload, n):
    return NS(type="tool_use", id=f"tu_{n}", name=name, input=payload)


class FakeClient:
    """answers maps check_id to a list of record_finding payloads, one per attempt."""

    def __init__(self, answers, doc_type="saas_terms", judge_rejects=()):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.doc_type = doc_type
        self.judge_rejects = set(judge_rejects)
        self.calls = []
        self.messages = self
        self._n = 0

    def create(self, **kwargs):
        self.calls.append(kwargs)
        self._n += 1
        usage = NS(input_tokens=1000, output_tokens=200,
                   cache_creation_input_tokens=0, cache_read_input_tokens=0)
        choice = kwargs.get("tool_choice", {}).get("name")
        if choice == "classify":
            content = [_tool_use("classify", {"doc_type": self.doc_type, "vendor": "Nimbusdesk",
                                              "summary": "Hosted help desk terms."}, self._n)]
        elif choice == "judge":
            ids = re.findall(r"check_id: (\w+)", kwargs["messages"][0]["content"])
            content = [_tool_use("judge", {"verdicts": [
                {"check_id": i, "supported": i not in self.judge_rejects, "reason": "scripted"}
                for i in ids]}, self._n)]
            self.judge_rejects = set()  # reject only on the first pass
        else:
            task = kwargs["messages"][0]["content"][1]["text"]
            ids = re.findall(r"^- (\w+): ", task.split("Checklist:")[1].split("Your earlier")[0], re.M)
            content = []
            for k, check_id in enumerate(ids):
                queue = self.answers.get(check_id)
                if queue:
                    payload = queue.pop(0) if len(queue) > 1 else queue[0]
                    content.append(_tool_use("record_finding", {"check_id": check_id, **payload},
                                             f"{self._n}_{k}"))
            content.append(_tool_use("finish", {}, f"{self._n}_f"))
        return NS(content=content, usage=usage, stop_reason="tool_use")


def ok(quote, page=1, explanation="Fine."):
    return {"status": "ok", "quote": quote, "page": page, "doc_id": "main", "explanation": explanation}


def concern(quote, page=1, explanation="Unfavourable."):
    return {"status": "concern", "quote": quote, "page": page, "doc_id": "main", "explanation": explanation}


MISSING = {"status": "missing", "quote": "", "page": 0, "doc_id": "main",
           "explanation": "Not addressed."}

# Correct answers for examples/sample_terms.txt
SAMPLE = {
    "liability_cap": [concern("limited to the fees paid by Customer in the three months before the event", 2)],
    "customer_indemnity": [ok("Customer will indemnify Nimbusdesk against third party claims arising from Customer Data", 2)],
    "data_ownership": [ok("As between the parties, Customer owns all Customer Data.")],
    "data_training": [concern("to develop, train and improve its products and machine learning models unless Customer opts out")],
    "dpa": [ok("the Data Processing Addendum at https://nimbusdesk.example/legal/dpa applies and is incorporated")],
    "breach_notice": [concern("it will notify Customer within ten business days of confirming the incident")],
    "data_exit": [ok("Customer may export Customer Data for thirty days, after which Nimbusdesk will delete Customer Data")],
    "termination": [ok("Either party may terminate this agreement if the other party materially breaches it")],
    "auto_renewal": [concern("notice of non-renewal at least ninety days before the end of the current term")],
    "price_changes": [ok("Nimbusdesk may increase the fees for any renewal term by giving at least thirty days of written notice")],
    "unilateral_changes": [concern("Nimbusdesk may modify these Terms at any time by posting a revised version on its website")],
    "sla": [concern("makes no commitment regarding availability", 2)],
    "ip_assignment": [ok("Nothing in these Terms transfers ownership of Customer's intellectual property to Nimbusdesk", 2)],
    "exclusivity": [MISSING],
    "governing_law": [ok("This agreement is governed by the laws of Ireland, and the courts of Dublin have exclusive jurisdiction", 2)],
}
