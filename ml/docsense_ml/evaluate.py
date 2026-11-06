"""Extraction evaluation: run the pipeline over a labelled set and score it.

python -m docsense_ml.evaluate --set ml/data/cord --arm regex --idr
python -m docsense_ml.evaluate --set ml/data/cord --arm llm --provider groq --idr
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from apps.pipeline import core
from apps.pipeline.layout import Region
from apps.validation.grounding import Word

from . import metrics
from .evalset import Sample, load_set


def evaluate(
    samples: list[Sample],
    *,
    ocr,
    llm,
    default_tax_rate: float = 18.0,
    oracle_ocr: bool = False,
    text_builder=core.whole_page_text,
    layout=None,
    oracle_layout: bool = False,
    on_progress=None,
) -> dict:
    docs = []
    requests = 0

    def count(rec):
        nonlocal requests
        if rec.status != "cache_hit":
            requests += 1

    llm.on_usage = count
    for i, s in enumerate(samples):
        started = time.monotonic()
        entry = {"id": s.id, "error": None}
        try:
            img = s.load_image()
            wbp = None
            if oracle_ocr and s.words:
                wbp = {1: [Word.from_dict(w) for w in s.words]}
            regions = None
            if oracle_layout and s.meta.get("regions"):  # arm C: ground-truth regions
                regions = {1: [Region(r["cls"], r["bbox"], 1.0, 1) for r in s.meta["regions"]]}
            res = core.process(
                [img],
                ocr,
                llm,
                words_by_page=wbp,
                default_tax_rate=default_tax_rate,
                text_builder=text_builder,
                layout=layout,
                regions_by_page=regions,
            )
            pred = res.invoice.model_dump(mode="json")
            entry.update(
                needs_review=res.needs_review,
                overall=res.overall,
                issues=[i.code for i in res.issues],
                prompt_chars=len(res.prompt_text),
            )
        except Exception as exc:  # noqa: BLE001 - a bad sample must not abort the run
            pred = {}
            entry.update(
                error=f"{type(exc).__name__}: {exc}"[:300],
                needs_review=True,
                overall=0.0,
                issues=["pipeline_error"],
                prompt_chars=0,
            )
        entry["pred"] = pred
        entry["score"] = metrics.score_document(pred, s.truth)
        entry["seconds"] = round(time.monotonic() - started, 2)
        docs.append(entry)
        if on_progress:
            on_progress(i + 1, len(samples), entry)

    agg = metrics.aggregate(docs)
    chars = [d["prompt_chars"] for d in docs if d["prompt_chars"]]
    agg["mean_prompt_tokens_est"] = round(sum(chars) / len(chars) / 4, 1) if chars else None
    agg["llm_requests"] = requests
    agg["errors"] = sum(1 for d in docs if d["error"])
    return {"metrics": agg, "docs": docs}


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, help="eval-set directory (manifest.jsonl)")
    ap.add_argument("--arm", choices=["regex", "llm"], required=True)
    ap.add_argument("--provider", default="groq", choices=["groq", "gemini"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--idr", action="store_true", help="IDR amounts + 10%% default tax (CORD)")
    ap.add_argument("--oracle-ocr", action="store_true", help="use the set's own word boxes")
    ap.add_argument(
        "--layout",
        default="none",
        help="none | oracle (ground-truth regions) | path/to/weights.pt (my YOLO)",
    )
    ap.add_argument("--cache-dir", default="ml/.cache")
    ap.add_argument("--min-interval", type=float, default=2.5, help="seconds between LLM calls")
    ap.add_argument("--out", help="results JSON (default docs/eval-results/<set>-<arm>.json)")
    args = ap.parse_args(argv)

    samples = load_set(args.set, args.limit)
    name = Path(args.set).name

    from apps.llm.cache import MemoryCache
    from apps.llm.client import LLMClient, Provider
    from apps.pipeline.ocr import DocTROCR

    from .baselines import RegexModel
    from .caches import CachedOCR

    ocr = CachedOCR(DocTROCR(), args.cache_dir)
    if args.arm == "regex":
        llm = LLMClient([Provider("regex", RegexModel(idr=args.idr))], cache=MemoryCache())
    else:
        from .llm import make_llm

        llm = make_llm(args.provider, args.cache_dir, args.min_interval)

    def progress(i, n, e):
        print(f"[{i}/{n}] {e['id']} review={e['needs_review']} {e['seconds']}s", flush=True)

    layout = None
    if args.layout not in ("none", "oracle"):
        from apps.pipeline.layout import YoloLayoutDetector

        layout = YoloLayoutDetector(args.layout)
    result = evaluate(
        samples,
        ocr=ocr,
        llm=llm,
        default_tax_rate=10.0 if args.idr else 18.0,
        oracle_ocr=args.oracle_ocr,
        layout=layout,
        oracle_layout=args.layout == "oracle",
        on_progress=progress,
    )
    payload = {
        "kind": "extraction",
        "dataset": name,
        "arm": (args.arm if args.arm == "regex" else f"llm:{args.provider}")
        + {"none": "", "oracle": " + oracle layout"}.get(args.layout, " + my layout model"),
        "n": len(samples),
        "ocr": "oracle" if args.oracle_ocr else "doctr",
        "git_sha": git_sha(),
        "created_at": datetime.now(UTC).isoformat(),
        "ocr_cache": {"hits": ocr.hits, "misses": ocr.misses},
        **result,
    }
    suffix = {"none": "", "oracle": "-oracle-layout"}.get(args.layout, "-layout-model")
    out = Path(args.out or f"docs/eval-results/{name}-{args.arm}{suffix}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    m = result["metrics"]
    print(json.dumps({k: m[k] for k in ("n_docs", "micro", "total_exact_match", "review_rate")}))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
