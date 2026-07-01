"""调用项目统一解析器提取港股招股书证据。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from hk_ipo_analyzer.config import load_config  # noqa: E402
from hk_ipo_analyzer.ipo_fetcher.etnet_fetcher import EtnetFetcher  # noqa: E402
from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient  # noqa: E402
from hk_ipo_analyzer.ipo_parser.cornerstone_parser import CornerstoneParser  # noqa: E402
from hk_ipo_analyzer.ipo_parser.financial_parser import FinancialParser  # noqa: E402
from hk_ipo_analyzer.ipo_parser.offer_structure_parser import OfferStructureParser  # noqa: E402
from hk_ipo_analyzer.ipo_parser.pdf_text import extract_pdf_text  # noqa: E402
from hk_ipo_analyzer.ipo_parser.risk_parser import RiskParser  # noqa: E402
from hk_ipo_analyzer.ipo_parser.sponsor_parser import SponsorParser  # noqa: E402
from hk_ipo_analyzer.models import IPORecord  # noqa: E402


def extract_from_pdf(pdf_path: Path, stock_code: str = "", company_name: str = "") -> dict:
    record = IPORecord(stock_code.zfill(5) if stock_code else "00000", company_name or pdf_path.stem)
    source_url = pdf_path.resolve().as_uri()
    text = extract_pdf_text(pdf_path)
    financial = FinancialParser()
    financial.parse(text, record, source_url)
    financial.parse_from_pdf(pdf_path, record, source_url)
    CornerstoneParser().parse(text, record, source_url)
    OfferStructureParser().parse(text, record, source_url)
    SponsorParser().parse(text, record, source_url)
    RiskParser().parse(text, record, source_url)
    record.fill_expected_nulls()
    return record.to_dict()


def extract_from_etnet(stock_code: str) -> dict:
    config = load_config(str(PROJECT_ROOT / "config" / "config.yaml"))
    client = PoliteHttpClient(config["http"])
    record = IPORecord(stock_code.zfill(5), "")
    EtnetFetcher(client).enrich(record)
    record.fill_expected_nulls()
    return record.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="IPO prospectus evidence extractor")
    parser.add_argument("--pdf")
    parser.add_argument("--dir")
    parser.add_argument("--stock")
    parser.add_argument("--code", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()

    if args.pdf:
        result = extract_from_pdf(Path(args.pdf), args.code, args.name)
    elif args.dir:
        result = []
        for pdf_file in sorted(Path(args.dir).glob("*.pdf")):
            match = re.search(r"(\d{5})", pdf_file.name)
            result.append(extract_from_pdf(pdf_file, match.group(1) if match else ""))
    elif args.stock:
        result = extract_from_etnet(args.stock)
    else:
        parser.error("one of --pdf, --dir, or --stock is required")

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        print(f"Saved to: {target}")
    else:
        print(output)


if __name__ == "__main__":
    main()
