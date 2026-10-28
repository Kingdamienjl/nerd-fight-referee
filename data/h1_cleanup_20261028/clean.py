#!/usr/bin/env python3
"""H1 cleanup: delete footer-debris items from snapshotted files only.
Skip rules (brief): provenance notes + entangled values stay untouched.
Span verification: each debris span must still contain the H1 sentence in
the file's current raw text, else the whole file is skipped as CHANGED.
Usage: clean.py <analysis.json> <results.json>"""
import json
import os
import re
import sys

H1 = "You can judge a person's power by their feats"

ENTANGLED_PREFIXES = [
    "Standard Human Weakness.",
    "Gets sensitive around the topic of his master",
    "Quite cocky and arrogant",
    "Is extremely curious, cocky and arrogant",
]
ENTANGLED_SUBSTRINGS = ["SCP-2747", "tsutsuki"]


def norm(val):
    return re.sub(r"\s+", " ", val).strip()


def scalar_skipped(key, value):
    if key == "note":
        return "provenance note (audit history, not content)"
    nv = norm(value)
    for p in ENTANGLED_PREFIXES:
        if nv.startswith(p):
            return f"entangled with legitimate content (prefix {p!r})"
    for s in ENTANGLED_SUBSTRINGS:
        if s in nv:
            return f"entangled with legitimate content (contains {s!r})"
    return None


def main():
    analysis_file, results_file = sys.argv[1], sys.argv[2]
    m = json.load(open(analysis_file))
    results = {"files": {}, "changed_skipped": []}
    tot_debris_items = tot_debris_occ = 0
    tot_skip_items = tot_skip_occ = 0
    for path, v in sorted(m["files"].items()):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            results["changed_skipped"].append({"file": path, "reason": str(e)})
            continue
        debris_spans = []
        skipped = []
        for it in v["items"]:
            reasons = []
            for s in it["scalars"]:
                r = scalar_skipped(s["key"], s["value"])
                if r:
                    reasons.append(r)
            if reasons:
                skipped.append(
                    {
                        "start_line_1b": it["start_line_1b"],
                        "end_line_1b": it["end_line_1b"],
                        "path": it["path"],
                        "reasons": sorted(set(reasons)),
                        "scalar_keys": [s["key"] for s in it["scalars"]],
                        "value_preview": norm(it["scalars"][0]["value"])[:160],
                    }
                )
            else:
                debris_spans.append((it["start_line_1b"], it["end_line_1b"]))
        # verify debris spans still contain H1 in current raw text
        # (normalize whitespace: YAML folds wrapped scalar lines, so the
        # sentence may span lines with newlines instead of spaces)
        changed = False
        for s1, e1 in debris_spans:
            chunk = " ".join(
                "".join(lines[s1 - 1 : e1]).replace("''", "'").split()
            )
            if H1 not in chunk:
                changed = True
                break
        if changed:
            results["changed_skipped"].append(
                {"file": path, "reason": "span verification failed (file changed since analysis)"}
            )
            continue
        debris_occ = 0
        for it in v["items"]:
            if not any(
                scalar_skipped(s["key"], s["value"]) for s in it["scalars"]
            ):
                debris_occ += len(it["scalars"])
        skip_occ = sum(len(it["scalars"]) for it in v["items"]) - debris_occ
        if debris_spans:
            keep = [True] * len(lines)
            for s1, e1 in debris_spans:
                for i in range(s1 - 1, e1):
                    keep[i] = False
            new_lines = [ln for ln, k in zip(lines, keep) if k]
            tmp = path + ".h1clean_tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            os.replace(tmp, path)
        results["files"][path] = {
            "debris_items": len(debris_spans),
            "debris_occ": debris_occ,
            "skipped_items": skipped,
            "skip_occ": skip_occ,
        }
        tot_debris_items += len(debris_spans)
        tot_debris_occ += debris_occ
        tot_skip_items += len(skipped)
        tot_skip_occ += skip_occ
    with open(results_file, "w") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    print(
        f"cleaned_files={len(results['files'])} debris_items={tot_debris_items} "
        f"debris_occ={tot_debris_occ} skipped_items={tot_skip_items} "
        f"skipped_occ={tot_skip_occ} changed_skipped_files={len(results['changed_skipped'])}"
    )
    for c in results["changed_skipped"]:
        print("CHANGED-SKIP:", c)


if __name__ == "__main__":
    main()
