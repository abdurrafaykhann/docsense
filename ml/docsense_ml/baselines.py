"""No-LLM baseline extractor (regex heuristics) exposed as a fake chat model.

Plugging in at the model seam keeps every other pipeline stage identical, so the comparison
"heuristics vs LLM" is apples to apples and needs no API keys.
"""

from __future__ import annotations

import re
from datetime import datetime

from apps.validation.schema import InvoiceExtraction

MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_AMOUNT = re.compile(
    r"(?<![\w.])\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?(?![\w])|(?<![\w.])\d+(?:[.,]\d{1,2})?(?![\w%])"
)


def parse_amount(token: str, idr: bool = False) -> float | None:
    """Locale-tolerant amount parse. idr=True treats '.'/',' + 3 digits as thousands."""
    t = re.sub(r"[^\d.,]", "", token)
    if not t or not re.search(r"\d", t):
        return None
    if idr:
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", t):
            return float(re.sub(r"[.,]", "", t))
        return float(t.replace(",", ".")) if re.fullmatch(r"\d+[.,]\d{1,2}", t) else _plain(t)
    return _plain(t)


def _plain(t: str) -> float | None:
    if "," in t and "." in t:
        # last separator is the decimal point
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        head, _, tail = t.rpartition(",")
        t = head.replace(",", "") + ("." + tail if len(tail) != 3 else tail)
    try:
        return float(t)
    except ValueError:
        return None


def _amounts(line: str, idr: bool) -> list[float]:
    out = []
    for m in _AMOUNT.finditer(line):
        if line[m.end() : m.end() + 1] == "%":
            continue
        v = parse_amount(m.group(), idr)
        if v is not None:
            out.append(v)
    return out


def _date(text: str) -> str | None:
    m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", text)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if y < 100 else 0
        try:
            return datetime(y, mo, d).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        return m.group()
    m = re.search(r"\b(\d{1,2})[ \-]([A-Za-z]{3})[a-z]*[ \-,]+(\d{4})\b", text)
    if m and m[2].lower() in MONTHS:
        try:
            return datetime(int(m[3]), MONTHS[m[2].lower()], int(m[1])).date().isoformat()
        except ValueError:
            pass
    return None


SECTION_RE = re.compile(r"^\[(VENDOR|META|TABLE|TOTALS|OTHER)\]$")


def parse_sections(text: str) -> dict[str, list[str]] | None:
    """Split region-labelled prompt text into {section: lines}; None if there are no markers."""
    sections: dict[str, list[str]] = {}
    current = None
    for ln in (x.strip() for x in text.splitlines()):
        if not ln or ln.startswith("---"):
            continue
        m = SECTION_RE.match(ln)
        if m:
            current = m.group(1).lower()
            sections.setdefault(current, [])
        elif current:
            sections[current].append(ln)
    return sections or None


def extract_text(text: str, idr: bool = False) -> dict:
    """Heuristic extraction. With region markers, each field is searched only where it belongs."""
    sections = parse_sections(text)
    all_lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.startswith("---") and not SECTION_RE.match(ln.strip())
    ]
    if sections:
        vendor_l = sections.get("vendor") or all_lines
        meta_l = (sections.get("meta") or []) + (sections.get("vendor") or []) or all_lines
        totals_l = sections.get("totals") or all_lines
        table_l = sections.get("table") or all_lines
        id_l = vendor_l + (sections.get("meta") or [])
    else:
        vendor_l = meta_l = totals_l = table_l = id_l = all_lines
    lines = all_lines

    out: dict = {"line_items": []}
    for ln in vendor_l:
        if re.search(r"[A-Za-z]{3,}", ln) and not re.search(r"\d{4,}", ln):
            out["vendor_name"] = ln.split("|")[0].strip()
            break
    meta_text = "\n".join(meta_l)
    id_text = "\n".join(id_l)
    out["invoice_date"] = _date(meta_text) or _date("\n".join(lines))
    if m := re.search(r"\bNTN\b[^0-9]*([0-9][0-9\- ]{5,14}[0-9])", id_text, re.I):
        out["ntn"] = m.group(1).strip()
    if m := re.search(
        r"\b(?:STRN|GST|S\.?T\.?R\.?N\.?)\b[^0-9]*([0-9][0-9\- ]{11,22}[0-9])", id_text, re.I
    ):
        out["strn"] = m.group(1).strip()
    if m := re.search(
        r"\b(?:invoice|inv|bill|receipt)\s*(?:no|number|#)?[.:#\s]*([A-Z0-9][A-Z0-9\-/]{2,})",
        meta_text,
        re.I,
    ):
        out["invoice_number"] = m.group(1)

    def last_amount(src: list[str], pattern: str, exclude: str | None = None) -> float | None:
        found = None
        for ln in src:
            if re.search(pattern, ln, re.I) and not (exclude and re.search(exclude, ln, re.I)):
                a = _amounts(ln, idr)
                if a:
                    found = a[-1]
        return found

    out["total"] = last_amount(
        totals_l, r"\btotal\b|\bjumlah\b|\bamount due\b", r"sub\s*-?\s*total"
    )
    out["subtotal"] = last_amount(totals_l, r"sub\s*-?\s*total")
    out["sales_tax"] = last_amount(totals_l, r"\b(tax|ppn|gst|vat|pb1|st)\b")
    if m := re.search(r"(\d+(?:\.\d+)?)\s*%", "\n".join(totals_l)):
        out["tax_rate"] = float(m.group(1))
    if out["total"] is None:
        pool = totals_l if sections and sections.get("totals") else all_lines
        amounts = [a for ln in pool for a in _amounts(ln, idr)]
        out["total"] = max(amounts) if amounts else None

    skip = re.compile(
        r"total|tax|ppn|gst|cash|change|tunai|kembali|discount|service|date|tel|npwp"
        r"|ntn|strn|invoice|\binv\b|bill|receipt|ref\b|\bno\b",
        re.I,
    )
    start = 0 if sections and sections.get("table") else 1
    for ln in table_l[start:]:
        if skip.search(ln):
            continue
        a = _amounts(ln, idr)
        desc = re.split(r"\d", ln, maxsplit=1)[0].strip(" |:-xX")
        if a and len(desc) >= 3:
            out["line_items"].append({"description": desc, "amount": a[-1]})
    return out


class _Runnable:
    def __init__(self, schema, idr):
        self.schema, self.idr = schema, idr

    def invoke(self, messages):
        text = messages[-1][1].split("OCR text:\n", 1)[-1]
        return self.schema.model_validate(
            {k: v for k, v in extract_text(text, self.idr).items() if v is not None}
        )


class RegexModel:
    def __init__(self, idr: bool = False):
        self.idr = idr

    def with_structured_output(self, schema):
        assert schema is InvoiceExtraction
        return _Runnable(schema, self.idr)
