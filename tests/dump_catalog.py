"""Dev-only helper: dump the catalog so the browser suite reads real data.

    python3 tests/dump_catalog.py   # writes tests/catalog.json

Kept separate from the Playwright specs because the browser cannot import
Python; CI regenerates it before the browser job runs.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import templates  # noqa: E402


def main():
    rows = []
    for entry in templates.entries():
        for example in entry["examples"]:
            rows.append({
                "typeId": entry["typeId"],
                "label": entry["label"],
                "purpose": example["purpose"],
                "shows": example.get("shows"),
                "minElements": example.get("minElements", 3),
                "source": example["source"],
            })
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=1)
    print("wrote %s (%d examples)" % (target, len(rows)))


if __name__ == "__main__":
    main()
