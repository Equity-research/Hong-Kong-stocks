from __future__ import annotations

import hashlib
import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class ProspectusDownloader:
    def __init__(self, client, destination: Path):
        self.client = client
        self.destination = destination

    def download(self, stock_code: str, url: str) -> Path | None:
        self.destination.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(url.encode()).hexdigest()[:10]
        target = self.destination / f"{stock_code}_{digest}.pdf"
        if target.exists() and target.stat().st_size > 0:
            return target
        try:
            response = self.client.get(url)
            content_type = response.headers.get("Content-Type", "").lower()
            if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
                LOGGER.warning("链接不是 PDF，跳过：%s", url)
                return None
            target.write_bytes(response.content)
            return target
        except Exception:
            LOGGER.exception("下载招股书失败：%s", url)
            return None

