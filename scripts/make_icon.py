"""Generate Gnomon's app icon (assets/icon.icns).

The mark: a sundial's gnomon — the ink triangle — standing on its dial
line, with the stretch of line its shadow falls on drawn in Daybook's
accent blue. The shadow is the only colour because the shadow is the part
that tells the time. Tile is the portfolio's paper; border is its hairline
rule (same construction as Palestra's barbell).

Drawn with AppKit, which the app already depends on, so there is nothing
extra to install. `iconutil` (ships with macOS) packs the .icns.

Usage:  ./venv/bin/python scripts/make_icon.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from AppKit import (
    NSAffineTransform,
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSCalibratedRGBColorSpace,
    NSColor,
    NSGraphicsContext,
    NSMakeRect,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icon.icns"

GRID = 1024.0  # design grid; origin bottom-left, as AppKit draws


def srgb(hex_colour: str):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)


PAPER = srgb("#FAF7F0")   # --surface
RULE = srgb("#DFD9CC")    # --rule
INK = srgb("#1D1B17")     # --ink
ACCENT = srgb("#24549A")  # --accent


def draw_mark() -> None:
    """The whole icon, on the 1024 grid."""
    # Tile: Apple's icon grid (824pt square, inset 100) with its corner radius.
    tile = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(100, 100, 824, 824), 185, 185
    )
    PAPER.setFill()
    tile.fill()
    RULE.setStroke()
    tile.setLineWidth_(6)
    tile.stroke()

    def bar(x, width, colour):
        colour.setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(x, 322, width, 36), 18, 18
        ).fill()

    bar(236, 430, INK)        # dial line under the gnomon
    bar(630, 158, ACCENT)     # ... and where the shadow falls

    gnomon = NSBezierPath.bezierPath()
    gnomon.moveToPoint_((312, 340))
    gnomon.lineToPoint_((648, 340))
    gnomon.lineToPoint_((648, 706))
    gnomon.closePath()
    gnomon.setLineJoinStyle_(1)  # round joins soften the sharp toe
    INK.setFill()
    INK.setStroke()
    gnomon.setLineWidth_(20)
    gnomon.fill()
    gnomon.stroke()


def render(pixels: int) -> bytes:
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, pixels, pixels, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )
    context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(context)
    scale = NSAffineTransform.transform()
    scale.scaleBy_(pixels / GRID)
    scale.concat()
    draw_mark()
    NSGraphicsContext.restoreGraphicsState()
    return bytes(rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None))


def run() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Gnomon.iconset"
        iconset.mkdir()
        for points in (16, 32, 128, 256, 512):
            (iconset / f"icon_{points}x{points}.png").write_bytes(render(points))
            (iconset / f"icon_{points}x{points}@2x.png").write_bytes(render(points * 2))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT)], check=True)
    # A flat PNG beside it, for READMEs and for looking at.
    (OUT.parent / "icon-512.png").write_bytes(render(512))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
