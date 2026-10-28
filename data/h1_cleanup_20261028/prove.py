#!/usr/bin/env python3
"""Prove the cleaner is correct on backup copies: apply the recorded debris
spans to pristine backup copies in scratch, then check (1) YAML still
parses, (2) remaining H1 == skipped count, (3) diff shows ONLY span lines
removed (no additions, deleted count == span total)."""
import json
import subprocess
import sys

import yaml

H1 = "You can judge a person's power by their feats"
analysis = json.load(open(sys.argv[1]))
r1 = json.load(open(sys.argv[2]))
r2 = json.load(open(sys.argv[3]))
cleaned = dict(r1["files"])
cleaned.update(r2["files"])
backup_tar = sys.argv[4]
targets = sys.argv[5:]

for path in targets:
    tar = subprocess.run(["tar", "-xzOf", backup_tar, path],
                         capture_output=True, text=True)
    assert tar.returncode == 0, path
    lines = tar.stdout.splitlines(keepends=True)
    items = analysis["files"][path]["items"]
    skip_starts = {s["start_line_1b"]
                   for s in cleaned[path]["skipped_items"]}
    debris = [(it["start_line_1b"], it["end_line_1b"])
              for it in items if it["start_line_1b"] not in skip_starts]
    keep = [True] * len(lines)
    for s1, e1 in debris:
        for i in range(s1 - 1, e1):
            keep[i] = False
    new = [ln for ln, k in zip(lines, keep) if k]
    new_text = "".join(new)
    # (1) parses?
    try:
        list(yaml.compose_all(new_text))
        parses = True
    except yaml.YAMLError as e:
        parses = False
        print(path, "PARSE FAIL", str(e)[:120])
    # (2) remaining H1 == skipped count?
    import io
    docs = list(yaml.compose_all(new_text))
    remaining = 0
    for doc in docs:
        if doc is None:
            continue
        stack = [doc]
        while stack:
            n = stack.pop()
            if isinstance(n, yaml.nodes.ScalarNode):
                if H1 in (n.value or ""):
                    remaining += 1
            elif isinstance(n, yaml.nodes.SequenceNode):
                stack.extend(n.value)
            elif isinstance(n, yaml.nodes.MappingNode):
                for k, v in n.value:
                    stack.extend([k, v])
    # (3) diff: only deletions, count == span total
    diff = subprocess.run(["diff", "-", "/dev/stdin"],
                          input=tar.stdout, capture_output=True, text=True)
    # do a real diff via temp files instead
    with open("/tmp/h1_verify_orig.yaml", "w") as f:
        f.write(tar.stdout)
    with open("/tmp/h1_verify_new.yaml", "w") as f:
        f.write(new_text)
    d = subprocess.run(["diff", "/tmp/h1_verify_orig.yaml",
                        "/tmp/h1_verify_new.yaml"],
                       capture_output=True, text=True)
    deleted = sum(1 for ln in d.stdout.splitlines() if ln.startswith("<"))
    added = sum(1 for ln in d.stdout.splitlines() if ln.startswith(">"))
    expected = sum(e - s + 1 for s, e in debris)
    print(f"{path}: parses={parses} remaining_H1={remaining} "
          f"expected_skipped={cleaned[path]['skip_occ']} "
          f"deleted={deleted} expected_deleted={expected} added={added}")
