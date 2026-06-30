from pathlib import Path

from hk_ipo_analyzer.ipo_fetcher.hkex_fetcher import HKEXFetcher


def test_parse_listing_table():
    html = Path("tests/fixtures/hkex_listing.html").read_text(encoding="utf-8")
    records = HKEXFetcher.parse_listing_html(html, "https://example.test/list", "fixture")
    assert len(records) == 1
    assert records[0].stock_code == "01234"
    assert records[0].company_name == "示例科技有限公司 - P"
    types = {document["document_type"] for document in records[0].documents}
    assert types == {"listing_announcement", "prospectus", "allotment_result"}
    assert records[0].fields["company_name"].source_url == "https://example.test/list"

