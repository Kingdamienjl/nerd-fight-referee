from pathlib import Path 
import json, re, yaml 

ROOT = Path(__file__).resolve().parents[1] 
GEN = ROOT / "profiles" / "generated" 
OUT = ROOT / "config" / "proactive_franchise_hints.json" 

MANUAL_HINTS = { 
    "kenpachi zaraki": "Bleach", 
    "toshiro hitsugaya": "Bleach", 
    "shunsui kyoraku": "Bleach", 
    "mayuri kurotsuchi": "Bleach", 
    "ichigo kurosaki": "Bleach", 
    "ulquiorra cifer": "Bleach", 
    "coyote starrk": "Bleach", 
    "aizen": "Bleach", 
    "sosuke aizen": "Bleach", 

    "zodd": "Berserk", 
    "nosferatu zodd": "Berserk", 
    "casca": "Berserk", 
    "guts": "Berserk", 
    "griffith": "Berserk", 

    "father": "Fullmetal Alchemist", 
    "roy mustang": "Fullmetal Alchemist", 
    "edward elric": "Fullmetal Alchemist", 
    "alphonse elric": "Fullmetal Alchemist", 

    "muzan kibutsuji": "Demon Slayer", 
    "nezuko kamado": "Demon Slayer", 
    "tanjiro kamado": "Demon Slayer", 
    "yoriichi tsugikuni": "Demon Slayer", 

    "dante zogratis": "Black Clover", 
    "julius novachrono": "Black Clover", 
    "yuno": "Black Clover", 
    "asta": "Black Clover", 

    "viego": "League of Legends", 
    "yasuo": "League of Legends", 
    "mordekaiser": "League of Legends", 

    "nier": "NieR", 
    "9s": "NieR", 
    "2b": "NieR", 
    "lina": "Slayers", 
    "ikki": "Saint Seiya", 
} 

def norm(s): 
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip() 

def load_yaml(path): 
    try: 
        return yaml.safe_load(path.read_text(errors="ignore")) or {} 
    except Exception: 
        return {} 

def clean_franchise(value): 
    if isinstance(value, list): 
        value = value[0] if value else "" 
    if isinstance(value, dict): 
        value = value.get("name") or value.get("id") or "" 
    value = str(value or "").strip() 
    bad = {"unknown", "mixed", "user-requests", "expansion-seeds", "crossover-icons", "none", "null"} 
    if not value or value.lower() in bad: 
        return "" 
    return value 

def infer_from_path(path): 
    parts = [x for x in path.parts] 
    try: 
        i = parts.index("generated") 
        after = parts[i+1:] 
    except ValueError: 
        return "" 

    # examples: 
    # generated/anime/bleach/name.yaml 
    # generated/comic/marvel/name.yaml 
    # generated/game/final-fantasy/name.yaml 
    # generated/mixed/expansion-seeds/tv_movie/star-wars/name.yaml 
    ignore = {"mixed", "expansion-seeds", "anime", "comic", "comics", "game", "tv", "tv_movie", "movie", "user-requests", "crossover-icons"} 
    for part in after[:-1]: 
        if part not in ignore: 
            return part.replace("-", " ").title() 
    return "" 

def main(): 
    hints = dict(MANUAL_HINTS) 

    all_files = sorted(GEN.rglob("*.yaml")) 
    total_files = len(all_files) 
    print(f"Found {total_files} profiles to process...") 

    for i, p in enumerate(all_files): 
        if (i + 1) % 100 == 0: 
            print(f"  ...processed {i + 1} / {total_files}") 

        data = load_yaml(p) 

        name = data.get("name") or data.get("id") or p.stem.replace("-", " ") 
        franchise = ( 
            clean_franchise(data.get("franchise")) 
            or clean_franchise(data.get("series")) 
            or clean_franchise(data.get("source")) 
            or clean_franchise(data.get("universe")) 
            or infer_from_path(p) 
        ) 

        if not franchise: 
            continue 

        names = { 
            norm(name), 
            norm(p.stem.replace("-", " ")), 
        } 

        aliases = data.get("aliases") or data.get("alias") or [] 
        if isinstance(aliases, str): 
            aliases = [aliases] 
        if isinstance(aliases, list): 
            for a in aliases: 
                names.add(norm(a)) 

        for n in names: 
            if n and n not in hints: 
                hints[n] = franchise 

    OUT.parent.mkdir(parents=True, exist_ok=True) 
    OUT.write_text(json.dumps(dict(sorted(hints.items())), indent=2), encoding="utf-8") 

    print(f"franchise_hints={len(hints)}") 
    print(f"out={OUT}") 

if __name__ == "__main__": 
    main() 
