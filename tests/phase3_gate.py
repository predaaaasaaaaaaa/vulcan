"""Phase 3 gate — 8 queries across asset types → stamped PNGs → contact sheet.

Run: .venv/bin/python tests/phase3_gate.py
The sheet lands in runs/phase3_gate/contact_sheet.png and MUST be viewed by eye.
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from PIL import Image, ImageDraw

from vulcan.assets.engine import resolve_asset

GATE = [
    {"asset_id": "a01", "type": "photo_cutout", "queries": ["elon musk pointing", "elon musk portrait", "elon musk"]},
    {"asset_id": "a02", "type": "photo_cutout", "queries": ["eiffel tower", "eiffel tower paris", "eiffel tower photo"]},
    {"asset_id": "a03", "type": "photo_cutout", "queries": ["iphone 15 pro", "iphone 15", "apple iphone"]},
    {"asset_id": "a04", "type": "3d_icon", "queries": ["rocket", "rocket launch", "spaceship"]},
    {"asset_id": "a05", "type": "flat_icon", "queries": ["brain", "mind", "intelligence"]},
    {"asset_id": "a06", "type": "logo", "queries": ["github", "github logo", "github icon"]},
    {"asset_id": "a07", "type": "emoji", "queries": ["💰", "money bag", "money"]},
    {"asset_id": "a08", "type": "screenshot", "queries": ["stripe.com homepage", "stripe website", "stripe dashboard"]},
]

OUT = Path("runs/phase3_gate")
CELL = 360


def build_sheet(results: list[dict]) -> Path:
    cols, rows = 4, 2
    sheet = Image.new("RGB", (cols * CELL, rows * CELL + 40 * rows), (16, 16, 18))
    draw = ImageDraw.Draw(sheet)
    for i, a in enumerate(results):
        cx, cy = (i % cols) * CELL, (i // cols) * (CELL + 40)
        label = f"{a['asset_id']} {a['type']} score={a.get('score')}"
        if a["status"] == "validated":
            img = Image.open(a["path"]).convert("RGBA")
            img.thumbnail((CELL - 20, CELL - 20))
            # checker background to reveal alpha quality
            for ty in range(0, CELL, 24):
                for tx in range(0, CELL, 24):
                    if (tx // 24 + ty // 24) % 2 == 0:
                        draw.rectangle([cx + tx, cy + ty, cx + tx + 24, cy + ty + 24], fill=(28, 28, 32))
            sheet.paste(img, (cx + (CELL - img.width) // 2, cy + (CELL - img.height) // 2), img)
        else:
            draw.text((cx + 20, cy + CELL // 2), "FAILED", fill=(255, 80, 80))
            label += " FAILED"
        draw.text((cx + 8, cy + CELL + 8), label[:52], fill=(240, 240, 240))
    out = OUT / "contact_sheet.png"
    sheet.save(out)
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in GATE:
        asset = {**spec, "path": None, "status": "pending", "score": None}
        resolve_asset(asset, OUT / "assets")
        results.append(asset)
        print(f"{asset['asset_id']} → {asset['status']} score={asset.get('score')} path={asset.get('path')}")
        if asset["status"] != "validated":
            for line in asset.get("_failure_log", [])[-4:]:
                print("   ", line)
    sheet = build_sheet(results)
    (OUT / "results.json").write_text(json.dumps(results, indent=1, default=str))
    ok = sum(1 for a in results if a["status"] == "validated")
    print(f"\n{ok}/8 validated → sheet: {sheet}")
