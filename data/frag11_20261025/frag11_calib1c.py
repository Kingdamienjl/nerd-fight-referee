#!/usr/bin/env python3
"""Frag-11 calibration round 1c (read-only): F4 truncation precision
+ F5 vocab dump for embedding.
- word_vocab: whole words with freq>=2 across all item names+descs.
- F4-vocab: short (<120) items whose final token is a non-word that
  is a strict prefix of a longer vocab word.
- F4-head: short items whose final token is a strict prefix of the
  item's head word.
- F4-head-ability: F4-head restricted to ability-word heads.
- Dump the F5 freq>=2 single-token vocab to f5_vocab.json.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

def item_names(prof, sections=("abilities", "weaknesses", "equipment", "resistances", "summons")):
    out = []
    for sec in sections:
        items = prof.get(sec)
        if isinstance(items, dict):
            items = list(items.values())
        for it in items or []:
            if isinstance(it, dict):
                out.append((sec, str(it.get("name") or ""), str(it.get("description") or "")))
    return out

all_words = Counter()
single_token = Counter()
terminal_words = Counter()
items = []
for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    for sec, name, desc in item_names(prof):
        items.append((str(path.relative_to("/app")), sec, name))
        for w in re.findall(r"[A-Za-z]+", name + " " + desc):
            all_words[w.casefold()] += 1
        toks1 = name.strip().rstrip(".:!").split()
        if len(toks1) == 1 and toks1[0][:1].isupper() and toks1[0].isalpha():
            single_token[toks1[0]] += 1
        if sec == "abilities" and name:
            head_part = name.split("(")[0].strip()
            hw = re.findall(r"[A-Za-z]+", head_part)
            if len(hw) >= 2:
                terminal_words[hw[-1].casefold()] += 1

word_vocab = {w for w, c in all_words.items() if c >= 2}
print(f"word_vocab(freq>=2) size={len(word_vocab)} items={len(items)}")
by4 = defaultdict(set)
for w in word_vocab:
    if len(w) >= 6:
        by4[w[:4]].add(w)
f5_vocab = sorted([w for w, c in single_token.items() if c >= 2])
print(f"F5 vocab size={len(f5_vocab)}")
Path("/app/data/frag11_20261025/f5_vocab.json").write_text(json.dumps(f5_vocab))
term100 = {w for w, c in terminal_words.most_common(100)}
ability_oracle = set(w.casefold() for w in f5_vocab) | term100
print(f"ability_oracle size={len(ability_oracle)}")

f4_vocab = []
f4_head = []
f4_head_ability = []
for rel, sec, name in items:
    if len(name) >= 120:
        continue
    toks = re.findall(r"[A-Za-z]+", name)
    if not toks:
        continue
    last = toks[-1].casefold()
    if len(last) < 4:
        continue
    if last not in word_vocab:
        cands = [w for w in by4.get(last[:4], ()) if w.startswith(last) and len(w) >= len(last) + 2]
        if cands:
            same = any(o.casefold().startswith(last) and len(o) >= len(last) + 2 for o in toks[:-1])
            f4_vocab.append((rel, sec, name, last, sorted(cands)[:3], same))
    head = toks[0].casefold()
    if head.startswith(last) and len(head) >= len(last) + 2 and head != last:
        f4_head.append((rel, sec, name, last, head))
        if head in ability_oracle:
            f4_head_ability.append((rel, sec, name, last, head))

print(f"F4-vocab short non-word-prefix finals: n={len(f4_vocab)}")
for r in f4_vocab[:30]:
    print("  F4v:", r[0], r[1], repr(r[2][:120]), "last=", r[3], "exp=", r[4], "same_item_exp=", r[5])
print(f"F4-head short finals prefix-of-head: n={len(f4_head)}")
for r in f4_head[:30]:
    print("  F4h:", r[0], r[1], repr(r[2][:120]), "last=", r[3], "head=", r[4])
print(f"F4-head-ability: n={len(f4_head_ability)}")
for r in f4_head_ability[:30]:
    print("  F4ha:", r[0], r[1], repr(r[2][:120]), "last=", r[3], "head=", r[4])
print("CALIB1C DONE")
