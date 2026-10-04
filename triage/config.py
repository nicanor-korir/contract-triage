"""Settings, all overridable through environment variables."""
import os


def _float(name: str):
    value = os.getenv(name)
    return float(value) if value else None


# Model names change, so they live in the environment and not in the code.
MODEL = os.getenv("TRIAGE_MODEL", "claude-sonnet-5-5")
VERIFIER_MODEL = os.getenv("TRIAGE_VERIFIER_MODEL", MODEL)

# Prices in USD per million tokens. Leave unset and the report shows tokens only.
# Take the numbers from the provider's current pricing page.
PRICE_INPUT = _float("TRIAGE_PRICE_INPUT_PER_MTOK")
PRICE_OUTPUT = _float("TRIAGE_PRICE_OUTPUT_PER_MTOK")
CACHE_WRITE_MULTIPLIER = float(os.getenv("TRIAGE_CACHE_WRITE_MULTIPLIER", "1.25"))
CACHE_READ_MULTIPLIER = float(os.getenv("TRIAGE_CACHE_READ_MULTIPLIER", "0.1"))

MAX_STEPS = int(os.getenv("TRIAGE_MAX_STEPS", "25"))          # agent loop turns
MAX_FETCHES = int(os.getenv("TRIAGE_MAX_FETCHES", "3"))       # referenced documents per run
MAX_DOC_CHARS = int(os.getenv("TRIAGE_MAX_DOC_CHARS", "400000"))
MAX_FETCHED_CHARS = int(os.getenv("TRIAGE_MAX_FETCHED_CHARS", "120000"))
MIN_QUOTE_CHARS = 20                                          # shorter quotes prove nothing
UNVERIFIED_LIMIT = 0.25                                       # above this share, escalate
