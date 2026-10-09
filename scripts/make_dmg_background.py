"""Draw the installer window's background (packaging/dmg_background.tiff).

GEOMETRY CONTRACT with packaging/dmg_settings.py (the same one MailRepo's
installer uses, 20 points higher): window 540x320, icon size 100, app icon
centred at (140, 105), Applications alias at (400, 105), both measured from
the TOP left as Finder does. The arrow is drawn between those two slots:
move one, move both. Finder's own chrome eats roughly the bottom 60 points
of the window, more when the reader has the path bar switched on, so
nothing readable sits lower than y = 240. (1.5.x had everything 20 points
lower: an empty band on top and the hint line crowding the path bar.)

Drawn with AppKit at 1x and 2x and packed into one multi-resolution TIFF
with tiffutil (ships with macOS), so it is sharp on a Retina screen.

Usage:  ./venv/bin/python scripts/make_dmg_background.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from AppKit import (
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSCalibratedRGBColorSpace,
    NSCenterTextAlignment,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSFontWeightRegular,
    NSFontWeightSemibold,
    NSForegroundColorAttributeName,
    NSGradient,
    NSGraphicsContext,
    NSMakeRect,
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
    NSString,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging" / "dmg_background.tiff"

WIDTH, HEIGHT = 540, 320
SLOT_Y = 105            # from the top, as in dmg_settings.py
APP_X, APPLICATIONS_X = 140, 400

CAPTION = "Drag Gnomon to Applications to install"
HINT = "Then open it. Right-click the clock for options and Quit."


def srgb(hex_colour: str):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)


PAPER = srgb("#FAF7F0")   # --surface
INK = srgb("#1D1B17")     # --ink
MUTED = srgb("#6B665C")
ACCENT = srgb("#24549A")  # --accent, the blue of the icon's shadow


def up(y_from_top: float) -> float:
    """Finder measures from the top; AppKit draws from the bottom."""
    return HEIGHT - y_from_top


def draw() -> None:
    NSGradient.alloc().initWithStartingColor_endingColor_(
        srgb("#FFFFFF"), PAPER
    ).drawInRect_angle_(NSMakeRect(0, 0, WIDTH, HEIGHT), -90)

    # Arrow between the slots (the 100pt icons span x 90..190 and 350..450).
    y = up(SLOT_Y)
    ACCENT.setStroke()
    ACCENT.setFill()
    shaft = NSBezierPath.bezierPath()
    shaft.setLineWidth_(7)
    shaft.setLineCapStyle_(1)  # round
    shaft.moveToPoint_((APP_X + 75, y))
    shaft.lineToPoint_((APPLICATIONS_X - 92, y))
    shaft.stroke()
    head = NSBezierPath.bezierPath()
    head.moveToPoint_((APPLICATIONS_X - 72, y))
    head.lineToPoint_((APPLICATIONS_X - 98, y + 16))
    head.lineToPoint_((APPLICATIONS_X - 98, y - 16))
    head.closePath()
    head.fill()

    centred = NSMutableParagraphStyle.alloc().init()
    centred.setAlignment_(NSCenterTextAlignment)

    def line(text, y_from_top, size, weight, colour):
        NSString.stringWithString_(text).drawInRect_withAttributes_(
            NSMakeRect(0, up(y_from_top) - size * 0.4, WIDTH, size * 1.4),
            {
                NSFontAttributeName: NSFont.systemFontOfSize_weight_(size, weight),
                NSForegroundColorAttributeName: colour,
                NSParagraphStyleAttributeName: centred,
            },
        )

    line(CAPTION, 208, 16, NSFontWeightSemibold, INK)
    line(HINT, 232, 12, NSFontWeightRegular, MUTED)


def render(scale: int) -> bytes:
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, WIDTH * scale, HEIGHT * scale, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )
    # Size in points: drawing coordinates stay 540x320 at either scale, and
    # the 2x image is tagged 144 dpi, which is how tiffutil pairs the two.
    rep.setSize_((WIDTH, HEIGHT))
    context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(context)
    draw()
    NSGraphicsContext.restoreGraphicsState()
    return bytes(rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None))


def run() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        one, two = Path(tmp) / "bg.png", Path(tmp) / "bg@2x.png"
        one.write_bytes(render(1))
        two.write_bytes(render(2))
        subprocess.run(
            ["tiffutil", "-cathidpicheck", str(one), str(two), "-out", str(OUT)],
            check=True, capture_output=True,
        )
        (OUT.parent / "dmg_background.png").write_bytes(two.read_bytes())  # for looking at
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
