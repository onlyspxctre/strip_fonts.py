# Font stripping tool

`strip_fonts.py` reduces font size for English terminal and development use. It keeps default character designs, common symbols, and selected faces while removing ligatures, optional stylistic alternatives, and unwanted character coverage.

The implementation uses **FontTools**, not FontForge.

## Requirements

Python 3.9+ and FontTools:

```bash
python3 -m pip install fonttools
```

For WOFF2 support:

```bash
python3 -m pip install 'fonttools[woff]'
```

## Usage

Pass individual font files, not a directory. Supported extensions: `.ttf`, `.otf`, `.woff`, `.woff2`, `.ttc`, and `.otc`.

```bash
python3 strip_fonts.py \
  fonts/SGr-IosevkaTerm-Regular.ttc \
  fonts/SGr-IosevkaTerm-Bold.ttc \
  --output ./stripped
```

Without `--output`, files are written beside their inputs with `-stripped` added to the filename. Originals are not edited. Existing outputs are skipped unless `--overwrite` is supplied.

```bash
# Replace previously generated outputs
python3 strip_fonts.py fonts/*.ttc --output ./stripped --overwrite

# Also retain Latin Extended-A; --keep-range can be repeated
python3 strip_fonts.py font.ttf --keep-range U+0100-U+017F

python3 strip_fonts.py --help
```

## What survives

- **Faces:** standard-width Regular and Italic at weight 400; Bold and Bold Italic at weight 700.
- **Characters:** printable ASCII, Latin-1, combining diacritics, punctuation, currencies, math, arrows, box drawing, block elements, and other common symbol ranges.
- **Rendering data:** default character shapes, required composite components, kerning, and mark positioning where present.

Oblique faces, other weights, nonstandard widths, and variable fonts are excluded. Files with no matching faces are skipped. The character policy uses Unicode ranges, not automatic language detection; some non-English characters remain in the retained ranges.

Private-use icons, including Nerd Font and Powerline glyphs, are **not retained by default**. Patch after stripping, or explicitly include the ranges you need. General emoji coverage is not retained, although some kept symbol ranges contain emoji-capable characters.

## How it works

1. **Validate inputs:** resolve paths, reject unsupported files, and check for output collisions or unsafe output paths.
2. **Select faces:** inspect font metadata and style names to retain only Regular, Italic, Bold, and Bold Italic at standard width.
3. **Select characters:** intersect the font's Unicode mappings with `KEEP_RANGES` plus any `--keep-range` arguments.
4. **Remove substitutions:** discard OpenType and legacy substitution tables, removing ligature and optional alternate-design behavior. This removes all substitution features, so it is unsuitable for scripts requiring contextual shaping.
5. **Subset glyphs:** FontTools removes unused glyphs and layout rules while retaining dependencies such as the components of accented letters.
6. **Write the result:** save standalone fonts directly, or rebuild collections from retained faces. Completed outputs replace their destination only after writing succeeds. Print glyph counts and file-size reductions.

Collection inputs remain collections—even if only one face survives. Separate inputs are not merged. For the Iosevka collections used here:

| Input | Retained faces |
| --- | --- |
| Regular TTC | Regular, Italic |
| Bold TTC | Bold, Bold Italic |

A TTC is a collection container, not a standalone TTF. Renaming its extension does not convert it; extract its faces before using tools that accept only standalone fonts, such as some font patchers.

### Code map

| Function | Responsibility |
| --- | --- |
| `parse_range()` | Parse a hexadecimal Unicode code point or inclusive range. |
| `selected_style()` | Classify a face from its metadata; return a retained style or `None`. |
| `strip_font()` | Subset one standalone face and save it safely; return glyph counts. |
| `process_file()` | Filter faces, strip them, and rebuild a collection when needed. |
| `main()` | Parse arguments, validate paths, run jobs, and report results/errors. |

Change `KEEP_RANGES` for character coverage, `selected_style()` for face selection, and `strip_font()` for subsetting behavior.

## Caveats and license

Visually check generated fonts in your terminal/editor before installing them. The tool deliberately sacrifices typography features for size, and missing characters may render through a fallback font or as missing-glyph boxes.

The script is licensed under the [MIT License](LICENSE). This does **not** change the licenses of input or output fonts. Check each font's modification, naming, and redistribution requirements separately.
