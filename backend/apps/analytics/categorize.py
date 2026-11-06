"""Keyword spend categoriser for approved invoices (transparent, no model needed)."""

from __future__ import annotations

import re

KEYWORDS = {
    "grocery": "rice oil sugar tea milk eggs flour biscuits chilli dal atta ghee".split(),
    "electronics": "led bulb cord charger usb cable power bank fan socket earphones switch".split(),
    "pharmacy": "paracetamol syrup vitamin antiseptic cream mask thermometer tablet".split(),
    "hardware": "cement paint pvc pipe nails drill brush steel tiles".split(),
    "restaurant": "karahi biryani naan drink kabab raita jamun roll burger".split(),
    "services": "support consultancy maintenance printing delivery licence license hours".split(),
}


def categorize(descriptions: list[str]) -> str:
    words = re.findall(r"[a-z]+", " ".join(descriptions).lower())
    scores = {c: sum(w in kws for w in words) for c, kws in KEYWORDS.items()}
    best, hits = max(scores.items(), key=lambda kv: kv[1])
    return best if hits else "uncategorized"
