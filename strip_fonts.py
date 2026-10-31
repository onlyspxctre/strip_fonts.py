#!/usr/bin/env python3
"""Aggressively subset fonts, keeping English/Latin text and common symbols.

Usage:
    python3 strip_fonts.py fonts/Regular.ttc fonts/Bold.ttc
    python3 strip_fonts.py fonts/Regular.ttf --output stripped

Requires Python 3.9+ and fontTools (pip install fonttools).
WOFF2 also requires Brotli (pip install 'fonttools[woff]').
Only standard-width Regular (400), Italic (400), Bold (700), and Bold Italic
(700) faces survive. Oblique, other weights/widths, and variable fonts are excluded.
TTC/OTC inputs are repackaged as collections containing only surviving faces.
The originals are never edited. By default, outputs go beside each input
with '-stripped' added to the filename; --output selects an output directory.
This is a Unicode-range policy, not automatic language detection. It keeps
Latin-1 (including accented letters used in English loanwords), combining
marks, punctuation, currencies, math, arrows, and common technical symbols.
It does not retain other scripts, CJK punctuation, or emoji by default.

Ligature and alternate substitution features are removed. Default character
shapes, kerning/mark positioning, and required composite components are kept.
Unused glyphs and layout rules are pruned by the FontTools subsetter, rather
than keeping every unencoded glyph. Visually check outputs before installing.
Check your font license before modifying or redistributing a font.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile


FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2", ".ttc", ".otc"}
KEEP_RANGES = (
    (0x0020, 0x007E),  # Printable ASCII: English, digits, basic symbols
    (0x00A0, 0x00FF),  # Latin-1: accents, currency, fractions, punctuation
    (0x0300, 0x036F),  # Combining diacritics
    (0x2000, 0x206F),  # General punctuation and formatting characters
    (0x2070, 0x209F),  # Superscripts and subscripts
    (0x20A0, 0x20CF),  # Currency symbols
    (0x2100, 0x214F),  # Letterlike symbols
    (0x2150, 0x218F),  # Fractions and Roman numerals
    (0x2190, 0x21FF),  # Arrows
    (0x2200, 0x22FF),  # Mathematical operators
    (0x2300, 0x23FF),  # Miscellaneous technical symbols
    (0x2400, 0x243F),  # Control pictures
    (0x2460, 0x24FF),  # Enclosed alphanumerics
    (0x2500, 0x259F),  # Box drawing and block elements
    (0x25A0, 0x25FF),  # Geometric shapes
    (0x2600, 0x26FF),  # Miscellaneous symbols (some have emoji presentation)
    (0x2700, 0x27BF),  # Dingbats
    (0x27C0, 0x27EF),  # Miscellaneous mathematical symbols-A
    (0x27F0, 0x27FF),  # Supplemental arrows-A
    (0x2900, 0x297F),  # Supplemental arrows-B
    (0x2980, 0x29FF),  # Miscellaneous mathematical symbols-B
    (0x2A00, 0x2AFF),  # Supplemental mathematical operators
    (0x2B00, 0x2BFF),  # Miscellaneous symbols and arrows
    (0xFE00, 0xFE0F),  # Variation selectors, if encoded as glyphs
    (0xFFFD, 0xFFFD),  # Replacement character
)


def parse_range(value):
    """Accept e.g. U+0100-U+017F, 0100-017F, or U+20AC."""
    try:
        parts = value.upper().replace("U+", "").split("-")
        if len(parts) not in (1, 2):
            raise ValueError
        low = int(parts[0], 16)
        high = int(parts[-1], 16)
        if not 0 <= low <= high <= 0x10FFFF:
            raise ValueError
        return low, high
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid Unicode range: {value!r}")


def strip_font(source, target, ranges):
    from fontTools import subset
    from fontTools.ttLib import TTFont

    temporary = None
    with TTFont(str(source)) as font:
        before = len(font.getGlyphOrder())
        codes = {
            code for table in font['cmap'].tables if table.isUnicode()
            for code in table.cmap
            if any(low <= code <= high for low, high in ranges)
        }
        # No GSUB: retain default cmap designs, not ligature/alternate outputs.
        # Remove older substitution mechanisms too, if present.
        for tag in ('GSUB', 'morx', 'mort', 'Silf'):
            if tag in font:
                del font[tag]
        options = subset.Options()
        options.layout_features = ['kern', 'mark', 'mkmk']
        options.notdef_glyph = True
        options.notdef_outline = True
        options.recommended_glyphs = True
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=codes)
        subsetter.subset(font)
        after = len(font.getGlyphOrder())
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, temporary = tempfile.mkstemp(
                prefix='.stripped-', suffix=target.suffix, dir=str(target.parent)
            )
            os.close(fd)
            font.save(temporary)
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        return before, after


def selected_style(font):
    """Use OS/2 metadata plus style names to distinguish italic from oblique."""
    import re

    if "fvar" in font:
        return None  # Do not silently collapse variable fonts to a default instance.
    if "OS/2" not in font:
        raise ValueError("Missing OS/2 table; cannot safely classify face")
    os2 = font["OS/2"]
    names = font["name"]
    style = " ".join(names.getDebugName(i) or "" for i in (2, 17))
    words = set(re.findall(r"[a-z]+", style.lower()))
    if os2.usWidthClass != 5 or words & {"extended", "expanded", "condensed", "narrow", "oblique", "slanted"}:
        return None
    if os2.fsSelection & (1 << 9):  # Explicit OBLIQUE flag
        return None
    italic = bool(os2.fsSelection & 1 or font["head"].macStyle & 2 or "italic" in words)
    # A slanted face without an italic designation is not treated as italic.
    if not italic and "post" in font and font["post"].italicAngle:
        return None
    if os2.usWeightClass == 400:
        return "Italic" if italic else "Regular"
    if os2.usWeightClass == 700:
        return "Bold Italic" if italic else "Bold"
    return None


def process_file(source, target, ranges):
    from fontTools.ttLib import TTCollection, TTFont

    is_collection = source.suffix.lower() in {".ttc", ".otc"}
    container = TTCollection(str(source)) if is_collection else TTFont(str(source))
    try:
        fonts = container.fonts if is_collection else [container]
        selected = []
        for index, font in enumerate(fonts):
            style = selected_style(font)
            label = font["name"].getDebugName(4) or f"Face {index + 1}"
            print(f"  {'KEEP ' + style if style else 'DROP'}: {label}")
            if style:
                selected.append(index)
        if not selected:
            print(f"SKIP {source}: no Regular, Italic, Bold, or Bold Italic faces matched")
            return

        if not is_collection:
            before, after = strip_font(source, target, ranges)
            print(f"  {before} -> {after} glyphs; saved {target}")
            return

        # Extract faces by index, avoiding ambiguous collection face names.
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".strip-fonts-", dir=target.parent) as work:
            work = Path(work)
            output = TTCollection()
            try:
                for index in selected:
                    font = fonts[index]
                    suffix = ".otf" if font.sfntVersion == "OTTO" else ".ttf"
                    extracted = work / f"face{index}{suffix}"
                    stripped = work / f"face{index}-stripped{suffix}"
                    font.save(str(extracted))
                    before, after = strip_font(extracted, stripped, ranges)
                    print(f"  Face {index + 1}: {before} -> {after} glyphs")
                    output.fonts.append(TTFont(str(stripped)))
                packed = work / ("packed" + target.suffix)
                output.save(str(packed), shareTables=True)
                os.replace(packed, target)
                print(f"Saved {target} ({len(output.fonts)} faces)")
            finally:
                output.close()
    finally:
        container.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", type=Path, nargs="+", help="Individual font file paths")
    parser.add_argument("-o", "--output", type=Path,
                        help="Output directory (default: beside each input)")
    parser.add_argument("--keep-range", type=parse_range, action="append", default=[],
                        metavar="HEX[-HEX]", help="Additional Unicode range; repeatable")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace existing output files (never input files)")
    args = parser.parse_args()
    sources = list(dict.fromkeys(path.expanduser().resolve() for path in args.inputs))
    for source in sources:
        if not source.is_file() or source.suffix.lower() not in FONT_EXTENSIONS:
            parser.error(f"Not a supported font file: {source}")
    output_dir = args.output.expanduser().resolve() if args.output else None
    jobs = [(source, (output_dir or source.parent) /
             (source.stem + "-stripped" + source.suffix)) for source in sources]
    targets = [target for _, target in jobs]
    if len(set(targets)) != len(targets):
        parser.error("Inputs have colliding output names; use separate output directories")
    for target in targets:
        if target.resolve() in sources or target.is_symlink():
            parser.error(f"Unsafe output path (input file or symlink): {target}")

    # Delay imports so --help works without these dependencies.
    try:
        import fontTools.subset  # noqa: F401
    except ImportError:
        parser.exit(2, "FontTools is required: python3 -m pip install fonttools\n"
                    "Or on Debian/Ubuntu: sudo apt install python3-fonttools\n")
    ranges = KEEP_RANGES + tuple(args.keep_range)
    failures = 0
    for source, target in jobs:
        if target.exists() and not args.overwrite:
            print(f"SKIP {target} (already exists; use --overwrite)")
            continue
        try:
            print(f"Processing {source}")
            process_file(source, target, ranges)
            if target.exists():
                before, after = source.stat().st_size, target.stat().st_size
                print(f"  Size: {before / 1048576:.2f} -> {after / 1048576:.2f} MiB "
                      f"({100 * (1 - after / before):.1f}% smaller)")
        except Exception as exc:
            failures += 1
            print(f"ERROR {source}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
