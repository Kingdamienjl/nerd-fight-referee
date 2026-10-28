#!/usr/bin/env python3
"""H1 cleanup analysis: YAML-compose candidate files, find scalars containing
the H1 footer sentence, record enclosing sequence-item spans + full values.
Usage: analyze.py <candidate_list_file> <out_json>"""
import json
import sys

import yaml
from yaml import nodes

H1 = "You can judge a person's power by their feats"
RT = "It is possible to add Respect Thread links"


def node_end_line(node):
    """Max 0-based end line of a node subtree."""
    end = node.end_mark.line
    if isinstance(node, nodes.MappingNode):
        for k, v in node.value:
            end = max(end, node_end_line(k), node_end_line(v))
    elif isinstance(node, nodes.SequenceNode):
        for item in node.value:
            end = max(end, node_end_line(item))
    return end


def walk(node, stack, hits):
    """stack: list of (parent_node, key_or_index, child_node) frames."""
    if isinstance(node, nodes.ScalarNode):
        if H1 in (node.value or ""):
            hits.append((list(stack), node))
        return
    if isinstance(node, nodes.SequenceNode):
        for i, item in enumerate(node.value):
            stack.append((node, i, item))
            walk(item, stack, hits)
            stack.pop()
    elif isinstance(node, nodes.MappingNode):
        for k, v in node.value:
            key = k.value if isinstance(k, nodes.ScalarNode) else None
            stack.append((node, key, v))
            walk(v, stack, hits)
            stack.pop()


def main():
    cand_file, out_file = sys.argv[1], sys.argv[2]
    with open(cand_file) as f:
        candidates = [line.strip() for line in f if line.strip()]
    manifest = {"files": {}, "failures": [], "rt_only": []}
    for path in candidates:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            manifest["failures"].append({"file": path, "error": str(e)})
            continue
        try:
            docs = list(yaml.compose_all(text))
        except yaml.YAMLError as e:
            manifest["failures"].append({"file": path, "error": str(e)[:200]})
            continue
        file_items = {}  # (start_line, end_line) -> item record
        rt_only_hits = 0
        for doc in docs:
            if doc is None:
                continue
            hits = []
            walk(doc, [], hits)
            for stack, scalar in hits:
                # find nearest enclosing sequence-item mapping
                item_node = None
                item_key = None
                path_keys = []
                for parent, key, child in stack:
                    if isinstance(parent, nodes.MappingNode) and key is not None:
                        path_keys.append(key)
                for parent, key, child in reversed(stack):
                    if isinstance(parent, nodes.SequenceNode) and isinstance(
                        child, nodes.MappingNode
                    ):
                        item_node = child
                        break
                # scalar's own key: last mapping key in stack
                scalar_key = None
                for parent, key, child in reversed(stack):
                    if isinstance(parent, nodes.MappingNode):
                        scalar_key = key
                        break
                if item_node is not None:
                    span = (item_node.start_mark.line, node_end_line(item_node))
                    rec = file_items.setdefault(
                        span,
                        {
                            "start_line_1b": span[0] + 1,
                            "end_line_1b": span[1] + 1,
                            "path": path_keys,
                            "scalars": [],
                        },
                    )
                    rec["scalars"].append(
                        {
                            "key": scalar_key,
                            "value": scalar.value,
                            "rt_present": RT in (scalar.value or ""),
                        }
                    )
                else:
                    file_items.setdefault(
                        ("noscope", scalar.start_mark.line),
                        {
                            "start_line_1b": scalar.start_mark.line + 1,
                            "end_line_1b": scalar.end_mark.line + 1,
                            "path": path_keys,
                            "scalars": [
                                {
                                    "key": scalar_key,
                                    "value": scalar.value,
                                    "rt_present": RT in (scalar.value or ""),
                                }
                            ],
                            "no_sequence_item": True,
                        },
                    )
            # RT-only scalars (no H1) in this doc
            rt_hits = []
            walk_rt_only = []

            def walk_rt(n):
                if isinstance(n, nodes.ScalarNode):
                    if RT in (n.value or "") and H1 not in (n.value or ""):
                        rt_hits.append(n.value)
                    return
                if isinstance(n, nodes.SequenceNode):
                    for it in n.value:
                        walk_rt(it)
                elif isinstance(n, nodes.MappingNode):
                    for k, v in n.value:
                        walk_rt(v)

            walk_rt(doc)
            rt_only_hits += len(rt_hits)
        if file_items:
            manifest["files"][path] = {
                "items": sorted(file_items.values(), key=lambda r: r["start_line_1b"]),
                "occurrences": sum(
                    len(it["scalars"]) for it in file_items.values()
                ),
            }
        if rt_only_hits:
            manifest["rt_only"].append({"file": path, "count": rt_only_hits})
    with open(out_file, "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    nfiles = len(manifest["files"])
    nitems = sum(len(v["items"]) for v in manifest["files"].values())
    nocc = sum(v["occurrences"] for v in manifest["files"].values())
    print(f"files_with_h1={nfiles} items={nitems} occurrences={nocc} "
          f"failures={len(manifest['failures'])} "
          f"rt_only_files={len(manifest['rt_only'])}")


if __name__ == "__main__":
    main()
