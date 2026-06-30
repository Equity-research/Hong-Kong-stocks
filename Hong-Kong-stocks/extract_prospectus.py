"""
IPO Prospectus Data Extractor
==============================
Extracts structured JSON from HK IPO prospectus PDFs.

Usage:
    python extract_prospectus.py --pdf path/to/prospectus.pdf --code 03752
    python extract_prospectus.py --dir data/prospectuses/         # batch mode
    python extract_prospectus.py --stock 03752                     # from etnet data (no PDF)

Output: JSON with company_overview, revenue, profit, margin, ipo_size,
        price_range, lot_size, use_of_proceeds, cornerstone_investors, risk_factors
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent

# Try to use the project's parsers
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def extract_from_pdf(pdf_path: Path, stock_code: str = "", company_name: str = "") -> dict:
    """Extract structured data from a PDF prospectus."""
    import pdfplumber

    result = {
        "company_overview": "",
        "revenue": [],
        "profit": [],
        "margin": {},
        "ipo_size": "",
        "price_range": "",
        "lot_size": "",
        "use_of_proceeds": [],
        "cornerstone_investors": [],
        "risk_factors": [],
        "_meta": {
            "stock_code": stock_code,
            "company_name": company_name,
            "source": str(pdf_path.name),
            "extracted_at": datetime.now().isoformat(),
            "extraction_method": "pdfplumber + regex",
        }
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"

            result["company_overview"] = _extract_company_overview(full_text)
            result["revenue"] = _extract_financial_table(full_text, ["收入", "收益", "营收", "Revenue", "營業收入"])
            result["profit"] = _extract_financial_table(full_text, ["净利润", "淨利潤", "纯利", "純利", "Net Profit", "淨利", "净利"])
            result["margin"] = _extract_margins(full_text)
            result["ipo_size"] = _extract_ipo_size(full_text)
            result["price_range"] = _extract_price_range(full_text)
            result["lot_size"] = _extract_lot_size(full_text)
            result["use_of_proceeds"] = _extract_use_of_proceeds(full_text)
            result["cornerstone_investors"] = _extract_cornerstone_investors(full_text)
            result["risk_factors"] = _extract_risk_factors(full_text)

    except Exception as e:
        result["_meta"]["error"] = str(e)

    return result


def extract_from_etnet(stock_code: str) -> dict:
    """Fill available fields from etnet online data when no PDF."""
    from hk_ipo_analyzer.config import load_config, project_path
    from hk_ipo_analyzer.ipo_fetcher.http_client import PoliteHttpClient
    from hk_ipo_analyzer.ipo_fetcher.etnet_fetcher import EtnetFetcher
    from hk_ipo_analyzer.models import IPORecord

    config = load_config(str(PROJECT_ROOT / "config" / "config.yaml"))
    client = PoliteHttpClient(config["http"])
    etnet = EtnetFetcher(client)

    record = IPORecord(stock_code.zfill(5), "")
    etnet.enrich(record)

    result = {
        "company_overview": str(record.value("business_description") or ""),
        "revenue": [],
        "profit": [],
        "margin": {},
        "ipo_size": _fmt_money(record.value("offer_size_hkd")),
        "price_range": str(record.value("offer_price_range") or ""),
        "lot_size": str(record.value("board_lot") or "") + " shares" if record.value("board_lot") else "",
        "use_of_proceeds": [],
        "cornerstone_investors": record.value("cornerstone_investors") or [],
        "risk_factors": record.risk_tags,
        "_meta": {
            "stock_code": stock_code,
            "company_name": record.company_name,
            "source": "etnet online",
            "extracted_at": datetime.now().isoformat(),
            "extraction_method": "etnet HTML parsing (no PDF)",
            "note": "Financial data (revenue/profit/margins) requires prospectus PDF. Run with --pdf."
        }
    }
    return result


def _extract_company_overview(text: str) -> str:
    patterns = [
        r"(?:概覽|概览|Overview|公司簡介|公司简介|業務|业务).{0,100}?\n(.{20,500}?)(?:\n\n|\n[A-Z])",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.DOTALL | re.I)
        if m:
            overview = m.group(1).strip()
            if 20 < len(overview) < 1000:
                return overview
    return ""


def _extract_financial_table(text: str, keywords: list[str]) -> list[dict]:
    """Try to find financial data rows for given keywords."""
    from hk_ipo_analyzer.ipo_parser.financial_parser import _parse_hkd_amount

    result = []
    # Look for year-columnar financial data
    years = re.findall(r"(?:截至|For the year|FY|20\d{2})\s*(?:12月31日|3月31日|年度)?\s*(20\d{2})", text, re.I)
    if not years:
        years = re.findall(r"20\d{2}\s*年?", text)
        years = list(set(years))[:3]

    for kw in keywords:
        # Find the line containing this keyword and nearby amounts
        idx = text.lower().find(kw.lower())
        if idx < 0:
            continue
        context = text[max(0, idx - 100):idx + 500]
        amounts = _parse_hkd_amount(context) if '_parse_hkd_amount' in dir() else None

        nums = re.findall(r"(?:HK\$|港幣|港元|RMB|人民幣)?\s*([\d.,]+)\s*([億亿万萬千]?)", context)
        values = []
        for num_str, unit in nums[:3]:
            try:
                val = float(num_str.replace(",", ""))
                mult = {"億": 1e8, "亿": 1e8, "萬": 1e4, "万": 1e4, "千": 1e3}
                val *= mult.get(unit, 1)
                values.append(val)
            except ValueError:
                pass

        if values:
            entry = {"label": kw}
            for i, yr in enumerate(years[:len(values)]):
                entry[f"FY{yr}"] = values[i]
            result.append(entry)

    return result


def _extract_margins(text: str) -> dict:
    margins = {}
    patterns = {
        "gross_margin": r"(?:毛利[率]?|Gross\s*Profit\s*Margin)[^%\d\n]{0,60}([\d.]+)\s*%",
        "net_margin": r"(?:淨利[率]?|净利[率]?|純利[率]?|Net\s*(?:Profit\s*)?Margin)[^%\d\n]{0,60}([\d.]+)\s*%",
        "operating_margin": r"(?:經營利潤率|经营利润率|Operating\s*Margin)[^%\d\n]{0,60}([\d.]+)\s*%",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.I)
        if m:
            margins[key] = float(m.group(1))
    return margins


def _extract_ipo_size(text: str) -> str:
    m = re.search(r"(?:發售規模|发售规模|集資(?:額|金额)|募集資金|Offer\s*Size|全球發售).{0,50}HK\$?\s*([\d.,]+\s*[億亿万萬千]?)", text, re.I)
    return m.group(1).strip() if m else ""


def _extract_price_range(text: str) -> str:
    m = re.search(r"(?:發售價|发售價|招股價|招股价|Offer\s*Price).{0,30}(HK\$[\d.]+\s*[-–至]\s*HK\$[\d.]+)", text, re.I)
    return m.group(1) if m else ""


def _extract_lot_size(text: str) -> str:
    m = re.search(r"(?:每手|一手|Board\s*Lot).{0,20}(\d[\d,]*)\s*股", text, re.I)
    return f"{m.group(1)} shares" if m else ""


def _extract_use_of_proceeds(text: str) -> list[dict]:
    """Extract use of proceeds section with percentages."""
    result = []
    section_match = re.search(r"(?:所得款項用途|募集資金用途|Use\s*of\s*Proceeds|發售所得)", text, re.I)
    if not section_match:
        return result
    section = text[section_match.start():section_match.start() + 3000]

    items = re.findall(
        r"(?:[约約]?\s*)?([\d.]+)\s*%[^%\n]{0,100}((?:用於|用于|用作|作為|作为|用作|投入|擴張|扩张|研發|研发|償還|偿还|營運|营运|一般|市場|市场|銷售|销售)[^\n]{5,100})",
        section,
    )
    for pct, desc in items[:8]:
        result.append({"percentage": float(pct), "description": desc.strip()})
    return result


def _extract_cornerstone_investors(text: str) -> list[dict]:
    """Extract cornerstone investor details."""
    result = []
    section_match = re.search(r"(?:基石投資者|基石投资者|Cornerstone\s*Investor)", text, re.I)
    if not section_match:
        return result
    section = text[section_match.start():section_match.start() + 10000]

    # Try to find structured cornerstone entries
    entries = re.findall(
        r"([A-Z][A-Za-z&.,'()\- ]{6,80}(?:Limited|Ltd\.?|Inc\.?|Capital|Holdings|Group|Investment|Fund|Asset|Management|Partners?|Securities|International|Asia|China|Financial|Bank|Trust|Venture|Private|Equity))",
        section,
    )
    if not entries:
        entries = re.findall(
            r"([\u4e00-\u9fff（）()]{3,18}(?:集團|控股|有限|投资|科技|基金|资产|资本|证券|医疗|医药|生物|电子|半导体|机器人|能源|材料|化工|消费|零售|地产|金融|保险|银行|国际|香港|中国|企業|公司))",
            section,
        )

    seen = set()
    for name in entries:
        clean = name.strip().rstrip(".,;，。；")
        if clean and clean not in seen and 3 < len(clean) < 80:
            seen.add(clean)
            result.append({"name": clean})

    return result


def _extract_risk_factors(text: str) -> list[str]:
    """Extract key risk factors from the prospectus."""
    risks = []
    section_match = re.search(r"(?:風險因素|风险因素|Risk\s*Factors)", text, re.I)
    if not section_match:
        return risks
    section = text[section_match.start():section_match.start() + 8000]

    # Find bullet points or numbered items in the risk section
    items = re.findall(r"(?:[•\-\*]\s*|\d+\.\s*)(.{15,200}?)(?=\n\s*(?:[•\-\*]|\d+\.)|$)", section)
    for item in items[:10]:
        clean = item.strip()
        if len(clean) > 10:
            risks.append(clean)

    return risks


def _fmt_money(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        if value >= 1e8:
            return f"HK${value/1e8:.2f}亿"
        return f"HK${value:,.0f}"
    return str(value)


def main():
    parser = argparse.ArgumentParser(description="IPO Prospectus Data Extractor")
    parser.add_argument("--pdf", help="Path to prospectus PDF")
    parser.add_argument("--dir", help="Directory containing prospectus PDFs")
    parser.add_argument("--stock", help="Stock code to fetch from etnet (online, no PDF needed)")
    parser.add_argument("--code", default="", help="Stock code for metadata")
    parser.add_argument("--name", default="", help="Company name for metadata")
    parser.add_argument("-o", "--output", help="Output JSON file path")
    parser.add_argument("--pretty", action="store_true", default=True, help="Pretty-print JSON")

    args = parser.parse_args()

    if args.pdf:
        result = extract_from_pdf(Path(args.pdf), args.code or "", args.name or "")
    elif args.dir:
        results = []
        for pdf_file in Path(args.dir).glob("*.pdf"):
            code = re.search(r"(\d{5})", pdf_file.name)
            result = extract_from_pdf(pdf_file, code.group(1) if code else "")
            results.append(result)
        result = results if len(results) > 1 else (results[0] if results else {})
    elif args.stock:
        result = extract_from_etnet(args.stock)
    else:
        parser.print_help()
        sys.exit(1)

    output = json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Saved to: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
