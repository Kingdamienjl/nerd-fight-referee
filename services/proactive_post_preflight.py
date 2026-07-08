from pathlib import Path 
import re, json 

ROOT = Path(__file__).resolve().parents[1] 
HINTS = ROOT / "config" / "proactive_franchise_hints.json" 
OUTBOX = ROOT / "harvest" / "promotion_outbox" 
REPORT = ROOT / "reports" / "missing_proactive_franchise_names.txt" 

def norm(s): 
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip() 

def strip_franchise(name): 
    return re.sub(r"\s*\([^)]*\)\s*", "", str(name or "")).strip() 

def main(): 
    hints = {} 
    if HINTS.exists(): 
        hints = json.loads(HINTS.read_text(errors="ignore")) 

    missing = [] 
    candidates = sorted(OUTBOX.glob("*.md")) if OUTBOX.exists() else [] 

    for p in candidates[-300:]: 
        text = p.read_text(errors="ignore") 
        for line in text.splitlines(): 
            if " VS " not in line: 
                continue 
            left, right = [x.strip() for x in line.split(" VS ", 1)] 
            for name in [left, right]: 
                clean = strip_franchise(name) 
                if not clean: 
                    continue 
                if "(" not in name and norm(clean) not in hints: 
                    missing.append(clean) 

    missing = sorted(set(missing)) 
    REPORT.parent.mkdir(parents=True, exist_ok=True) 
    REPORT.write_text("\n".join(missing), encoding="utf-8") 

    print(f"missing_franchise_names={len(missing)}") 
    print(f"report={REPORT}") 
    for item in missing[:80]: 
        print(item) 

if __name__ == "__main__": 
    main() 
