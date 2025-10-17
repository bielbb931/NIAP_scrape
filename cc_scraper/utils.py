
from __future__ import annotations
import re
from typing import Dict, List

FIELD_ALIASES: Dict[str, List[str]] = {
    "VID": ["VID", "Validation ID", "VPL ID", "Validation Identifier"],
    "Vendor": ["Vendor", "Manufacturer"],
    "Product": ["Product", "Product Name", "TOE"],
    "CCTL": ["CCTL", "CC Testing Lab", "Lab", "Testing Laboratory"],
    "Certification Date": ["Certification Date", "Check-in Date", "Validation Date", "Date"],
    "Status": ["Status", "State"],
    "Conformance Claims": ["Conformance Claims", "PP", "Protection Profile", "Conformance"],
    "Assurance Maintenance Date": ["Assurance Maintenance Date", "AMD", "Maintenance Date"],
    "Maintenance Update": ["Maintenance Update", "Maintenance", "Assurance Maintenance"],
    "Scheme": ["Scheme", "Country"],
}

def normalize_label(label: str) -> str:
    label = (label or "").strip()
    for canonical, aliases in FIELD_ALIASES.items():
        for a in aliases:
            if a.lower() == label.lower():
                return canonical
    return label

def squash_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()
