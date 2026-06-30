from __future__ import annotations

from pathlib import Path

import fitz


def extract_pdf_text(path: Path, max_pages: int | None = None) -> str:
    chunks: list[str] = []
    with fitz.open(path) as document:
        count = len(document) if max_pages is None else min(len(document), max_pages)
        for index in range(count):
            chunks.append(document[index].get_text("text"))
    return "\n".join(chunks)

