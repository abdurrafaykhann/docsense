"""Builds and executes ml/notebooks/02_anomaly_methods.ipynb (outputs embedded).

    python ml/notebooks/build_anomaly_notebook.py
"""

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

HERE = Path(__file__).parent
nb = nbf.v4.new_notebook()
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

nb.cells = [
    md(
        "# Anomaly & fraud detection: methods and why we chose them\n\n"
        "DocSense flags four kinds of problems in approved invoices: **exact/near duplicates**, "
        "**image duplicates**, **unusual amounts** and **price creep**. This notebook builds a "
        "synthetic spend history with *known* injected anomalies, compares candidate methods on "
        "precision/recall, and records the reasoning behind the methods used in "
        "`backend/apps/analytics/detectors.py`.\n\n"
        "Everything here is deterministic (fixed seeds) and uses the production detector code."
    ),
    code(
        "import sys\nfrom pathlib import Path\nROOT = Path.cwd().resolve()\n"
        "while not (ROOT / 'backend').exists(): ROOT = ROOT.parent\n"
        "sys.path.insert(0, str(ROOT / 'backend'))\n"
        "import numpy as np, pandas as pd, matplotlib\nmatplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\nfrom datetime import date, timedelta\n"
        "from apps.analytics import detectors as D\nrng = np.random.default_rng(42)\n"
        "print('backend:', ROOT / 'backend')"
    ),
    md(
        "## 1. A synthetic spend history with ground-truth anomalies\n\n"
        "12 vendors with very different typical invoice sizes (Rs 400 corner shop up to Rs 90,000 "
        "wholesaler), 20-40 invoices each, log-normal totals. We inject three amount anomalies per "
        "vendor type (x4-x9 spikes, tiny invoices, abnormal tax ratio) and keep the labels."
    ),
    code(
        "rows, labels, vendors = [], {}, {}\nnext_id = 1\n"
        "for v in range(1, 13):\n"
        "    scale = float(np.exp(rng.uniform(np.log(400), np.log(90000))))\n"
        "    n = int(rng.integers(20, 41)); vendors[v] = scale\n"
        "    for i in range(n):\n"
        "        total = float(scale * np.exp(rng.normal(0, 0.18)))\n"
        "        sub = total / 1.18\n"
        "        rows.append(D.InvoiceRow(next_id, v, f'V{v}-{i}', date(2024,1,1)+timedelta(days=int(i*(300/n))),\n"
        "                                 total, sub, total - sub, int(rng.integers(1, 7))))\n"
        "        labels[next_id] = None; next_id += 1\n"
        "# inject anomalies\n"
        "inj = {}\n"
        "for r in rng.choice(rows, 18, replace=False):\n"
        "    kind = rng.choice(['spike', 'tiny', 'tax'])\n"
        "    if kind == 'spike':  r.total = r.total * float(rng.uniform(4, 9)); r.subtotal = r.total/1.18; r.sales_tax = r.total - r.subtotal\n"
        "    if kind == 'tiny':   r.total = r.total / float(rng.uniform(6, 12)); r.subtotal = r.total/1.18; r.sales_tax = r.total - r.subtotal\n"
        "    if kind == 'tax':    r.sales_tax = 0.0; r.subtotal = r.total; r.n_items = 35\n"
        "    inj[r.document_id] = kind\n"
        "df = pd.DataFrame([r.__dict__ for r in rows])\n"
        "print(len(df), 'invoices,', len(inj), 'injected anomalies:', pd.Series(inj).value_counts().to_dict())"
    ),
    md("## 2. EDA: why a single global threshold cannot work"),
    code(
        "fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))\n"
        "ax[0].hist(np.log10(df.total), bins=40, color='#6366f1'); ax[0].set_title('log10(total): one fat, multi-modal blob')\n"
        "df.assign(v=df.vendor_id).boxplot(column='total', by='v', ax=ax[1], showfliers=True); ax[1].set_yscale('log')\n"
        "ax[1].set_title('per vendor (log scale): different centres and spreads'); plt.suptitle('')\n"
        "plt.tight_layout(); plt.savefig('/dev/null') if False else plt.show()\n"
        "print('between-vendor spread of medians: x%.0f' % (df.groupby('vendor_id').total.median().max() / df.groupby('vendor_id').total.median().min()))"
    ),
    md(
        "## 3. Comparing amount-outlier methods\n\n"
        "* **Global z-score** on totals (the naive baseline)\n"
        "* **Per-vendor classical z-score** (mean/std)\n"
        "* **Per-vendor robust z-score** (median/MAD on log totals) - production method #1\n"
        "* **IsolationForest** on vendor-relative size, tax ratio and item count - production method #2\n"
        "* **Robust + IsolationForest merged** - what DocSense actually runs"
    ),
    code(
        "def score(flagged):\n"
        "    flagged = set(flagged); truth = set(inj)\n"
        "    tp = len(flagged & truth); p = tp/len(flagged) if flagged else 0; r = tp/len(truth)\n"
        "    return dict(precision=round(p,3), recall=round(r,3), f1=round(2*p*r/(p+r),3) if p+r else 0, flagged=len(flagged))\n"
        "res = {}\n"
        "z = (df.total - df.total.mean())/df.total.std()\n"
        "res['global z > 3'] = score(df.document_id[z.abs() > 3])\n"
        "g = df.groupby('vendor_id').total\n"
        "zc = (df.total - g.transform('mean'))/g.transform('std')\n"
        "res['per-vendor z > 3'] = score(df.document_id[zc.abs() > 3])\n"
        "rb = D.robust_outliers(rows); res['per-vendor robust z > 3.5'] = score(f.document_id for f in rb)\n"
        "iso = D.isolation_outliers(rows, contamination=0.03); res['isolation forest'] = score(f.document_id for f in iso)\n"
        "merged = D.merge_outliers(rb, iso); res['robust + isolation (production)'] = score(f.document_id for f in merged)\n"
        "table = pd.DataFrame(res).T; table"
    ),
    md(
        "**Reading the table.** A global threshold is dominated by the biggest vendors, so it misses "
        "spikes at small vendors and flags ordinary big-vendor invoices. Per-vendor *classical* z-scores "
        "fix scale but are themselves distorted by the outliers they are trying to find (the spike inflates "
        "the standard deviation: *masking*). Median/MAD does not have that problem. IsolationForest "
        "catches what totals alone cannot (zero tax on a normal total, 35 line items) and works for "
        "vendors with little history; the union gives the best recall at acceptable precision."
    ),
    code(
        "by_kind = {k: [] for k in ('spike','tiny','tax')}\n"
        "caught = {f.document_id for f in merged}\n"
        "for did, k in inj.items(): by_kind[k].append(did in caught)\n"
        "print('recall by anomaly type (merged):', {k: f'{sum(v)}/{len(v)}' for k, v in by_kind.items()})\n"
        "robust_ids = {f.document_id for f in rb}\n"
        "print('tax-ratio anomalies found by robust z alone:', sum(1 for d,k in inj.items() if k=='tax' and d in robust_ids), '(expected ~0: totals look normal)')"
    ),
    md(
        "## 4. Image duplicates: choosing the perceptual-hash threshold\n\n"
        "We render distinct synthetic invoices, create *re-photographed* copies (JPEG re-encode, slight "
        "rescale, brightness shift) and compare 64-bit pHash Hamming distances of true duplicates vs "
        "different documents."
    ),
    code(
        "import imagehash\nfrom PIL import Image, ImageEnhance\nimport io\n"
        "val = sorted((ROOT/'ml'/'data'/'synth'/'none'/'images'/'val').glob('*.jpg'))[:40]\n"
        "if not val: print('synthetic dataset not built; run python -m docsense_ml.synth.build')\n"
        "def copy_of(im):\n"
        "    im = im.resize((int(im.width*0.9), int(im.height*0.9)))\n"
        "    im = ImageEnhance.Brightness(im).enhance(0.85)\n"
        "    b = io.BytesIO(); im.save(b, 'JPEG', quality=45); return Image.open(io.BytesIO(b.getvalue()))\n"
        "ims = [Image.open(p).convert('RGB') for p in val]\n"
        "h = [str(imagehash.phash(i)) for i in ims]; hc = [str(imagehash.phash(copy_of(i))) for i in ims]\n"
        "same = [D.hamming(a, b) for a, b in zip(h, hc)]\n"
        "diff = [D.hamming(h[i], h[j]) for i in range(len(h)) for j in range(i+1, len(h))]\n"
        "print('true duplicates : max distance', max(same), 'mean', round(np.mean(same),1))\n"
        "print('different docs  : min distance', min(diff), '5th pct', int(np.percentile(diff,5)), 'mean', round(np.mean(diff),1))\n"
        "plt.hist(diff, bins=30, alpha=.6, label='different documents'); plt.hist(same, bins=10, alpha=.8, label='re-photographed copies')\n"
        "plt.axvline(6, color='k', ls='--', label='threshold used (6 bits)'); plt.legend(); plt.xlabel('pHash Hamming distance'); plt.show()\n"
        "print('with threshold 6: duplicate recall', np.mean(np.array(same) <= 6), '| false-match rate', np.mean(np.array(diff) <= 6))"
    ),
    md(
        "## 5. Price creep: sensitivity of the threshold\n\n"
        "Series of 5 monthly prices for one item with +/-2% noise; the last price is raised by a known "
        "percentage. We sweep the detector's `min_increase`."
    ),
    code(
        "def creep_hit(true_pct, thr, trials=200):\n"
        "    hit = 0\n"
        "    for t in range(trials):\n"
        "        base = 500.0; ps = [base*(1+rng.normal(0,0.02)) for _ in range(4)] + [base*(1+true_pct)*(1+rng.normal(0,0.02))]\n"
        "        its = [D.ItemRow(i+1, 1, 'oil', date(2024,1,1)+timedelta(days=30*i), p) for i, p in enumerate(ps)]\n"
        "        hit += bool(D.price_creep(its, min_increase=thr))\n"
        "    return hit/trials\n"
        "grid = pd.DataFrame({f'min_increase={thr:.0%}': {f'true +{p:.0%}': creep_hit(p, thr) for p in (0.0, 0.05, 0.10, 0.15, 0.30)} for thr in (0.05, 0.08, 0.10, 0.15)})\n"
        "grid"
    ),
    md(
        "The 5% rows show why 10% is the default: at +0% the detector must stay quiet (false alarms from "
        "2% noise appear below ~8%), while real +15% and +30% increases are caught essentially always.\n\n"
        "## Decisions\n\n"
        "| Problem | Method in production | Why |\n|---|---|---|\n"
        "| Exact duplicate | same file hash / same vendor + invoice number | deterministic, zero false positives |\n"
        "| Near duplicate | same vendor + amount, dates within 3 days | catches re-keyed copies |\n"
        "| Image duplicate | pHash Hamming <= 6 bits | all re-photographed copies caught; ~1.4% of pairs of *different* synthetic invoices also fall within 6 bits (similar templates), so this is the weakest flag and has `low` severity |\n"
        "| Unusual amount | per-vendor robust z (median/MAD, log) **+** IsolationForest, merged | section 3: robust to masking; forest covers tax/size combos |\n"
        "| Price creep | latest unit price >= 10% above the earlier median (>= 3 observations) | section 5 |\n"
    ),
]

nb.metadata["kernelspec"] = {"name": "docsense", "display_name": "docsense", "language": "python"}
client = NotebookClient(nb, timeout=600, kernel_name="docsense", resources={"metadata": {"path": str(HERE)}})
client.execute()
out = HERE / "02_anomaly_methods.ipynb"
nbf.write(nb, out)
print("wrote", out)
