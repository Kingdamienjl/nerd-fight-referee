import json
actual=json.load(open("/app/data/recovery_sample50n_actual.json"))
expected=json.load(open("/app/data/recovery_sample50n_expected.json"))
out=[]
for rel in ["profiles/needs_review/game/castlevania/isaac.yaml","profiles/needs_review/game/destiny/oryx.yaml","profiles/needs_review/game/elden-ring/maliketh.yaml"]:
    out.append("="*20+" "+rel)
    a=actual[rel]; e=expected[rel]
    out.append("PS:")
    for k,v in (a.get("power_scale") or {}).items():
        t = v.get("text") if isinstance(v,dict) else v
        bt = ((e.get("power_scale") or {}).get(k) or {})
        bt = bt.get("text") if isinstance(bt,dict) else bt
        if t and t!=bt: out.append(f"  NEW stat {k}: {t!r}")
    for sec in ("abilities","weaknesses","equipment"):
        bmap=set()
        for it in (e.get(sec) or []):
            if isinstance(it,dict): bmap.add(str(it.get("name") or ""))
        for it in (a.get(sec) or []):
            if isinstance(it,dict) and str(it.get("name") or "") not in bmap:
                out.append(f"  NEW [{sec}] N={it.get('name')!r}")
                out.append(f"      D={str(it.get('description') or '')!r}")
    out.append("SRC_TITLES: "+repr([str(s.get("title"))+" | "+str(s.get("url")) for s in (a.get("sources") or []) if isinstance(s,dict)]))
open("/app/data/frag11_20261025/gate50n_dump.txt","w").write("\n".join(out)+"\n")
print("lines", len(out))
