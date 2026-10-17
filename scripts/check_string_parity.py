#!/usr/bin/env python3
"""String parity gate for LogSleuth.

Ensures the shipped locales stay in sync:
  app/src/main/res/values/strings.xml          (English, source of truth)
  app/src/main/res/values-zh-rCN/strings.xml    (Simplified Chinese)
  app/src/main/res/values-ar/strings.xml        (Arabic)

Checks:
  1. Key sets are identical (missing / extra keys both fail).
  2. Positional format arguments match (%1$d, %1$s, …) — same count and
     same positional indices per key, so runtime formatting can never
     crash or silently drop data in one locale.

CI runs this on every branch and PR; it is a merge gate.

Usage:
    python3 scripts/check_string_parity.py [--fix-hint]
Exit codes: 0 = parity, 1 = drift (details printed).
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app" / "src" / "main" / "res"
LOCALES = {
    "default": APP_DIR / "values" / "strings.xml",
    "zh-rCN": APP_DIR / "values-zh-rCN" / "strings.xml",
    "ar": APP_DIR / "values-ar" / "strings.xml",
}

# %1$s, %1$d, %2$02d … (explicitly indexed)
FMT_ARG = re.compile(r"%(\d+)\$[sdf]")
# Bare %s / %d (unindexed — allowed but must match too)
FMT_BARE = re.compile(r"%(?!\d+\$)[sd]")


def load_keys(path: Path) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "resources":
        raise SystemExit(f"{path}: unexpected root element <{root.tag}>")
    keys = {}
    for child in root:
        if child.tag != "string":
            continue
        name = child.get("name")
        if not name:
            raise SystemExit(f"{path}: <string> without a name attribute")
        if name in keys:
            raise SystemExit(f"{path}: duplicate key {name!r}")
        keys[name] = "".join(child.itertext())
    return keys


def fmt_signature(value: str) -> tuple:
    indexed = sorted(int(m) for m in FMT_ARG.findall(value))
    bare = len(FMT_BARE.findall(value))
    return (tuple(indexed), bare)


def main() -> int:
    if "default" not in LOCALES:
        raise SystemExit("internal: 'default' locale must be present")

    data = {}
    for locale, path in LOCALES.items():
        if not path.exists():
            print(f"FAIL: missing strings file for locale {locale}: {path}")
            return 1
        data[locale] = load_keys(path)

    base_locale = "default"
    base = data.pop(base_locale)
    base_keys = set(base)

    failures = []

    for other_locale, other in data.items():
        other_keys = set(other)

        missing = sorted(base_keys - other_keys)
        for key in missing:
            failures.append(
                f"  [{other_locale}] missing key {key!r} (present in {base_locale})"
            )

        extra = sorted(other_keys - base_keys)
        for key in extra:
            failures.append(
                f"  [{other_locale}] extra key {key!r} (not in {base_locale})"
            )

        for key in sorted(base_keys & other_keys):
            sig_base = fmt_signature(base[key])
            sig_other = fmt_signature(other[key])
            if sig_base != sig_other:
                failures.append(
                    f"  [{other_locale}] {key!r}: format args differ — "
                    f"{base_locale}={sig_base}, {other_locale}={sig_other}"
                )

    if failures:
        print(f"String parity drift detected against {base_locale}:")
        for line in failures:
            print(line)
        print("\nFix: add the missing strings (or remove the extra ones) and keep\n"
              "positional format arguments (%1$d …) identical in all files.")
        return 1

    print(
        f"String parity OK: {len(base_keys)} keys match across all "
        f"{len(LOCALES)} locales (format args verified)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
