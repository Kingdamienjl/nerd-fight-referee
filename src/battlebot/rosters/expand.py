"""Expand roster CSVs from curated identity seed lists."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from battlebot.profiles.variants import CURATED_VARIANTS


ROSTER_HEADER = ["category", "franchise", "name", "aliases", "wiki_title", "wiki_url"]
DEFAULT_ROSTER_DIR = Path("profiles/rosters")
OUTPUT_FILES = {
    "comic": "backfill_roster_003_comics.csv",
    "game": "backfill_roster_004_games.csv",
    "anime": "backfill_roster_005_anime.csv",
    "mixed": "backfill_roster_006_mixed.csv",
    "variants": "backfill_roster_007_variants.csv",
}


@dataclass(frozen=True)
class RosterRow:
    category: str
    franchise: str
    name: str
    aliases: str = ""
    wiki_title: str = ""
    wiki_url: str = ""

    def key(self) -> tuple[str, str, str]:
        return (self.category.casefold(), self.franchise.casefold(), self.name.casefold())

    def as_list(self) -> list[str]:
        return [
            self.category,
            self.franchise,
            self.name,
            self.aliases,
            self.wiki_title or self.name,
            self.wiki_url,
        ]


SEEDS: dict[tuple[str, str], str] = {
    ("comic", "Marvel"): """
Iron Man|Tony Stark, Spider-Man|Peter Parker, Miles Morales, Captain America|Steve Rogers,
Thor, Hulk|Bruce Banner, Wolverine|Logan, Deadpool|Wade Wilson, Doctor Strange|Stephen Strange,
Scarlet Witch|Wanda Maximoff, Black Panther|T'Challa, Storm|Ororo Munroe, Magneto|Erik Lensherr,
Professor X|Charles Xavier, Jean Grey, Cyclops|Scott Summers, Rogue, Gambit, Nightcrawler,
Colossus, Iceman, Beast, Cable, Bishop, Psylocke, Emma Frost, Kitty Pryde, Mystique,
Sabretooth, Juggernaut, Apocalypse, Mister Sinister, Doctor Doom, Galactus, Silver Surfer,
Thanos, Loki, Hela, Odin, Sentry, Blue Marvel, Captain Marvel|Carol Danvers, Ms. Marvel|Kamala Khan,
She-Hulk|Jennifer Walters, Moon Knight|Marc Spector, Blade, Ghost Rider|Johnny Blaze,
Ghost Rider|Robbie Reyes, Punisher|Frank Castle, Daredevil|Matt Murdock, Elektra, Kingpin,
Bullseye, Luke Cage, Iron Fist|Danny Rand, Jessica Jones, Shang-Chi, Black Widow|Natasha Romanoff,
Hawkeye|Clint Barton, Kate Bishop, Ant-Man|Scott Lang, Wasp|Janet van Dyne, Vision,
Ultron, Kang the Conqueror, Annihilus, Nova|Richard Rider, Star-Lord|Peter Quill, Gamora,
Drax, Rocket Raccoon, Groot, Adam Warlock, Beta Ray Bill, Namor, Black Bolt, Medusa,
Crystal, Karnak, Quicksilver, Red Skull, Baron Zemo, Taskmaster, Venom|Eddie Brock,
Carnage|Cletus Kasady, Green Goblin|Norman Osborn, Doctor Octopus, Sandman, Electro,
Mysterio, Kraven the Hunter, Lizard|Curt Connors, Morbius, Cloak, Dagger, Squirrel Girl
""",
    ("comic", "DC"): """
Superman|Clark Kent, Batman|Bruce Wayne, Wonder Woman|Diana Prince, The Flash|Barry Allen,
The Flash|Wally West, Green Lantern|Hal Jordan, Green Lantern|John Stewart, Aquaman|Arthur Curry,
Martian Manhunter|J'onn J'onzz, Cyborg|Victor Stone, Shazam|Billy Batson, Black Adam,
Green Arrow|Oliver Queen, Black Canary|Dinah Lance, Zatanna, Doctor Fate|Kent Nelson,
Constantine|John Constantine, Swamp Thing, Raven, Starfire, Beast Boy, Robin|Dick Grayson,
Nightwing|Dick Grayson, Red Hood|Jason Todd, Robin|Tim Drake, Batgirl|Barbara Gordon,
Batwoman|Kate Kane, Supergirl|Kara Zor-El, Power Girl, Steel|John Henry Irons,
Lex Luthor, Joker, Harley Quinn, Deathstroke|Slade Wilson, Darkseid, Doomsday, Brainiac,
General Zod, Sinestro, Reverse-Flash|Eobard Thawne, Zoom|Hunter Zolomon, Gorilla Grodd,
Black Manta, Ocean Master, Cheetah, Ares, Circe, Ra's al Ghul, Bane, Scarecrow,
Riddler, Two-Face, Penguin, Poison Ivy, Clayface, Mr. Freeze, Killer Croc, Solomon Grundy,
Lobo, Etrigan, Blue Beetle|Jaime Reyes, Booster Gold, Firestorm, Atom|Ray Palmer,
Hawkman, Hawkgirl, Vixen, Mister Miracle, Big Barda, Orion, Spectre, Phantom Stranger,
Trigon, Mongul, Amanda Waller, Peacemaker, Vigilante, Static, Icon, Rocket, Midnighter,
Apollo, Grifter, Red Tornado, Plastic Man, Metamorpho, Captain Atom, Animal Man
""",
    ("comic", "Image Comics"): """
Invincible|Mark Grayson, Omni-Man|Nolan Grayson, Atom Eve|Samantha Eve Wilkins, Thragg,
Allen the Alien, Battle Beast, Robot|Rudolph Conners, Rex Splode, Dupli-Kate, Monster Girl,
The Immortal, Spawn|Al Simmons, Angela, Violator, Savage Dragon, Witchblade|Sara Pezzini,
The Darkness|Jackie Estacado, Rick Grimes, Michonne, Negan, Yorick Brown, Lying Cat,
Hazel, Alana, Marko, Prince Robot IV, Maika Halfwolf, Lord Drakkon
""",
    ("anime", "Dragon Ball"): """
Son Goku|Goku|Kakarot, Vegeta, Gohan, Piccolo, Krillin, Frieza, Cell, Majin Buu,
Beerus, Whis, Broly, Trunks, Future Trunks, Goten, Android 17, Android 18, Jiren,
Hit, Zamasu, Goku Black, Gogeta, Vegito, Bardock, Raditz, Nappa, Tien Shinhan,
Yamcha, Master Roshi, Bulma, Chi-Chi, Pan, Caulifla, Kale, Kefla, Toppo, Dyspo
""",
    ("anime", "Naruto"): """
Naruto Uzumaki, Sasuke Uchiha, Sakura Haruno, Kakashi Hatake, Itachi Uchiha, Madara Uchiha,
Obito Uchiha, Minato Namikaze, Jiraiya, Tsunade, Orochimaru, Might Guy, Rock Lee,
Gaara, Shikamaru Nara, Hinata Hyuga, Neji Hyuga, Pain|Nagato, Konan, Kisame Hoshigaki,
Deidara, Sasori, Hidan, Kakuzu, Kaguya Otsutsuki, Boruto Uzumaki, Sarada Uchiha,
Mitsuki, Killer B, Raikage A, Tobirama Senju, Hashirama Senju, Hiruzen Sarutobi
""",
    ("anime", "One Piece"): """
Monkey D. Luffy, Roronoa Zoro, Nami, Usopp, Sanji, Tony Tony Chopper, Nico Robin,
Franky, Brook, Jinbe, Shanks, Dracule Mihawk, Kaido, Big Mom|Charlotte Linlin,
Marshall D. Teach|Blackbeard, Whitebeard|Edward Newgate, Portgas D. Ace, Sabo,
Trafalgar Law, Eustass Kid, Boa Hancock, Crocodile, Donquixote Doflamingo, Rob Lucci,
Kizaru|Borsalino, Akainu|Sakazuki, Aokiji|Kuzan, Fujitora|Issho, Silvers Rayleigh,
Gol D. Roger, Yamato, Charlotte Katakuri, King, Marco, Enel, Buggy
""",
    ("anime", "Bleach"): """
Ichigo Kurosaki, Rukia Kuchiki, Renji Abarai, Byakuya Kuchiki, Kenpachi Zaraki,
Toshiro Hitsugaya, Sosuke Aizen, Kisuke Urahara, Yoruichi Shihoin, Orihime Inoue,
Uryu Ishida, Yhwach, Grimmjow Jaegerjaquez, Ulquiorra Cifer, Coyote Starrk,
Baraggan Louisenbairn, Nelliel Tu Odelschwanck, Mayuri Kurotsuchi, Shunsui Kyoraku,
Genryusai Yamamoto, Gin Ichimaru, Kaname Tosen, Retsu Unohana
""",
    ("anime", "JoJo's Bizarre Adventure"): """
Jonathan Joestar, Joseph Joestar, Jotaro Kujo, Josuke Higashikata, Giorno Giovanna,
Jolyne Cujoh, Johnny Joestar, Josuke Higashikata (JoJolion), Dio Brando, DIO,
Kars, Yoshikage Kira, Diavolo, Enrico Pucci, Funny Valentine, Tooru, Caesar Zeppeli,
Noriaki Kakyoin, Jean Pierre Polnareff, Muhammad Avdol, Okuyasu Nijimura, Koichi Hirose,
Bruno Bucciarati, Leone Abbacchio, Guido Mista, Narancia Ghirga, Trish Una
""",
    ("anime", "Sailor Moon"): """
Usagi Tsukino|Sailor Moon, Ami Mizuno|Sailor Mercury, Rei Hino|Sailor Mars,
Makoto Kino|Sailor Jupiter, Minako Aino|Sailor Venus, Chibiusa, Mamoru Chiba|Tuxedo Mask,
Setsuna Meioh|Sailor Pluto, Haruka Tenoh|Sailor Uranus, Michiru Kaioh|Sailor Neptune,
Hotaru Tomoe|Sailor Saturn, Queen Beryl, Queen Metalia, Black Lady, Sailor Galaxia
""",
    ("anime", "Jujutsu Kaisen"): """
Yuji Itadori, Megumi Fushiguro, Nobara Kugisaki, Satoru Gojo, Ryomen Sukuna,
Yuta Okkotsu, Maki Zenin, Toge Inumaki, Panda, Kento Nanami, Aoi Todo, Mahito,
Suguru Geto, Kenjaku, Toji Fushiguro, Jogo, Hanami, Choso, Kinji Hakari, Hajime Kashimo
""",
    ("anime", "Demon Slayer"): """
Tanjiro Kamado, Nezuko Kamado, Zenitsu Agatsuma, Inosuke Hashibira, Giyu Tomioka,
Kyojuro Rengoku, Tengen Uzui, Muichiro Tokito, Mitsuri Kanroji, Obanai Iguro,
Sanemi Shinazugawa, Gyomei Himejima, Shinobu Kocho, Muzan Kibutsuji, Akaza, Doma,
Kokushibo, Gyutaro, Daki, Rui, Kanao Tsuyuri, Genya Shinazugawa
""",
    ("anime", "Mixed Anime"): """
Alucard, Seras Victoria, Integra Hellsing, Guts, Griffith, Casca, Zodd, Skull Knight,
Shinji Ikari, Asuka Langley Soryu, Rei Ayanami, Eva Unit-01, Rimuru Tempest, Sung Jinwoo,
Makima, Denji, Power, Aki Hayakawa, Mob|Shigeo Kageyama, Arataka Reigen, Vash the Stampede,
Millions Knives, Nicholas D. Wolfwood, Yusuke Urameshi, Hiei, Kurama, Toguro,
Seiya, Ikki, Athena, Hades, Father, Edward Elric, Alphonse Elric, Roy Mustang
""",
    ("game", "Final Fantasy"): """
Cloud Strife, Sephiroth, Tifa Lockhart, Aerith Gainsborough, Barret Wallace, Squall Leonhart,
Rinoa Heartilly, Seifer Almasy, Zidane Tribal, Vivi Ornitier, Garnet Til Alexandros XVII,
Tidus, Yuna, Auron, Jecht, Lightning, Noctis Lucis Caelum, Clive Rosfield, Joshua Rosfield,
Jill Warrick, Kefka Palazzo, Terra Branford, Cecil Harvey, Kain Highwind, Golbez,
Warrior of Light, Garland, Ultimecia, Kuja, Emet-Selch, Hydaelyn, Zodiark
""",
    ("game", "Kingdom Hearts"): """
Sora, Riku, Kairi, Mickey Mouse, Donald Duck, Goofy, Roxas, Axel, Xion, Aqua,
Terra, Ventus, Vanitas, Master Xehanort, Ansem Seeker of Darkness, Xemnas,
Marluxia, Larxene, Saix, Xigbar, Namine, Master Eraqus
""",
    ("game", "Devil May Cry"): """
Dante, Vergil, Nero, Trish, Lady, V, Sparda, Mundus, Arkham, Arius, Sanctus,
Credo, Agnus, Urizen, Nightmare, Nelo Angelo
""",
    ("game", "Doom"): """
Doom Slayer, Doomguy, Marauder, Cyberdemon, Spider Mastermind, Icon of Sin,
Khan Maykr, Samuel Hayden, Olivia Pierce, Baron of Hell, Revenant, Arch-Vile
""",
    ("game", "God of War"): """
Kratos, Atreus, Zeus, Ares, Athena, Hades, Poseidon, Hercules, Baldur, Freya,
Thor, Odin, Heimdall, Tyr, Mimir, Fenrir, Surtr, Magni, Modi, Gaia
""",
    ("game", "Mortal Kombat"): """
Scorpion, Sub-Zero, Liu Kang, Raiden, Johnny Cage, Sonya Blade, Kano, Shang Tsung,
Shao Kahn, Kitana, Mileena, Jade, Kung Lao, Jax, Noob Saibot, Smoke, Cyrax,
Sektor, Reptile, Baraka, Quan Chi, Shinnok, Kenshi, Ermac, Rain, Sindel,
Kotal Kahn, Cassie Cage, D'Vorah, Geras, Kronika
""",
    ("game", "Mixed Games"): """
Ryu, Ken Masters, Chun-Li, M. Bison, Akuma, Guile, Cammy, Zangief, Juri Han,
Jin Kazama, Kazuya Mishima, Heihachi Mishima, Nina Williams, King, Yoshimitsu,
Master Chief, Cortana, Arbiter, Noble Six, Samus Aran, Ridley, Link, Zelda,
Ganondorf, Sonic the Hedgehog, Shadow the Hedgehog, Knuckles, Tails, Eggman,
Leon S. Kennedy, Albert Wesker, Jill Valentine, Chris Redfield, Ada Wong,
Solid Snake, Raiden, Senator Armstrong, Big Boss, Bayonetta, Jeanne, Mega Man,
Zero, Sigma, X, Ryu Hayabusa, 2B, A2, Geralt of Rivia, Ciri, Diablo, Tyrael,
Mephisto, Malenia, Radahn, Ranni, Tarnished, Elden Beast
""",
    ("mixed", "Crossover Icons"): """
Mario, Luigi, Princess Peach, Bowser, Donkey Kong, Kirby, Meta Knight, Fox McCloud,
Captain Falcon, Pit, Palutena, Inkling, Shovel Knight, Shantae, Lara Croft,
Nathan Drake, Kratos, Doom Slayer, Master Chief, Sonic the Hedgehog, Mega Man,
Ryu, Chun-Li, Scorpion, Sub-Zero, Cloud Strife, Sephiroth, Sora, Bayonetta,
Geralt of Rivia, 2B, Link, Zelda, Samus Aran, Pikachu, Mewtwo, Lucario,
Charizard, Ash Ketchum, Optimus Prime, Megatron, Leonardo, Raphael, Donatello,
Michelangelo, He-Man, Skeletor, She-Ra, Spawn, Invincible, Goku, Naruto Uzumaki
""",
}

MARVEL_VARIANTS = ("", " (Marvel Comics)", " (Earth-616)", " (Marvel Cinematic Universe)")
DC_VARIANTS = ("", " (DC Comics)", " (Post-Crisis)", " (Post-Flashpoint)", " (Rebirth)", " (Prime Earth)")
IMAGE_VARIANTS = ("", " (Image Comics)")
MIXED_VARIANTS = ("",)


def parse_seed_entry(entry: str) -> tuple[str, str]:
    parts = [part.strip() for part in entry.split("|") if part.strip()]
    if not parts:
        return "", ""
    return parts[0], "|".join(parts[1:])


def title_variants(category: str, franchise: str) -> tuple[str, ...]:
    """Return safe roster title variants for a category/franchise.

    Comic continuity variants must never leak into anime/game franchises.
    Anime/game transformation forms should come from curated form variants,
    not publisher continuity suffixes.
    """
    normalized_category = category.strip().casefold()
    normalized_franchise = franchise.strip().casefold()

    if normalized_category != "comic":
        return ("",)

    if normalized_franchise == "marvel":
        return MARVEL_VARIANTS

    if normalized_franchise == "dc":
        return DC_VARIANTS

    if normalized_franchise in {"image", "image comics"}:
        return IMAGE_VARIANTS

    return ("",)

def seed_rows() -> list[RosterRow]:
    rows = []
    for (category, franchise), raw_names in SEEDS.items():
        for raw_entry in raw_names.replace("\n", " ").split(","):
            name, aliases = parse_seed_entry(raw_entry)
            if not name:
                continue
            for suffix in title_variants(category, franchise):
                if suffix and suffix in name:
                    continue
                title = f"{name}{suffix}"
                rows.append(RosterRow(category, franchise, title, aliases, title))
    return rows


def variant_rows() -> list[RosterRow]:
    return [
        RosterRow(
            seed.category,
            seed.franchise,
            seed.name,
            seed.aliases,
            seed.name,
            "",
        )
        for seed in CURATED_VARIANTS
    ]


def read_roster_rows(roster_dir: Path, *, include_generated_outputs: bool = True) -> list[RosterRow]:
    rows = []
    for path in sorted(roster_dir.glob("*.csv")):
        if not include_generated_outputs and path.name in set(OUTPUT_FILES.values()):
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if not row.get("name"):
                    continue
                rows.append(
                    RosterRow(
                        row.get("category", ""),
                        row.get("franchise", ""),
                        row.get("name", ""),
                        row.get("aliases", ""),
                        row.get("wiki_title", ""),
                        row.get("wiki_url", ""),
                    )
                )
    return rows


def split_key(row: RosterRow) -> str:
    if row.category in {"comic", "game", "anime"}:
        return row.category
    return "mixed"


def expand_rosters(roster_dir: Path, target_total: int) -> dict[str, int]:
    roster_dir.mkdir(parents=True, exist_ok=True)
    existing = read_roster_rows(roster_dir, include_generated_outputs=False)
    used = {row.key() for row in existing}
    buckets: dict[str, list[RosterRow]] = {key: [] for key in OUTPUT_FILES}
    total = len(existing)
    candidates: dict[str, list[RosterRow]] = {key: [] for key in OUTPUT_FILES}
    for row in seed_rows():
        if row.key() in used:
            continue
        used.add(row.key())
        candidates[split_key(row)].append(row)

    while total < target_total and any(candidates.values()):
        for key in ("comic", "game", "anime", "mixed"):
            if total >= target_total:
                break
            if not candidates[key]:
                continue
            buckets[key].append(candidates[key].pop(0))
            total += 1
    for row in variant_rows():
        buckets["variants"].append(row)
        if row.key() in used:
            continue
        used.add(row.key())
        total += 1

    counts = {}
    for key, filename in OUTPUT_FILES.items():
        path = roster_dir / filename
        rows = buckets[key]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(ROSTER_HEADER)
            writer.writerows(row.as_list() for row in rows)
        counts[filename] = len(rows)
    counts["total_roster_rows"] = total
    return counts


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expand curated roster CSVs")
    parser.add_argument("--roster-dir", type=Path, default=DEFAULT_ROSTER_DIR)
    parser.add_argument("--target-total", type=int, default=1500)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    counts = expand_rosters(args.roster_dir, args.target_total)
    for key, value in counts.items():
        print(f"{key}: {value}")
    print("Next: harvest, auto-repair needs_review, import changed profiles, then check counts.")


if __name__ == "__main__":
    main()
