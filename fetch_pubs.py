#!/usr/bin/env python3
"""
fetch_pubs.py
─────────────
Searches PubMed for publications by Mallory Feldman at UNC or OSU,
exports a combined papers.bib to publications/papers.bib (relative to
this script's location), AND copies it to ~/Desktop/papers.bib.

Sends a plain-text email via Gmail SMTP when new papers are found.

Usage
-----
  python fetch_pubs.py

Required env vars (set in your shell profile or GitHub Actions secrets):
  GMAIL_USER   – your Gmail address (the sender)
  GMAIL_PASS   – a Gmail App Password (not your regular password)
                 https://myaccount.google.com/apppasswords
  NOTIFY_EMAIL – the address that receives the alert (can be same as GMAIL_USER)

Dependencies
------------
  pip install biopython
"""

import os
import re
import sys
import shutil
import smtplib
import textwrap
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from Bio import Entrez

# ── Config ────────────────────────────────────────────────────────────────────
Entrez.email = os.environ.get("GMAIL_USER", "malloryjeanfeldman@email.com")

SEARCH_QUERY = (
    '(Feldman MJ[Author]) AND '
    '("University of North Carolina"[Affiliation] OR '
    '"Ohio State"[Affiliation] OR "The Ohio State"[Affiliation] OR "OSU"[Affiliation])'
)
MAX_RESULTS = 200

# Paths
SCRIPT_DIR   = Path(__file__).parent.resolve()
BIB_OUT      = SCRIPT_DIR / "publications" / "papers.bib"
DESKTOP_OUT  = Path.home() / "Desktop" / "bib_files"
SEEN_FILE    = SCRIPT_DIR / ".seen_pmids"   # tracks previously known PMIDs

# Email
GMAIL_USER   = os.environ.get("GMAIL_USER", "")
GMAIL_PASS   = os.environ.get("GMAIL_PASS", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", GMAIL_USER)


# ── PubMed helpers ────────────────────────────────────────────────────────────
def search_pubmed(query: str, max_results: int = 200) -> list[str]:
    handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
    record = Entrez.read(handle)
    handle.close()
    return list(record["IdList"])


def fetch_records(pmid_list: list[str]):
    if not pmid_list:
        return []
    handle = Entrez.efetch(
        db="pubmed", id=",".join(pmid_list), rettype="medline", retmode="xml"
    )
    records = Entrez.read(handle)
    handle.close()
    return records.get("PubmedArticle", [])


# ── BibTeX builder ────────────────────────────────────────────────────────────
def _safe(text: str) -> str:
    """Escape braces that would break BibTeX."""
    return str(text).replace("\\", "").strip()


def article_to_bib(article) -> tuple[str, str]:
    """Return (pmid, bib_entry_string)."""
    medline = article["MedlineCitation"]
    art     = medline["Article"]
    pmid    = str(medline["PMID"])

    title   = _safe(art.get("ArticleTitle", "Untitled"))
    journal = _safe(art["Journal"]["Title"])

    pub_date = art["Journal"]["JournalIssue"].get("PubDate", {})
    year     = str(pub_date.get("Year", pub_date.get("MedlineDate", "")[:4]))

    volume  = _safe(art["Journal"]["JournalIssue"].get("Volume", ""))
    issue   = _safe(art["Journal"]["JournalIssue"].get("Issue", ""))

    # Page range
    pages = ""
    if "Pagination" in art:
        pages = _safe(art["Pagination"].get("MedlinePgn", ""))

    # Authors
    authors = []
    for a in art.get("AuthorList", []):
        last = a.get("LastName", "")
        fore = a.get("ForeName", a.get("Initials", ""))
        if last:
            authors.append(f"{fore} {last}".strip())
    author_str = " and ".join(authors)

    # DOI
    doi = ""
    for loc in art.get("ELocationID", []):
        if loc.attributes.get("EIdType") == "doi":
            doi = str(loc)
            break

    # Abstract
    abstract_parts = []
    if "Abstract" in art:
        for part in art["Abstract"].get("AbstractText", []):
            label = part.attributes.get("Label", "") if hasattr(part, "attributes") else ""
            text  = str(part).strip()
            abstract_parts.append(f"{label + ': ' if label else ''}{text}")
    abstract = " ".join(abstract_parts)

    # BibTeX key:  FirstAuthorLastname + Year + first word of title
    first_last  = re.sub(r"\W+", "", authors[0].split()[-1]) if authors else "Unknown"
    title_word  = re.sub(r"\W+", "", title.split()[0]) if title else "Paper"
    key         = f"{first_last}{year}{title_word}"

    lines = [f"@Article{{{key},"]
    lines.append(f"  author   = {{{author_str}}},")
    lines.append(f"  title    = {{{title}}},")
    lines.append(f"  journal  = {{{journal}}},")
    lines.append(f"  year     = {{{year}}},")
    if volume:  lines.append(f"  volume   = {{{volume}}},")
    if issue:   lines.append(f"  issue    = {{{issue}}},")
    if pages:   lines.append(f"  pages    = {{{pages}}},")
    if doi:     lines.append(f"  doi      = {{{doi}}},")
    if abstract:
        wrapped = textwrap.fill(abstract, width=80,
                                subsequent_indent="              ")
        lines.append(f"  abstract = {{{wrapped}}},")
    lines.append("}")

    return pmid, "\n".join(lines)


# ── Seen-PMID tracking ────────────────────────────────────────────────────────
def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        return set(SEEN_FILE.read_text().split())
    return set()


def save_seen(pmids: set[str]) -> None:
    SEEN_FILE.write_text("\n".join(sorted(pmids)))


# ── Email ─────────────────────────────────────────────────────────────────────
def send_email(new_entries: list[tuple[str, str]]) -> None:
    if not (GMAIL_USER and GMAIL_PASS and NOTIFY_EMAIL):
        print("⚠️  Email env vars not set – skipping notification.")
        return

    titles = "\n".join(
        f"  • {_extract_title(bib)}" for _, bib in new_entries
    )
    body = (
        f"Hi Mallory,\n\n"
        f"{len(new_entries)} new publication(s) were found on PubMed "
        f"and added to papers.bib on {datetime.today().strftime('%B %d, %Y')}.\n\n"
        f"{titles}\n\n"
        f"Please check the file and add any custom keywords before re-publishing your site.\n\n"
        f"— Your website bot 🤖"
    )

    msg = MIMEText(body)
    msg["Subject"] = f"📄 {len(new_entries)} new pub(s) added to your website"
    msg["From"]    = GMAIL_USER
    msg["To"]      = NOTIFY_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_PASS)
        smtp.send_message(msg)
    print(f"✉️  Notification sent to {NOTIFY_EMAIL}")


def _extract_title(bib: str) -> str:
    m = re.search(r"title\s*=\s*\{(.+?)\}", bib, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else "(unknown title)"


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"🔍 Searching PubMed …\n   Query: {SEARCH_QUERY}")
    pmids = search_pubmed(SEARCH_QUERY, MAX_RESULTS)
    print(f"   Found {len(pmids)} result(s)")

    if not pmids:
        print("Nothing to do.")
        return

    seen     = load_seen()
    new_pmids = [p for p in pmids if p not in seen]

    print(f"   {len(new_pmids)} new (not previously seen)")

    records   = fetch_records(pmids)
    entries   = [article_to_bib(r) for r in records]          # list of (pmid, bib)
    new_entries = [(p, b) for p, b in entries if p in set(new_pmids)]

    # Write full bib (all found, not just new) so the file stays complete
    bib_text = "\n\n".join(b for _, b in entries)

    BIB_OUT.parent.mkdir(parents=True, exist_ok=True)
    BIB_OUT.write_text(bib_text, encoding="utf-8")
    print(f"✅  Wrote {len(entries)} entries → {BIB_OUT}")

    # Copy to Desktop
    shutil.copy2(BIB_OUT, DESKTOP_OUT)
    print(f"🖥️   Copied → {DESKTOP_OUT}")

    # Update seen list
    save_seen(seen | set(pmids))

    # Email if new papers found
    if new_entries:
        print(f"📬 Sending email about {len(new_entries)} new paper(s) …")
        send_email(new_entries)
    else:
        print("No new papers — no email sent.")


if __name__ == "__main__":
    main()
