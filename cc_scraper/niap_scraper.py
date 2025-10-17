
from __future__ import annotations
import asyncio
import os
import json
import time
from typing import Dict, List, Any
from dataclasses import dataclass, asdict

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from .utils import normalize_label, squash_ws, FIELD_ALIASES

TARGET_URL = os.environ.get("NIAP_URL", "https://www.niap-ccevs.org/products")

CANON_FIELDS = [
    "VID",
    "Vendor",
    "Product",
    "CCTL",
    "Certification Date",
    "Status",
    "Conformance Claims",
    "Assurance Maintenance Date",
    "Maintenance Update",
    "Scheme",
]

@dataclass
class Record:
    VID: str | None = None
    Vendor: str | None = None
    Product: str | None = None
    CCTL: str | None = None
    Certification_Date: str | None = None
    Status: str | None = None
    Conformance_Claims: str | None = None
    Assurance_Maintenance_Date: str | None = None
    Maintenance_Update: str | None = None
    Scheme: str | None = None
    Product_URL: str | None = None

    def to_dict(self):
        # Normalize keys to snake_case for file output consistency
        d = {
            "vid": self.VID,
            "vendor": self.Vendor,
            "product": self.Product,
            "cctl": self.CCTL,
            "certification_date": self.Certification_Date,
            "status": self.Status,
            "conformance_claims": self.Conformance_Claims,
            "assurance_maintenance_date": self.Assurance_Maintenance_Date,
            "maintenance_update": self.Maintenance_Update,
            "scheme": self.Scheme,
            "product_url": self.Product_URL,
        }
        return d

def _extract_fields_from_card(el) -> Dict[str, str]:
    # Try common patterns seen on NIAP product cards/details
    data: Dict[str, str] = {}
    # Strategy 1: definition list style (dt/dd)
    dts = el.locator("dt")
    dds = el.locator("dd")
    if dts.count() and dds.count() and dts.count() == dds.count():
        for i in range(dts.count()):
            label = normalize_label(squash_ws(dts.nth(i).inner_text()))
            value = squash_ws(dds.nth(i).inner_text())
            data[label] = value
    else:
        # Strategy 2: key spans/strong: value pairs
        rows = el.locator("css=*:text-matches('.*', 'i')")
        # We'll scan leaf nodes for label:value patterns
        try:
            inner = el.inner_text()
        except Exception:
            inner = ""
        # Fallback: parse lines containing colon
        for line in (inner or "").splitlines():
            if ":" in line:
                label, value = line.split(":", 1)
                label = normalize_label(squash_ws(label))
                value = squash_ws(value)
                if label:
                    data.setdefault(label, value)
    return data

def scrape_page(page, results: List[Record]) -> None:
    # The grid loads dynamically; ensure content is present
    page.wait_for_load_state("networkidle")
    # Try to find item cards (several likely selectors)
    selectors = [
        "[data-testid='product-card']",
        "article:has-text('VID')",
        "div.card:has-text('VID')",
        ".product-card, .card, .grid > div",
    ]
    cards = None
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count():
            cards = loc
            break
    if cards is None or cards.count() == 0:
        # Some pages load via endless scroll; try scrolling and re-checking
        for _ in range(10):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(300)
            if page.locator("article, .card, [data-testid]").count():
                cards = page.locator("article, .card, [data-testid]")
                break
    if cards is None:
        return

    for i in range(cards.count()):
        card = cards.nth(i)
        fields = _extract_fields_from_card(card)
        rec = Record()
        # Map fields
        for f in CANON_FIELDS:
            v = None
            # try canonical
            if f in fields:
                v = fields[f]
            else:
                # try aliases
                for alias in FIELD_ALIASES.get(f, []):
                    if alias in fields:
                        v = fields[alias]
                        break
            if v:
                key = f.replace(" ", "_")
                setattr(rec, key if key != "Conformance_Claims" else "Conformance_Claims", v)
        # Try to grab a URL if present
        link = card.locator("a:has-text('Details'), a[href*='/products/']")
        if link.count():
            try:
                rec.Product_URL = link.first.get_attribute("href")
            except Exception:
                pass
        results.append(rec)

def run(headless: bool = True, out_csv: str = "output/niap_products.csv", out_jsonl: str = "output/niap_products.jsonl") -> int:
    results: List[Record] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120000)
        # If there is pagination, attempt to iterate
        page.wait_for_timeout(1000)
        scrape_page(page, results)
        # Look for a "Next" or paginator
        has_next = True
        seen = set()
        while has_next:
            has_next = False
            for sel in ["button[aria-label='Next']", "a[rel='next']", "button:has-text('Next')", "a:has-text('Next')"]:
                next_btn = page.locator(sel)
                if next_btn.count() and next_btn.first.is_enabled():
                    # avoid infinite loops
                    key = page.url + "::" + str(len(results))
                    if key in seen:
                        has_next = False
                        break
                    seen.add(key)
                    next_btn.first.click()
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(1000)
                    scrape_page(page, results)
                    has_next = True
                    break
        browser.close()

    # Write files
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    import csv
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(Record().to_dict().keys()))
        w.writeheader()
        for r in results:
            w.writerow(r.to_dict())

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

    print(f"Saved {len(results)} records to {out_csv} and {out_jsonl}")
    return len(results)

if __name__ == "__main__":
    headless = os.environ.get("HEADLESS", "1") != "0"
    out_csv = os.environ.get("OUT_CSV", "output/niap_products.csv")
    out_jsonl = os.environ.get("OUT_JSONL", "output/niap_products.jsonl")
    run(headless=headless, out_csv=out_csv, out_jsonl=out_jsonl)
