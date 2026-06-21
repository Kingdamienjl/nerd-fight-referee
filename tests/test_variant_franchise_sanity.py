
from pathlib import Path





DC_TOKENS = {

    "dc-comics",

    "post-crisis",

    "post-flashpoint",

    "rebirth",

    "new-52",

    "dceu",

}



MARVEL_TOKENS = {

    "marvel-comics",

    "earth-616",

    "marvel-cinematic-universe",

    "mcu",

}



COMIC_CONTINUITY_TOKENS = DC_TOKENS | MARVEL_TOKENS





def _parts(path: Path) -> tuple[str, str, str, str]:

    parts = path.as_posix().split("/")

    # profiles/generated/anime/dragon-ball/foo.yaml

    if len(parts) >= 5 and parts[0] == "profiles":

        return parts[1], parts[2], parts[3], path.stem

    return "", "", "", path.stem





def test_generated_profiles_do_not_mix_franchise_continuities():

    bad: list[str] = []



    for path in sorted(Path("profiles/generated").rglob("*.yaml")):

        _kind, category, franchise, slug = _parts(path)

        category = category.lower()

        franchise = franchise.lower()

        slug = slug.lower()



        for token in COMIC_CONTINUITY_TOKENS:

            if token in slug and category != "comic":

                bad.append(f"{path}: comic continuity token on non-comic profile: {token}")



        for token in DC_TOKENS:

            if token in slug and "dc" not in franchise:

                bad.append(f"{path}: DC continuity token outside DC franchise: {token}")



        for token in MARVEL_TOKENS:

            if token in slug and "marvel" not in franchise:

                bad.append(f"{path}: Marvel continuity token outside Marvel franchise: {token}")



        if franchise == "dragon-ball":

            for token in COMIC_CONTINUITY_TOKENS:

                if token in slug:

                    bad.append(f"{path}: Dragon Ball profile has comic continuity token: {token}")



    assert not bad, "Variant/franchise sanity failures:\n" + "\n".join(bad[:100])

