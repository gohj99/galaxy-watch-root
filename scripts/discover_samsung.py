#!/usr/bin/env python3
"""Read Samsung Open Source search results without accepting download terms."""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


class SearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_row = False
        self.in_cell = False
        self.row: list[str] = []
        self.rows: list[list[str]] = []
        self.links: list[str] = []
        self._row_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "tr":
            self.in_row = True
            self.row = []
            self._row_links = []
        elif self.in_row and tag == "td":
            self.in_cell = True
        elif self.in_row and tag == "a":
            href = attrs_dict.get("href") or ""
            if "showSrcDownPop" in href:
                self._row_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.row:
                self.rows.append(self.row + ["\n".join(self._row_links)])

    def handle_data(self, data: str) -> None:
        if self.in_row and self.in_cell:
            value = " ".join(data.split())
            if value:
                self.row.append(value)


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "galaxy-watch-root source checker"})
    try:
        with urlopen(request, timeout=45) as response:
            return response.read()
    except Exception as exc:  # pragma: no cover - network-specific error text
        raise SystemExit(
            f"Samsung Open Source request failed: {exc}. "
            "Cloudflare or a temporary block is common; do not publish a release from incomplete metadata."
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="https://opensource.samsung.com/uploadSearch")
    args = parser.parse_args()

    url = f"{args.base_url}?searchValue={quote(args.query)}"
    body = fetch(url).decode("utf-8", "replace")
    if "Just a moment" in body or "cf-chl-" in body:
        raise SystemExit("Samsung Open Source returned a Cloudflare challenge; metadata was not trusted.")
    parser_html = SearchParser()
    parser_html.feed(body)
    candidates = []
    for row in parser_html.rows:
        text = " ".join(row[:-1])
        match = re.search(r"showSrcDownPop\(['\"](\d+)", row[-1])
        if match and args.model.upper() in text.upper():
            candidates.append({
                "model": args.model,
                "upload_id": match.group(1),
                "row": row[:-1],
                "source_page": url,
            })
    if not candidates:
        raise SystemExit(f"No Samsung source result contains model {args.model}.")
    result = {
        "query": args.query,
        "model": args.model,
        "source_page": url,
        "result_count": len(parser_html.rows),
        "candidates": candidates,
        "selected": candidates[0],
        "download": {
            "requires_user_accepted_terms": True,
            "note": "This script only discovers metadata. It never submits Samsung's legal agreement."
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
