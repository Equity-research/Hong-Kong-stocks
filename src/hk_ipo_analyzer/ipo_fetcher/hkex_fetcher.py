from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from hk_ipo_analyzer.models import IPORecord, utc_now_iso

LOGGER = logging.getLogger(__name__)
CODE_RE = re.compile(r"(?<!\d)(\d{4,5})(?!\d)")


class HKEXFetcher:
    def __init__(self, client, sources: dict):
        self.client = client
        self.sources = sources

    def fetch_current_listings(self) -> list[IPORecord]:
        urls = [("HKEXnews 主板新上市资料", self.sources["hkex_main_board"])]
        if self.sources.get("enable_gem", True):
            urls.append(("HKEXnews GEM 新上市资料", self.sources["hkex_gem"]))
        merged: dict[str, IPORecord] = {}
        for source_name, url in urls:
            try:
                response = self.client.get(url)
                for record in self.parse_listing_html(response.text, url, source_name):
                    existing = merged.get(record.stock_code)
                    if existing:
                        existing.documents.extend(
                            doc for doc in record.documents if doc not in existing.documents
                        )
                    else:
                        merged[record.stock_code] = record
            except Exception:
                LOGGER.exception("获取 HKEX 列表失败：%s", url)
        return list(merged.values())

    def resolve_pdf_links(self, document: dict) -> list[dict]:
        """HKEX 的“下载”有时先进入文档清单页；只解析公开 PDF 链接。"""
        url = document["url"]
        if url.lower().split("?")[0].endswith(".pdf"):
            return [document]
        try:
            response = self.client.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
            resolved = []
            for anchor in soup.select("a[href]"):
                href = urljoin(url, str(anchor.get("href")))
                if href.lower().split("?")[0].endswith(".pdf"):
                    item = dict(document)
                    item["url"] = href
                    item["title"] = anchor.get_text(" ", strip=True) or document.get("title", "")
                    resolved.append(item)
            return resolved
        except Exception:
            LOGGER.exception("解析 HKEX 文档清单失败：%s", url)
            return []

    @staticmethod
    def parse_listing_html(html: str, source_url: str, source_name: str) -> list[IPORecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[IPORecord] = []
        fetched_at = utc_now_iso()
        for row in soup.select("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            code_match = CODE_RE.search(cells[0].get_text(" ", strip=True))
            if not code_match:
                continue
            code = code_match.group(1).zfill(4)
            name = cells[1].get_text(" ", strip=True)
            if not name:
                continue
            record = IPORecord(stock_code=code, company_name=name)
            record.set_field("stock_code", code, source_url, source_name, fetched_at)
            record.set_field("company_name", name, source_url, source_name, fetched_at)
            for link in row.select("a[href]"):
                HKEXFetcher._append_document(record, link, source_url, source_name, fetched_at)
            records.append(record)
        return records

    @staticmethod
    def _append_document(
        record: IPORecord,
        link: Tag,
        page_url: str,
        source_name: str,
        fetched_at: str,
    ) -> None:
        href = urljoin(page_url, str(link.get("href")))
        text = link.get_text(" ", strip=True)
        context = " ".join(link.parent.get_text(" ", strip=True).split()) if link.parent else text
        label = f"{text} {context}".lower()
        if "配發" in label or "配发" in label or "allotment" in label:
            document_type = "allotment_result"
        elif "招股" in label or "prospect" in label:
            document_type = "prospectus"
        elif "公告" in label or "announcement" in label:
            document_type = "listing_announcement"
        elif href.lower().endswith(".pdf"):
            document_type = "document"
        else:
            return
        record.documents.append(
            {
                "document_type": document_type,
                "title": text or context,
                "url": href,
                "source_name": source_name,
                "fetched_at": fetched_at,
            }
        )
