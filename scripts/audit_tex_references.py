#!/usr/bin/env python3
"""Fail closed on broken internal references and bibliography keys."""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"


def main() -> int:
    tex_files = sorted(PAPER.rglob("*.tex"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in tex_files)
    bib = (PAPER / "references.bib").read_text(encoding="utf-8")

    labels = re.findall(r"\\label\{([^}]+)\}", text)
    referenced = set(
        re.findall(r"\\(?:ref|eqref|autoref)\{([^}]+)\}", text)
    )
    cited = {
        key.strip()
        for group in re.findall(
            r"\\cite(?:p|t|alp|alt|author|year|yearpar)?\{([^}]+)\}", text
        )
        for key in group.split(",")
        if key.strip()
    }
    bib_keys = set(re.findall(r"(?m)^@\w+\s*\{\s*([^,\s]+)\s*,", bib))

    duplicate_labels = sorted(
        label for label, count in Counter(labels).items() if count > 1
    )
    missing_labels = sorted(referenced - set(labels))
    missing_citations = sorted(cited - bib_keys)

    problems = []
    if duplicate_labels:
        problems.append(f"duplicate labels: {', '.join(duplicate_labels)}")
    if missing_labels:
        problems.append(f"undefined references: {', '.join(missing_labels)}")
    if missing_citations:
        problems.append(f"undefined citations: {', '.join(missing_citations)}")

    if problems:
        print("TeX reference audit: FAIL", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print(
        "TeX reference audit: PASS "
        f"({len(labels)} labels, {len(referenced)} referenced labels, "
        f"{len(cited)} citation keys)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
