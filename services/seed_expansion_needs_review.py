from pathlib import Path 
from datetime import datetime 
import re 

ROOT = Path(__file__).resolve().parents[1] 
GEN = ROOT / "profiles" / "generated" 
NR = ROOT / "profiles" / "needs_review" / "mixed" / "expansion-seeds" 

SEEDS = { 
    "Power Rangers": [ 
        "Tommy Oliver", "Jason Lee Scott", "Kimberly Hart", "Billy Cranston", 
        "Trini Kwan", "Zack Taylor", "Lord Zedd", "Rita Repulsa", 
        "Goldar", "Ivan Ooze", "Andros", "Astronema", "Jen Scotts", 
        "Wes Collins", "Eric Myers", "Dillon", "Drakkon", 
    ], 
    "Pokemon": [ 
        "Pikachu", "Charizard", "Mewtwo", "Lucario", "Greninja", 
        "Gengar", "Machamp", "Gardevoir", "Rayquaza", "Groudon", 
        "Kyogre", "Arceus", "Dialga", "Palkia", "Giratina", 
        "Zacian", "Eternatus", "Red", "Ash Ketchum", "Cynthia", 
    ], 
    "Marvel": [ 
        "Doctor Doom", "Magneto", "Storm", "Jean Grey", "Cyclops", 
        "Wolverine", "Rogue", "Gambit", "Nightcrawler", "Cable", 
        "Silver Surfer", "Galactus", "Thanos", "Scarlet Witch", 
        "Vision", "Black Panther", "Moon Knight", "Ghost Rider", 
        "Blade", "Nova", "Sentry", "Blue Marvel", "Kang the Conqueror", 
    ], 
    "DC": [ 
        "Darkseid", "Brainiac", "Martian Manhunter", "Zatanna", 
        "Doctor Fate", "Raven", "Cyborg", "Beast Boy", "Deathstroke", 
        "Black Adam", "Shazam", "Sinestro", "Atrocitus", "Larfleeze", 
        "Reverse-Flash", "Zoom", "Constantine", "Etrigan", "Swamp Thing", 
        "Mister Miracle", "Big Barda", "Orion", 
    ], 
    "Mortal Kombat": [ 
        "Liu Kang", "Raiden", "Scorpion", "Sub-Zero", "Noob Saibot", 
        "Shao Kahn", "Shang Tsung", "Quan Chi", "Kitana", "Mileena", 
        "Sindel", "Johnny Cage", "Kenshi", "Ermac", "Rain", "Fujin", 
    ], 
    "Street Fighter": [ 
        "Ryu", "Ken Masters", "Chun-Li", "Guile", "Akuma", 
        "M. Bison", "Cammy", "Juri Han", "Sagat", "Vega", 
        "Balrog", "Dhalsim", "Zangief", "Luke Sullivan", 
    ], 
} 

def slugify(x): 
    x = re.sub(r"\([^)]*\)", "", x.lower()) 
    x = re.sub(r"[^a-z0-9]+", "-", x) 
    return x.strip("-") or "unknown" 

def q(x): 
    return str(x).replace('"', "'") 

GEN_INDEX = {p.stem for p in GEN.rglob("*.yaml")} | {p.stem for p in GEN.rglob("*.yml")} 
REVIEW_ROOT = ROOT / "profiles" / "needs_review" 
REVIEW_INDEX = {p.stem for p in REVIEW_ROOT.rglob("*.yaml")} | {p.stem for p in REVIEW_ROOT.rglob("*.yml")} 

def category_for(franchise): 
     if franchise in {"Pokemon", "More Pokemon", "Mortal Kombat", "Street Fighter", "Tekken", "Soulcalibur", "King of Fighters", "Castlevania", "Mega Man", "Metroid", "Final Fantasy Expansion"}: 
         return "game" 
     if franchise in {"Marvel", "DC", "More Marvel", "More DC", "Teenage Mutant Ninja Turtles", "Transformers"}: 
         return "comics" 
     if franchise in {"Power Rangers", "Star Wars", "Lord of the Rings", "Harry Potter", "Horror Icons"}: 
         return "tv_movie" 
     return "mixed" 

def write_seed(franchise, name): 
    slug = slugify(name) 
    if slug in GEN_INDEX: 
        return "skip_generated" 
    if slug in REVIEW_INDEX: 
        return "skip_review" 

    cat = category_for(franchise) 
    outdir = NR / cat / slugify(franchise) 
    outdir.mkdir(parents=True, exist_ok=True) 
    out = outdir / f"{slug}.yaml" 
    now = datetime.now().isoformat(timespec="seconds") 

    out.write_text(f'''name: "{q(name)}" 
id: "{slug}" 
slug: "{slug}" 
category: "{cat}" 
franchise: "{q(franchise)}" 
source_status: "needs_review" 
profile_status: "expansion_seed" 

queue: 
  priority: "p0_roster_expansion" 
  request_count: 1 
  first_seen_source: "curated_expansion_seed" 
  last_requested_at: "{now}" 
  requested_by: "roster_expansion" 
  reason: "Curated franchise expansion target to broaden fight coverage." 

research: 
  category_guess: "{cat}" 
  franchise_guess: "{q(franchise)}" 
  source_candidates: 
    - "vsbattles" 
    - "superherodb" 
    - "comicvine" 
    - "fandom" 
    - "manual_web_search" 
  research_targets: 
    - "Find exact character profile for {q(name)}" 
    - "Confirm canon/source for {q(franchise)}" 
    - "Collect powers, weapons, weaknesses, combat style, forms, and signature tools" 

combat_identity: 
  identity_summary: "{q(name)} is a curated roster expansion target from {q(franchise)}." 
  combat_style: "profile pending source verification" 

weapon_power: 
  - "Profile pending source verification" 

key_tools: 
  - "Profile pending source verification" 

strengths: 
  - "Curated high-value roster expansion target" 

weaknesses: 
  - "Source verification pending" 

best_route: "Needs source-backed profile data before a confident win route can be assigned." 
risk: "Source verification pending" 

notes: 
  - "Created by franchise expansion seed script." 
''', encoding="utf-8") 
    return "created" 

# AI_NERD_EXPANSION_WAVE_2 
WAVE_2_SEEDS = { 
    "Transformers": [ 
        "Optimus Prime", "Megatron", "Starscream", "Bumblebee", "Soundwave", 
        "Shockwave", "Grimlock", "Unicron", "Hot Rod", "Rodimus Prime", 
        "Ultra Magnus", "Galvatron", "Devastator", "Predaking", "Arcee", 
        "Wheeljack", "Ironhide", "Ratchet", "Jazz", "Blackarachnia", 
    ], 
    "Teenage Mutant Ninja Turtles": [ 
        "Leonardo", "Raphael", "Donatello", "Michelangelo", "Splinter", 
        "Shredder", "Bebop", "Rocksteady", "Casey Jones", "April O'Neil", 
        "Karai", "Leatherhead", "Krang", "Metalhead", "Baxter Stockman", 
    ], 
    "Star Wars": [ 
        "Darth Vader", "Luke Skywalker", "Yoda", "Obi-Wan Kenobi", "Darth Maul", 
        "Emperor Palpatine", "Mace Windu", "Count Dooku", "General Grievous", 
        "Ahsoka Tano", "Anakin Skywalker", "Kylo Ren", "Rey Skywalker", 
        "Boba Fett", "Din Djarin", "Cal Kestis", "Starkiller", "Revan", 
    ], 
    "Lord of the Rings": [ 
        "Gandalf", "Sauron", "Aragorn", "Legolas", "Gimli", "Saruman", 
        "Witch-king of Angmar", "Balrog", "Galadriel", "Elrond", "Boromir", 
        "Frodo Baggins", "Samwise Gamgee", "Gollum", "Shelob", 
    ], 
    "Harry Potter": [ 
        "Harry Potter", "Hermione Granger", "Ron Weasley", "Albus Dumbledore", 
        "Lord Voldemort", "Severus Snape", "Sirius Black", "Bellatrix Lestrange", 
        "Minerva McGonagall", "Draco Malfoy", "Remus Lupin", "Mad-Eye Moody", 
        "Lucius Malfoy", "Gellert Grindelwald", "Newt Scamander", 
    ], 
    "Horror Icons": [ 
        "Freddy Krueger", "Jason Voorhees", "Michael Myers", "Leatherface", 
        "Pinhead", "Chucky", "Ghostface", "Candyman", "Pennywise", 
        "The Creeper", "Pumpkinhead", "Ash Williams", "Predator", "Xenomorph", 
    ], 
    "Tekken": [ 
        "Jin Kazama", "Kazuya Mishima", "Heihachi Mishima", "Nina Williams", 
        "Paul Phoenix", "King", "Yoshimitsu", "Hwoarang", "Bryan Fury", 
        "Ling Xiaoyu", "Lars Alexandersson", "Devil Jin", "Jun Kazama", 
        "Marshall Law", "Armor King", 
    ], 
    "Soulcalibur": [ 
        "Siegfried", "Nightmare", "Mitsurugi", "Taki", "Ivy Valentine", 
        "Sophitia", "Kilik", "Maxi", "Voldo", "Cervantes", "Astaroth", 
        "Talim", "Zasalamel", "Raphael Sorel", "Inferno", 
    ], 
    "King of Fighters": [ 
        "Kyo Kusanagi", "Iori Yagami", "Terry Bogard", "Mai Shiranui", 
        "Rugal Bernstein", "Geese Howard", "Athena Asamiya", "Kula Diamond", 
        "K'", "Leona Heidern", "Orochi", "Ash Crimson", "Rock Howard", 
    ], 
    "Castlevania": [ 
        "Simon Belmont", "Trevor Belmont", "Richter Belmont", "Alucard", 
        "Dracula", "Death", "Sypha Belnades", "Grant Danasty", "Soma Cruz", 
        "Shanoa", "Maria Renard", "Hector", "Isaac", "Carmilla", 
    ], 
    "Mega Man": [ 
        "Mega Man", "Proto Man", "Bass", "Dr. Wily", "Zero", "X", 
        "Sigma", "Axl", "Vile", "Roll", "Duo", "Copy X", 
        "Omega Zero", "Dr. Light", 
    ], 
    "Metroid": [ 
        "Samus Aran", "Ridley", "Dark Samus", "Mother Brain", "Kraid", 
        "Raven Beak", "SA-X", "Metroid Prime", "Sylux", "Adam Malkovich", 
    ], 
    "More Marvel": [ 
        "Mister Sinister", "Apocalypse", "Juggernaut", "Mystique", "Sabretooth", 
        "Emma Frost", "Iceman", "Colossus", "Psylocke", "Kitty Pryde", 
        "Daken", "Omega Red", "Taskmaster", "Bullseye", "Kingpin", 
        "Carnage", "Venom", "Anti-Venom", "Morbius", "Molecule Man", 
        "Hercules", "Ares", "Beta Ray Bill", "Gladiator", "Hyperion", 
        "Franklin Richards", "Legion", "Onslaught", "Nimrod", "Ultron", 
    ], 
    "More DC": [ 
        "Metallo", "Bizarro", "Parasite", "Mongul", "Lobo", "Superboy-Prime", 
        "Doomsday", "Red Tornado", "Plastic Man", "Vixen", "Hawkgirl", 
        "Hawkman", "Captain Atom", "Blue Beetle", "Booster Gold", 
        "Firestorm", "Red Robin", "Nightwing", "Batgirl", "Hush", 
        "Clayface", "Killer Croc", "Poison Ivy", "Mr. Freeze", "Ra's al Ghul", 
        "Talia al Ghul", "Cheetah", "Giganta", "Ares", "Circe", 
    ], 
    "More Pokemon": [ 
        "Miraidon", "Koraidon", "Lugia", "Ho-Oh", "Deoxys", "Darkrai", 
        "Cresselia", "Reshiram", "Zekrom", "Kyurem", "Xerneas", "Yveltal", 
        "Zygarde", "Solgaleo", "Lunala", "Necrozma", "Mew", "Celebi", 
        "Jirachi", "Victini", "N", "Lance", "Steven Stone", "Leon", 
    ], 
    "Final Fantasy Expansion": [ 
        "Garland", "Emperor Mateus", "Cloud of Darkness", "Golbez", "Exdeath", 
        "Kefka Palazzo", "Ultimecia", "Kuja", "Jecht", "Vayne Solidor", 
        "Lightning", "Noctis Lucis Caelum", "Clive Rosfield", "Tifa Lockhart", 
        "Aerith Gainsborough", "Zack Fair", "Vincent Valentine", "Yuffie Kisaragi", 
        "Terra Branford", "Celes Chere", "Squall Leonhart", "Rinoa Heartilly", 
    ], 
} 

def main(): 
    created = sg = sr = 0 
    all_seeds = dict(SEEDS)
    all_seeds.update(WAVE_2_SEEDS)
    for franchise, names in all_seeds.items(): 
        for name in names: 
            r = write_seed(franchise, name) 
            if r == "created": created += 1 
            elif r == "skip_generated": sg += 1 
            elif r == "skip_review": sr += 1 
    print(f"created={created}") 
    print(f"skip_generated={sg}") 
    print(f"skip_review_exists={sr}") 
    print(f"needs_review={REVIEW_ROOT}") 

if __name__ == "__main__": 
    main() 
