# cc_scraper/niap_scraper.py
from __future__ import annotations
import os, csv, json, re
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass
from playwright.sync_api import sync_playwright

TARGET_URL = os.environ.get("NIAP_URL", "https://www.niap-ccevs.org/products")

REQUIRED_HEADERS = [
    "VID","Vendor","Product","CCTL","Certification Date","Status",
    "Conformance Claims","Assurance Maintenance Date","Maintenance Update","Scheme",
]

ALIASES = {
    "vid":"VID","vendor":"Vendor","product":"Product","cctl":"CCTL",
    "certification date":"Certification Date","status":"Status",
    "conformance claims":"Conformance Claims",
    "assurance maintenance date":"Assurance Maintenance Date",
    "maintenance update":"Maintenance Update","scheme":"Scheme",
}

def norm(s: Optional[str]) -> str:
    return " ".join((s or "").split()).strip()

def to_canonical(header: str) -> Optional[str]:
    h = norm(header).lower()
    return ALIASES.get(h)

@dataclass
class Row:
    VID: str = ""; Vendor: str = ""; Product: str = ""; CCTL: str = ""
    Certification_Date: str = ""; Status: str = ""
    Conformance_Claims: str = ""; Assurance_Maintenance_Date: str = ""
    Maintenance_Update: str = ""; Scheme: str = ""
    Product_URL: str = ""
    def to_dict(self) -> Dict[str, str]:
        return {
            "vid": self.VID, "vendor": self.Vendor, "product": self.Product, "cctl": self.CCTL,
            "certification_date": self.Certification_Date, "status": self.Status,
            "conformance_claims": self.Conformance_Claims,
            "assurance_maintenance_date": self.Assurance_Maintenance_Date,
            "maintenance_update": self.Maintenance_Update, "scheme": self.Scheme,
            "product_url": self.Product_URL,
        }

# ---------- grid helpers ----------
def _find_grid(page):
    for sel in ["div[role='grid']","div.MuiDataGrid-root","div.MuiDataGrid-main","table"]:
        loc = page.locator(sel)
        if loc.count():
            return loc.first
    return None

def _get_headers(page, grid):
    header_cells = page.get_by_role("columnheader")
    if header_cells.count() == 0:
        header_cells = grid.locator("thead tr th")
    index_to_name = {}
    for i in range(header_cells.count()):
        txt = norm(header_cells.nth(i).inner_text())
        canon = to_canonical(txt)
        if canon:
            index_to_name[i] = canon
    return index_to_name

def _rows_locator(page):
    return page.locator("div[role='row']").filter(has_not=page.locator("div[role='columnheader']"))

def _grid_scroller(page):
    loc = page.locator("div.MuiDataGrid-virtualScroller").first
    return loc if loc.count() else None

def _scroll_grid_to_end(page, pause_ms: int = 120, repeats: int = 10):
    """Scroll INSIDE the grid (not the window) so virtualized rows render."""
    scroller = _grid_scroller(page)
    if scroller:
        for _ in range(repeats):
            scroller.evaluate("(el) => { el.scrollTop = el.scrollHeight }")
            page.wait_for_timeout(pause_ms)
    else:
        for _ in range(repeats):
            page.mouse.wheel(0, 2000); page.wait_for_timeout(pause_ms)

def _get_total_from_pager(page) -> Optional[int]:
    # Parse "1–250 of 277"
    sels = ["div.MuiTablePagination-displayedRows","[class*='MuiTablePagination-displayedRows']","[aria-live='polite']","div[role='status']"]
    for s in sels:
        loc = page.locator(s)
        for i in range(min(3, loc.count())):
            txt = (loc.nth(i).inner_text() or "").strip()
            m = re.search(r"\bof\s+(\d{1,7})\b", txt)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    pass
    return None

def _set_page_size_to_max(page):
    try:
        combos = page.get_by_role("combobox")
        target = None
        for i in range(combos.count()):
            al = ((combos.nth(i).get_attribute("aria-label") or "") + " " +
                  (combos.nth(i).get_attribute("aria-labelledby") or "")).lower()
            if "rows per page" in al:
                target = combos.nth(i); break
        if not target and combos.count():
            target = combos.first
        if target and target.is_visible():
            target.click(); page.wait_for_timeout(200)
            options = page.get_by_role("option")
            if options.count() == 0:
                options = page.get_by_role("menuitem")
            best = None; best_val = -1
            for i in range(options.count()):
                txt = (options.nth(i).inner_text() or "").strip()
                num = int("".join(ch for ch in txt if ch.isdigit()) or "0")
                if num > best_val:
                    best_val = num; best = options.nth(i)
            if best and best_val > 0:
                best.click(); page.wait_for_timeout(400)
                return True
    except Exception:
        pass
    return False

# ---------- extraction (dedupe by Product, with fallbacks) ----------
def _extract_rows(page, grid, index_to_name, seen_products: Set[str]) -> List[Row]:
    """
    Dedup key preference: Product (normalized, lowercase) -> Product_URL -> full row string.
    """
    rows: List[Row] = []
    data_rows = _rows_locator(page)
    if data_rows.count() == 0:
        data_rows = grid.locator("tbody tr")

    for r_i in range(data_rows.count()):
        row_loc = data_rows.nth(r_i)
        cells = row_loc.get_by_role("gridcell")
        if cells.count() == 0:
            cells = row_loc.locator("td")
        if cells.count() == 0:
            continue

        # First pass: collect all values so we can form the key from Product
        values: Dict[str, str] = {}
        product_url = ""
        for c_i in range(cells.count()):
            key = index_to_name.get(c_i)
            val = norm(cells.nth(c_i).inner_text())
            if key == "Product":
                link = cells.nth(c_i).locator("a")
                if link.count():
                    product_url = link.first.get_attribute("href") or ""
            if key:
                values[key] = val

        # Build dedupe key
        product_key = values.get("Product", "")
        key_norm = product_key.lower().strip()
        if not key_norm:
            # fallback to URL
            if product_url:
                key_norm = f"url::{product_url.strip().lower()}"
            else:
                # last resort: whole row joined
                all_text = " | ".join(values.get(k, "") for k in REQUIRED_HEADERS)
                key_norm = f"row::{norm(all_text).lower()}"

        if key_norm in seen_products:
            continue
        seen_products.add(key_norm)

        # Populate Row dataclass
        rec = Row(
            VID=values.get("VID",""),
            Vendor=values.get("Vendor",""),
            Product=values.get("Product",""),
            CCTL=values.get("CCTL",""),
            Certification_Date=values.get("Certification Date",""),
            Status=values.get("Status",""),
            Conformance_Claims=values.get("Conformance Claims",""),
            Assurance_Maintenance_Date=values.get("Assurance Maintenance Date",""),
            Maintenance_Update=values.get("Maintenance Update",""),
            Scheme=values.get("Scheme",""),
            Product_URL=product_url,
        )
        rows.append(rec)

    return rows

# ---------- pager helpers (arrows only UI) ----------
def _pager_next_btn(page):
    for s in [
        "button[title='Next page']",
        "button[aria-label='Go to next page']",
        "button[aria-label*='Next']",
        "button.MuiPaginationItem-previousNext[aria-label*='Next']",
    ]:
        loc = page.locator(s).first
        if loc.count():
            return loc
    return None

def _is_disabled(btn) -> bool:
    try:
        if not btn or not btn.count():
            return True
        return (not btn.is_enabled()) or ("Mui-disabled" in (btn.get_attribute("class") or ""))
    except Exception:
        return True

# --------------- main ----------------
def run(headless: bool = True,
        out_csv: str = "output/niap_products.csv",
        out_jsonl: str = "output/niap_products.jsonl") -> int:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    os.makedirs(os.path.dirname(out_jsonl), exist_ok=True)

    all_rows: List[Row] = []
    seen_products: Set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context()
        page = ctx.new_page()

        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_load_state("networkidle")
        page.get_by_role("columnheader", name="VID").first.wait_for(state="visible", timeout=60_000)

        # Best-effort: dismiss cookie/banner
        for txt in ["Accept","I Agree","Got it","Close"]:
            try:
                b = page.get_by_role("button", name=txt).first
                if b and b.is_visible():
                    b.click(); page.wait_for_timeout(250)
            except Exception:
                pass

        grid = _find_grid(page)
        if not grid: raise RuntimeError("Could not locate the products grid/table.")
        header_map = _get_headers(page, grid)
        if not header_map: raise RuntimeError("Could not read column headers; grid structure may have changed.")

        # Max rows/page if possible
        try: _set_page_size_to_max(page)
        except Exception: pass

        # Ensure first page fully rendered
        _scroll_grid_to_end(page)

        total = _get_total_from_pager(page) or 0

        # Collect the current page
        def collect_current():
            nonlocal all_rows, grid, header_map
            _scroll_grid_to_end(page)
            grid = _find_grid(page) or grid
            batch = _extract_rows(page, grid, header_map, seen_products)
            all_rows.extend(batch)

        collect_current()

        # Click Next until disabled; collect after each advance
        next_btn = _pager_next_btn(page)
        safety = 0
        while next_btn and not _is_disabled(next_btn):
            safety += 1
            if safety > 100:  # guard
                break
            next_btn.click()
            for _ in range(10):
                page.wait_for_timeout(120)
                _scroll_grid_to_end(page, pause_ms=40, repeats=1)
            collect_current()
            next_btn = _pager_next_btn(page)
            if total and len(seen_products) >= total:
                break

        # Extra collect on final page (some UIs need one more render)
        collect_current()

        browser.close()

    # Write CSV + JSONL
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(Row().to_dict().keys()))
        writer.writeheader()
        for r in all_rows:
            writer.writerow(r.to_dict())

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

    print(f"Saved {len(all_rows)} rows to {out_csv} and {out_jsonl}")
    return len(all_rows)

if __name__ == "__main__":
    headless = os.environ.get("HEADLESS", "1") != "0"
    out_csv  = os.environ.get("OUT_CSV", "output/niap_products.csv")
    out_jsonl = os.environ.get("OUT_JSONL", "output/niap_products.jsonl")
    run(headless=headless, out_csv=out_csv, out_jsonl=out_jsonl)


