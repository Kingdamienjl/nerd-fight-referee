from pathlib import Path 
from datetime import datetime 
import json, yaml, shutil, re 

ROOT = Path(__file__).resolve().parents[1] 
QUEUE = ROOT / "harvest" / "profile_refresh_queue" 
DONE = ROOT / "harvest" / "profile_refresh_done" 
BACKUP = ROOT / "backups" / "profile_refresh" 

PLACEHOLDERS = [ 
    "Profile pending source verification", 
    "Basic combat capability", 
    "Curated high-value roster expansion target", 
    "Needs source-backed profile data before a confident win route can be assigned.", 
    "Source verification pending", 
] 

FRANCHISE_HINTS = ROOT / "config" / "proactive_franchise_hints.json" 

def load_yaml(p): 
    try: 
        return yaml.safe_load(p.read_text(errors="ignore")) or {} 
    except Exception: 
        return {} 

def save_yaml(p, data): 
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8") 

def norm(s): 
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip() 

def load_hints(): 
    if not FRANCHISE_HINTS.exists(): 
        return {} 
    try: 
        return json.loads(FRANCHISE_HINTS.read_text(errors="ignore")) 
    except Exception: 
        return {} 

def infer_franchise(profile, path, hints): 
    name = profile.get("name") or path.stem.replace("-", " ") 
    for key in [norm(name), norm(path.stem.replace("-", " "))]: 
        if key in hints: 
            return hints[key] 

    parts = list(path.parts) 
    if "generated" in parts: 
        after = parts[parts.index("generated")+1:-1] 
        ignore = {"mixed", "expansion-seeds", "anime", "comic", "comics", "game", "tv", "tv_movie", "movie", "user-requests", "crossover-icons"} 
        for part in after: 
            if part not in ignore: 
                return part.replace("-", " ").title() 

    return profile.get("franchise") or profile.get("series") or "Unknown" 

def clean_value(v): 
    if isinstance(v, str): 
        for ph in PLACEHOLDERS: 
            v = v.replace(ph, "").strip(" ,;-") 
        return v.strip() 
    if isinstance(v, list): 
        cleaned = [] 
        for item in v: 
            c = clean_value(item) 
            if c and c not in cleaned: 
                cleaned.append(c) 
        return cleaned 
    if isinstance(v, dict): 
        return {k: clean_value(val) for k, val in v.items()} 
    return v 

def refresh_profile(profile_path, reason, hints):
    p = Path(profile_path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists(): 
        return False, "missing_profile" 

    data = load_yaml(p) 
    if not data: 
        return False, "empty_or_bad_yaml" 

    raw_before = p.read_text(errors="ignore") 
    changed = False 

    name = data.get("name") or p.stem.replace("-", " ").title() 
    franchise = infer_franchise(data, p, hints) 

    for k, v in list(data.items()): 
        cleaned = clean_value(v) 
        if cleaned != v: 
            data[k] = cleaned 
            changed = True 

    if not data.get("name"): 
        data["name"] = name 
        changed = True 

    if not data.get("franchise") or str(data.get("franchise")).lower() in {"unknown", "mixed", "none", "null"}: 
        data["franchise"] = franchise 
        changed = True 

    if not data.get("weapon_power") or "pending" in str(data.get("weapon_power")).lower(): 
        data["weapon_power"] = f"{name}'s signature abilities and core combat kit" 
        changed = True 

    if not data.get("key_tools") or any("basic combat" in str(x).lower() for x in (data.get("key_tools") if isinstance(data.get("key_tools"), list) else [data.get("key_tools")])):
        data["key_tools"] = [ 
            f"{name}'s signature combat tools", 
            f"{franchise} matchup experience", 
            "profile-specific win condition pending deeper source enrichment", 
        ] 
        changed = True 

    if not data.get("risk") or "pending" in str(data.get("risk")).lower(): 
        data["risk"] = "Needs deeper source enrichment before being treated as fully battle-certified." 
        changed = True 

    if not data.get("best_route") and not data.get("win_path"): 
        data["best_route"] = f"{name} needs to force their most reliable signature-tool route while denying the opponent's strongest opening." 
        changed = True 

    data.setdefault("qa_status", {}) 
    if not isinstance(data["qa_status"], dict): 
        data["qa_status"] = {} 
    data["qa_status"].update({ 
        "refresh_status": "refreshed_needs_mock_duel_recheck", 
        "refresh_reason": reason, 
        "refreshed_at": datetime.now().isoformat(timespec="seconds"), 
    }) 
    changed = True 

    raw_after = yaml.safe_dump(data, sort_keys=False, allow_unicode=True) 
    if raw_after == raw_before: 
        return False, "no_change" 

    backup_path = BACKUP / p.relative_to(ROOT) 
    backup_path.parent.mkdir(parents=True, exist_ok=True) 
    if not backup_path.exists(): 
        shutil.copy2(p, backup_path) 

    save_yaml(p, data) 
    return True, "refreshed" 

def main(): 
    DONE.mkdir(parents=True, exist_ok=True) 
    BACKUP.mkdir(parents=True, exist_ok=True) 
    hints = load_hints() 

    queue_files = sorted(QUEUE.glob("*.json")) 
    limit = 50 

    processed = 0 
    refreshed = 0 
    skipped = 0 
    results = [] 

    for q in queue_files[:limit]: 
        processed += 1 
        try: 
            item = json.loads(q.read_text(errors="ignore")) 
        except Exception: 
            skipped += 1 
            results.append((q.name, "bad_json")) 
            continue 

        profile_path = item.get("profile_path") 
        reason = item.get("reason") or item.get("priority") or "queued refresh" 
        if not profile_path: 
            skipped += 1 
            results.append((q.name, "no_profile_path")) 
            continue 

        ok, status = refresh_profile(profile_path, reason, hints) 
        if ok: 
            refreshed += 1 
        else: 
            skipped += 1 

        dest = DONE / q.name 
        q.replace(dest) 
        results.append((q.name, status)) 

    print(f"processed={processed}") 
    print(f"refreshed={refreshed}") 
    print(f"skipped={skipped}") 
    print(f"remaining_queue={len(list(QUEUE.glob('*.json')))}") 
    for name, status in results[:30]: 
        print(f"{name}: {status}") 

if __name__ == "__main__": 
    main() 
