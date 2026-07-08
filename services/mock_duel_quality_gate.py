from pathlib import Path 
from datetime import datetime 
import random, json, re, sys, yaml 

from battlebot.fight.decision_formatter import format_decision 

ROOT = Path(__file__).resolve().parents[1] 
GEN = ROOT / "profiles" / "generated" 
LOG_DIR = ROOT / "logs" / "mock_duel_quality" 
BAD = ROOT / "harvest" / "mock_duel_bad_outputs" 
GOOD = ROOT / "harvest" / "mock_duel_good_outputs" 

BAD_PATTERNS = [ 
    "profile pending source verification", 
    "needs source-backed", 
    "judge review needed", 
    "no supported loser path", 
    "no expanded evidence", 
    "more reliable stat-and-tool profile", 
    "{{", 
    "}}", 
    "null", 
    "none", 
] 

GENERIC_PATTERNS = [ 
    "packet-defined fighter", 
    "basic combat capability", 
    "profile-backed abilities", 
    "needs a clearer profile-backed win route", 
] 

def clean(x, limit=160): 
    if isinstance(x, list): 
        x = ", ".join(str(i.get("name") if isinstance(i, dict) else i) for i in x if i) 
    elif isinstance(x, dict): 
        x = ", ".join(str(v) for v in x.values() if v) 
    x = re.sub(r"\s+", " ", str(x or "")).strip() 
    return x[:limit].strip() 

def load_yaml(p): 
    try: 
        return yaml.safe_load(p.read_text(errors="ignore")) or {} 
    except Exception: 
        return {} 

def terms(profile): 
    buckets = [] 
    for key in ["weapon_power", "key_tools", "abilities", "powers", "weapons", "equipment", "magic", "forms", "strengths"]: 
        v = profile.get(key) 
        if v: 
            if isinstance(v, list): 
                for item in v: 
                    if isinstance(item, dict): 
                        buckets.append(item.get("name") or item.get("id") or item.get("description")) 
                    else: 
                        buckets.append(item) 
            elif isinstance(v, dict): 
                buckets.extend(v.values()) 
            else: 
                buckets.append(v) 
    out = [] 
    for item in buckets: 
        t = clean(item, 60) 
        if t and t.lower() not in {"yes", "no", "unknown", "profile pending source verification"}: 
            out.append(t) 
    return out[:6] 

def profile_score(profile): 
    text = json.dumps(profile, default=str).lower() 
    score = 0 
    for key in ["abilities", "powers", "weapons", "equipment", "weaknesses", "best_route", "risk"]: 
        if profile.get(key): 
            score += 2 
    if "profile pending source verification" in text: 
        score -= 12 
    if "unknown" in text: 
        score -= 2 
    return score 

def card(profile): 
    name = clean(profile.get("name") or profile.get("id") or "Unknown", 80) 
    tools = terms(profile) 
    weapon = clean(profile.get("weapon_power") or profile.get("power_of_choice") or profile.get("weapon_of_choice") or tools[:2], 140) 
    route = clean(profile.get("best_route") or profile.get("win_path") or "Use the strongest confirmed tools while denying the opponent's best opening.", 220) 
    risk = clean(profile.get("risk") or profile.get("weaknesses") or "Needs matchup-specific verification.", 160) 
    return { 
        "name": name, 
        "weapon_power": weapon or "Needs verified signature tool", 
        "style": clean(profile.get("combat_style") or profile.get("style") or "versatile fighter", 80), 
        "key_tools": tools[:4] or ["Needs verified signature tool"], 
        "best_route": route, 
        "risk": risk, 
    } 

def make_decision(a_prof, b_prof): 
    a_score = profile_score(a_prof) 
    b_score = profile_score(b_prof) 
    a_card = card(a_prof) 
    b_card = card(b_prof) 

    if a_score >= b_score: 
        winner, loser = a_card["name"], b_card["name"] 
        winner_card, loser_card = a_card, b_card 
    else: 
        winner, loser = b_card["name"], a_card["name"] 
        winner_card, loser_card = b_card, a_card 

    tool = winner_card["key_tools"][0] if winner_card["key_tools"] else "their best verified tool" 
    return { 
        "title": "Nerd Fight Referee Decision", 
        "winner": winner, 
        "loser": loser, 
        "confidence": "medium", 
        "winner_probability": 0.65, 
        "loser_probability": 0.35, 
        "summary": f"{winner} controls the matchup through {tool}, forcing {loser} to answer before their own route stabilizes.", 
        "loser_best_path": f"{loser} needed to force their safest opening before {winner} could lean on {tool}.", 
        "matchup_card": [winner_card, loser_card], 
        "deciding_factors": [ 
            { 
                "factor": "Signature Tools", 
                "evidence": f"{winner} has the cleaner confirmed tool lane through {tool}.", 
                "tactical_effect": f"{tool} gives {winner} the more reliable route to pressure and finish.", 
            }, 
            { 
                "factor": "Counterplay", 
                "evidence": f"{loser} needed a cleaner matchup-specific answer than the profile currently proves.", 
                "tactical_effect": f"The loser route is possible, but less reliable from the available profile data.", 
            }, 
        ], 
        "warnings": [], 
    } 

def judge_text(text): 
    low = text.lower() 
    bad = [p for p in BAD_PATTERNS if p in low] 
    generic = [p for p in GENERIC_PATTERNS if p in low] 
    too_short = len(text.strip()) < 500 
    return bad, generic, too_short 

def main(): 
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 25 
    LOG_DIR.mkdir(parents=True, exist_ok=True) 
    BAD.mkdir(parents=True, exist_ok=True) 
    GOOD.mkdir(parents=True, exist_ok=True) 

    files = sorted(GEN.rglob("*.yaml")) + sorted(GEN.rglob("*.yml")) 
    random.shuffle(files) 
    pairs = list(zip(files[0::2], files[1::2]))[:limit] 

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S") 
    report = {"time": datetime.now().isoformat(timespec="seconds"), "duels": 0, "good": 0, "bad": 0, "issues": []} 

    for a, b in pairs: 
        a_prof, b_prof = load_yaml(a), load_yaml(b) 
        decision = make_decision(a_prof, b_prof) 
        try: 
            text = format_decision(decision) 
            rc = 0 
        except Exception as e: 
            text = str(e) 
            rc = 1 

        bad, generic, too_short = judge_text(text) 
        issue = rc != 0 or bad or generic or too_short 

        name = f"{stamp}_{a.stem}-vs-{b.stem}.txt" 
        dest = BAD / name if issue else GOOD / name 
        dest.write_text(text, encoding="utf-8", errors="ignore") 

        report["duels"] += 1 
        if issue: 
            report["bad"] += 1 
            report["issues"].append({ 
                "a": a.as_posix(), 
                "b": b.as_posix(), 
                "output": dest.as_posix(), 
                "returncode": rc, 
                "bad_patterns": bad, 
                "generic_patterns": generic, 
                "too_short": too_short, 
            }) 
        else: 
            report["good"] += 1 

    out_report = LOG_DIR / f"mock_duel_quality_{stamp}.json" 
    out_report.write_text(json.dumps(report, indent=2), encoding="utf-8") 

    print(json.dumps(report, indent=2)) 
    print(f"report={out_report}") 

if __name__ == "__main__": 
    main() 
