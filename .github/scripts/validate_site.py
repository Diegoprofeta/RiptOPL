#!/usr/bin/env python3
"""Validate local site links, fragments and duplicate IDs without network calls."""
import argparse
from pathlib import Path
from urllib.parse import unquote, urlsplit
from bs4 import BeautifulSoup


def validate(root):
    pages = {p.resolve(): BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser") for p in root.glob("*.html")}
    errors = []
    count = 0
    for path, soup in pages.items():
        ids = [tag["id"] for tag in soup.select("[id]")]
        if len(ids) != len(set(ids)):
            errors.append(f"{path.name}: duplicate IDs")
        for tag in soup.select("[href], [src]"):
            value = tag.get("href", tag.get("src", ""))
            url = urlsplit(value)
            if url.scheme or url.netloc or value.startswith("/"):
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if target.is_dir():
                target /= "index.html"
            count += 1
            if not target.exists():
                errors.append(f"{path.name}: missing {value}")
            elif url.fragment and target in pages:
                anchor = unquote(url.fragment)
                if not pages[target].find(id=anchor) and not pages[target].find(attrs={"name": anchor}):
                    errors.append(f"{path.name}: missing anchor {value}")
    if errors:
        raise ValueError("\n".join(errors))
    print(f"Verified {len(pages)} HTML pages, {count} local links/resources and unique IDs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    validate(parser.parse_args().site.resolve())
