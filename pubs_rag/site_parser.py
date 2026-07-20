"""Parse the two publication index pages from the ciphex-website source.

ciphex.io is a client-rendered Vite SPA for most routes (no content API —
see the ecosystem map), but `/ecosystem-publications` and
`/ecosystem-updates` are each backed by their own static, server-rendered
HTML entry file in the ciphex-website repo (`src/ecosystem-publications.html`,
`src/ecosystem-updates.html`, confirmed against Cipherion-Market-Research/
ciphex-website@main). Each publication is a `.pdf-preview-card` button
carrying `data-slug` / `data-title` / `data-date` / `data-pdf` attributes
baked in at build time — so a plain GitHub raw-content fetch + BeautifulSoup
parse gets the same metadata a headless browser would get from the live
site, with no JS rendering required.
"""
from bs4 import BeautifulSoup


def parse_publication_index(html: str, listed_on: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for card in soup.select(".pdf-preview-card[data-slug]"):
        entries.append(
            {
                "slug": card["data-slug"],
                "title": card["data-title"],
                "date": card["data-date"],
                "pdf_path": card["data-pdf"],
                "listed_on": listed_on,
            }
        )
    return entries
