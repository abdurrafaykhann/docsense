"""Render invoice HTML to an image and read exact region / field / word boxes from the DOM."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from .generator import InvoiceData

TEMPLATE_DIR = Path(__file__).parent / "templates"
CLASSES = ["vendor", "meta", "table", "totals", "other"]  # YOLO class ids 0..4


def _money(v: float, style: str = "plain") -> str:
    s = f"{v:,.2f}"
    return {"plain": s, "rs": f"Rs. {s}", "pkr": f"PKR {s}"}[style]


def _qty(v) -> str:
    return f"{v:g}"


def _fmtdate(iso: str, fmt: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime(fmt)


def make_env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))
    env.filters.update(money=_money, qty=_qty, fmtdate=_fmtdate)
    return env


def render_html(d: InvoiceData, env: Environment | None = None) -> str:
    env = env or make_env()
    style = {**d.style, "urdu": d.style.get("urdu", True)}
    return env.get_template(f"{d.template}.html").render(d=d, s=style)


JS_EXTRACT = """
() => {
  const sx = window.scrollX, sy = window.scrollY;
  const br = document.body.getBoundingClientRect();
  const W = Math.ceil(br.width), H = Math.ceil(br.height + br.top + sy);
  const box = el => { const r = el.getBoundingClientRect();
    return [r.left + sx, r.top + sy, r.right + sx, r.bottom + sy]; };
  const regions = [...document.querySelectorAll('[data-region]')]
    .map(e => ({cls: e.dataset.region, box: box(e)}));
  const fields = {};
  document.querySelectorAll('[data-field]').forEach(e => {
    if (!(e.dataset.field in fields)) fields[e.dataset.field] = box(e); });
  const words = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const re = /\\S+/g; let m;
    while ((m = re.exec(n.nodeValue))) {
      const rg = document.createRange();
      rg.setStart(n, m.index); rg.setEnd(n, m.index + m[0].length);
      const r = rg.getClientRects()[0];
      if (r && r.width > 0) words.push({text: m[0], box: [r.left + sx, r.top + sy, r.right + sx, r.bottom + sy]});
    }
  }
  return {W, H, regions, fields, words};
}
"""


@dataclass
class Rendered:
    image: np.ndarray  # RGB uint8
    regions: list[dict]  # [{cls, bbox:[x0,y0,x1,y1] normalised}]
    fields: dict[str, list[float]]
    words: list[dict]  # [{text, bbox, conf, page}]


def _norm(box, W, H) -> list[float]:
    x0, y0, x1, y1 = box
    c = lambda v: min(1.0, max(0.0, v))  # noqa: E731
    return [round(c(x0 / W), 5), round(c(y0 / H), 5), round(c(x1 / W), 5), round(c(y1 / H), 5)]


class Renderer:
    """Context manager holding one browser; renders many invoices fast."""

    def __init__(self, scale: float = 2.0, channel: str | None = "msedge"):
        self.scale, self.channel = scale, channel
        self.env = make_env()

    def __enter__(self) -> Renderer:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        kwargs = {"channel": self.channel} if self.channel else {}
        self._browser = self._pw.chromium.launch(**kwargs)
        self._ctx = self._browser.new_context(device_scale_factor=self.scale)
        self._page = self._ctx.new_page()
        return self

    def __exit__(self, *exc) -> None:
        self._browser.close()
        self._pw.stop()

    def render(self, d: InvoiceData) -> Rendered:
        page = self._page
        page.set_viewport_size({"width": 900, "height": 600})
        page.set_content(render_html(d, self.env), wait_until="load")
        data = page.evaluate(JS_EXTRACT)
        W, H = data["W"], data["H"]
        # the viewport is wider than narrow receipts: clip to the document body
        png = page.screenshot(full_page=True, clip={"x": 0, "y": 0, "width": W, "height": H})
        img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
        regions = [{"cls": r["cls"], "bbox": _norm(r["box"], W, H)} for r in data["regions"]]
        fields = {k: _norm(v, W, H) for k, v in data["fields"].items()}
        words = [
            {"text": w["text"], "bbox": _norm(w["box"], W, H), "conf": 1.0, "page": 1}
            for w in data["words"]
        ]
        return Rendered(img, regions, fields, words)


def to_yolo_lines(regions: list[dict]) -> list[str]:
    """YOLO txt: 'class cx cy w h' (normalised). Degenerate boxes are dropped."""
    lines = []
    for r in regions:
        x0, y0, x1, y1 = r["bbox"]
        w, h = x1 - x0, y1 - y0
        if w <= 0.005 or h <= 0.002:
            continue
        lines.append(f"{CLASSES.index(r['cls'])} {x0 + w / 2:.6f} {y0 + h / 2:.6f} {w:.6f} {h:.6f}")
    return lines
