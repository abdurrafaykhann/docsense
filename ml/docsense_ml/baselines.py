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


def extract_text(text: str, idr: bool = False) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("---")]
    out: dict = {"line_items": []}
    for ln in lines:
        if re.search(r"[A-Za-z]{3,}", ln) and not re.search(r"\d{4,}", ln):
            out["vendor_name"] = ln.split("|")[0].strip()
            break
    joined = "\n".join(lines)
    out["invoice_date"] = _date(joined)
    if m := re.search(r"\bNTN\b[^0-9]*([0-9][0-9\- ]{5,14}[0-9])", joined, re.I):
        out["ntn"] = m.group(1).strip()
    if m := re.search(
        r"\b(?:STRN|GST|S\.?T\.?R\.?N\.?)\b[^0-9]*([0-9][0-9\- ]{11,22}[0-9])", joined, re.I
    ):
        out["strn"] = m.group(1).strip()
    if m := re.search(
        r"\b(?:invoice|inv|bill|receipt)\s*(?:no|number|#)?[.:#\s]*([A-Z0-9][A-Z0-9\-/]{2,})",
        joined,
        re.I,
    ):
        out["invoice_number"] = m.group(1)

    def last_amount(pattern: str, exclude: str | None = None) -> float | None:
        found = None
        for ln in lines:
            if re.search(pattern, ln, re.I) and not (exclude and re.search(exclude, ln, re.I)):
                a = _amounts(ln, idr)
                if a:
                    found = a[-1]
        return found

    out["total"] = last_amount(r"\btotal\b|\bjumlah\b|\bamount due\b", r"sub\s*-?\s*total")
    out["subtotal"] = last_amount(r"sub\s*-?\s*total")
    out["sales_tax"] = last_amount(r"\b(tax|ppn|gst|vat|pb1|st)\b")
    if m := re.search(r"(\d+(?:\.\d+)?)\s*%", joined):
        out["tax_rate"] = float(m.group(1))
    if out["total"] is None:
        all_amounts = [a for ln in lines for a in _amounts(ln, idr)]
        out["total"] = max(all_amounts) if all_amounts else None

    skip = re.compile(
        r"total|tax|ppn|gst|cash|change|tunai|kembali|discount|service|date|tel|npwp"
        r"|ntn|strn|invoice|inv|bill|receipt|ref|no",
        re.I,
    )
    for ln in lines[1:]:
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
