#!/usr/bin/env python3
"""Encode matched RGB display PNGs with one shared palette below host limits.
Only the published visualization is quantized; original six-band COGs are unchanged.
Called by urban_gee.py after its completed computation; may also run standalone.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
ENCODING = "Indexed PNG: 127 shared RGB colours, no dithering, transparent index 255; spatial grid unchanged"


def main():
    path = DATA / "urban-provenance.json"
    manifest = json.loads(path.read_text())
    if manifest.get("rgbVisualization", {}).get("webEncoding") == ENCODING:
        # Older Pillow versions may truncate a short palette before index 255.
        # Repair only palette storage, never quantize an already-quantized image.
        for name in ["urban-before.png", "urban-after.png"]:
            image = Image.open(DATA / name)
            palette = image.getpalette()
            image.putpalette((palette + [0] * 768)[:768])
            image.save(DATA / name, optimize=True, transparency=255)
            manifest["outputs"][name] = {
                "sha256": hashlib.sha256((DATA / name).read_bytes()).hexdigest(),
                "bytes": (DATA / name).stat().st_size,
            }
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        (ROOT / "raw" / "urban" / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        print("Shared-palette storage verified without repeat quantization.")
        return
    names = ["urban-before.png", "urban-after.png"]
    images = [Image.open(DATA / name).convert("RGBA") for name in names]
    thumbs = []
    for image in images:
        thumb = image.convert("RGB")
        thumb.thumbnail((700, 700))
        thumbs.append(thumb)
    sample = Image.new(
        "RGB", (thumbs[0].width + thumbs[1].width, max(x.height for x in thumbs))
    )
    sample.paste(thumbs[0], (0, 0))
    sample.paste(thumbs[1], (thumbs[0].width, 0))
    palette = sample.quantize(colors=127, method=Image.Quantize.MEDIANCUT)
    for name, image in zip(names, images):
        quantized = image.convert("RGB").quantize(
            palette=palette, dither=Image.Dither.NONE
        )
        quantized.putpalette((palette.getpalette() + [0] * 768)[:768])
        quantized.paste(255, mask=Image.eval(image.getchannel("A"), lambda x: 255 - x))
        quantized.info["transparency"] = 255
        quantized.save(DATA / name, optimize=True)
        if (DATA / name).stat().st_size > 5242880:
            raise RuntimeError(
                "Web PNG still exceeds host file limit; deployment must stop"
            )
        manifest["outputs"][name] = {
            "sha256": hashlib.sha256((DATA / name).read_bytes()).hexdigest(),
            "bytes": (DATA / name).stat().st_size,
        }
    manifest["rgbVisualization"]["webEncoding"] = ENCODING
    manifest["rgbVisualization"]["sharedPaletteRGB"] = palette.getpalette()[: 127 * 3]
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    (ROOT / "raw" / "urban" / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    catalogue_path = DATA / "thematic.json"
    catalogue = json.loads(catalogue_path.read_text())
    entry = next(x for x in catalogue["layers"] if x["id"] == "urban")
    entry["webEncoding"] = ENCODING
    entry[
        "method"
    ] += " Web visualizations use one shared 127-colour indexed PNG palette for both dates; analytical COG values are unchanged."
    catalogue_path.write_text(json.dumps(catalogue, indent=2) + "\n")
    print(
        "Shared-palette display encoding complete:",
        {name: (DATA / name).stat().st_size for name in names},
    )


if __name__ == "__main__":
    main()
