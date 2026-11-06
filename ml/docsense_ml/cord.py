"""CORD-v2 (Naver Clova, CC BY 4.0) -> DocSense eval-set format.

CORD receipts are Indonesian (IDR, ~10% PPN). It annotates menu items, subtotal, tax and total;
it has NO vendor name / date / NTN, so those fields are not annotated here (see metrics.py).
Citation: Park et al., "CORD: A Consolidated Receipt Dataset for Post-OCR Parsing", 2019.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

from .evalset import write_manifest

REPO = "naver-clova-ix/cord-v2"
TEST_FILE = "data/test-00000-of-00001-9c204eb3f4e11791.parquet"  # ~234 MB


def parse_money(v) -> float | None:
    """CORD amounts: '1,346,000', '75.000', '12000' -> float (IDR has no decimals)."""
    if v is None:
        return None
    s = re.sub(r"[^\d.,]", "", str(v))
    if not s:
        return None
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        return float(re.sub(r"[.,]", "", s))
    if re.fullmatch(r"\d+[.,]\d{1,2}", s):
        return float(s.replace(",", "."))
    digits = re.sub(r"\D", "", s)
    return float(digits) if digits else None


def cord_truth(gt_parse: dict) -> dict:
    menu = gt_parse.get("menu") or []
    if isinstance(menu, dict):
        menu = [menu]
    items = []
    for m in menu:
        if isinstance(m.get("nm"), str) or m.get("price") is not None:
            items.append(
                {
                    "description": m.get("nm"),
                    "quantity": parse_money(m.get("cnt")),
                    "amount": parse_money(m.get("price")),
                }
            )
    sub = gt_parse.get("sub_total") or {}
    tot = gt_parse.get("total") or {}
    truth = {
        "subtotal": parse_money(sub.get("subtotal_price")),
        "sales_tax": parse_money(sub.get("tax_price")),
        "total": parse_money(tot.get("total_price")),
        "line_items": [i for i in items if i["amount"] is not None],
    }
    # only annotate fields that CORD actually labels for this receipt
    return {k: v for k, v in truth.items() if v not in (None, []) or k == "line_items"}


def download_test_split(raw_dir: Path) -> Path:
    """Stream the test parquet (~234 MB) with resume support; plain HTTPS, no HF client."""
    import requests

    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / "cord-v2-test.parquet"
    if dest.exists():
        return dest
    part = dest.with_suffix(".part")
    url = f"https://huggingface.co/datasets/{REPO}/resolve/main/{TEST_FILE}"
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, stream=True, timeout=60, headers=headers) as r:
        r.raise_for_status()
        with part.open("ab" if have else "wb") as fh:
            done = have
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                print(f"downloaded {done / 1e6:.0f} MB", flush=True) if done % (32 << 20) < (
                    1 << 20
                ) else None
    part.rename(dest)
    print()
    return dest


def convert(parquet: Path, out_dir: Path, limit: int | None = None) -> int:
    import pyarrow.parquet as pq
    from PIL import Image

    out_dir = Path(out_dir)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    rows = []
    pf = pq.ParquetFile(parquet)
    for batch in pf.iter_batches(batch_size=8):
        for rec in batch.to_pylist():
            gt = json.loads(rec["ground_truth"])
            truth = cord_truth(gt.get("gt_parse", {}))
            if "total" not in truth:
                continue
            idx = len(rows)
            name = f"cord_{idx:04d}.png"
            img = Image.open(io.BytesIO(rec["image"]["bytes"])).convert("RGB")
            img.save(out_dir / "images" / name)
            rows.append(
                {
                    "id": f"cord_{idx:04d}",
                    "image": f"images/{name}",
                    "truth": truth,
                    "meta": {"dataset": "CORD-v2", "license": "CC-BY-4.0", "currency": "IDR"},
                }
            )
            if limit and len(rows) >= limit:
                write_manifest(out_dir, rows)
                return len(rows)
    write_manifest(out_dir, rows)
    return len(rows)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Download CORD-v2 test split and convert it")
    ap.add_argument("--out", default="ml/data/cord")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    out = Path(args.out)
    path = download_test_split(out / "_raw")
    print("converted", convert(path, out, args.limit), "receipts ->", out)
