"""Turn a PDF, HTML page, text file or URL into numbered pages of text."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

CHUNK_CHARS = 3000
URL_RE = re.compile(r"https?://[^\s)>\]\"'<]+")
_TRANSLATE = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u00a0": " ", "\u00ad": "",
})


@dataclass
class Page:
    number: int
    text: str


@dataclass
class Document:
    source: str
    pages: list[Page]
    links: set[str] = field(default_factory=set)

    @property
    def chars(self) -> int:
        return sum(len(p.text) for p in self.pages)

    def render(self, max_chars: int | None = None) -> str:
        text = "\n\n".join(f"[PAGE {p.number}]\n{p.text}" for p in self.pages)
        return text if max_chars is None else text[:max_chars]

    def urls(self) -> set[str]:
        """Every URL the document itself mentions. Only these may be fetched."""
        found = set(self.links)
        for page in self.pages:
            found.update(u.rstrip(".,;") for u in URL_RE.findall(page.text))
        return found


def squash(text: str) -> str:
    """Comparison form: same characters, minus whitespace, hyphens and case.

    PDF extraction breaks lines and hyphenates words, so a quote that is
    word for word correct can still differ in spacing. Squashing both sides
    keeps the match strict on wording and tolerant of layout.
    """
    return re.sub(r"[\s\-]+", "", text.translate(_TRANSLATE)).casefold()


def _chunk(text: str) -> list[Page]:
    """Split unpaged text into pseudo pages on paragraph boundaries."""
    pages, current = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) > CHUNK_CHARS:
            pages.append(current)
            current = ""
        current = f"{current}\n\n{para}" if current else para
    if current:
        pages.append(current)
    return [Page(i + 1, t) for i, t in enumerate(pages)]


def _from_pdf(data: bytes, source: str) -> Document:
    reader = PdfReader(io.BytesIO(data))
    pages = [Page(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]
    return Document(source, [p for p in pages if p.text])


def _from_html(html: str, source: str, base_url: str | None = None) -> Document:
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]) if base_url else a["href"]
        if href.startswith("http"):
            links.add(href.split("#")[0])
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    for block in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "tr", "br"]):
        block.append("\n\n")
    text = re.sub(r"[ \t]+", " ", soup.get_text(" "))
    return Document(source, _chunk(text), links)


def _from_url(url: str) -> Document:
    response = httpx.get(url, follow_redirects=True, timeout=30,
                         headers={"User-Agent": "contract-triage/0.1"})
    response.raise_for_status()
    if "pdf" in response.headers.get("content-type", "") or url.lower().endswith(".pdf"):
        return _from_pdf(response.content, url)
    return _from_html(response.text, url, base_url=str(response.url))


def load(source: str) -> Document:
    """Load a contract from a file path or an http(s) URL."""
    if source.startswith(("http://", "https://")):
        doc = _from_url(source)
    else:
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            doc = _from_pdf(path.read_bytes(), source)
        elif suffix in {".html", ".htm"}:
            doc = _from_html(path.read_text(encoding="utf-8", errors="replace"), source)
        else:
            doc = Document(source, _chunk(path.read_text(encoding="utf-8", errors="replace")))
    if not doc.pages:
        raise ValueError(f"No text could be extracted from {source}. Scanned PDFs need OCR first.")
    return doc
