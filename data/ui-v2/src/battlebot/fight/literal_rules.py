"""Apply explicit simulation prerequisites before deterministic scoring."""
from copy import deepcopy
import json
import re


def has_chakra(profile):
    # Require an explicit affirmative field/tag; mentions in attack descriptions
    # are not evidence that the target possesses the required resource.
    tags = profile.get("interaction_tags") or []
    if "has_chakra" in tags or "chakra_user" in tags:
        return True
    source = str(profile.get("power_source") or "").strip().casefold()
    return source in {"chakra", "chakra network", "chakra system"}


def apply_literal_rules(first, second, rules):
    first, second = deepcopy(first), deepcopy(second)
    if rules.get("energy_equalization"):
        return first, second
    if rules.get("genjutsu_requires_chakra", True):
        for attacker, target in ((first, second), (second, first)):
            if has_chakra(target):
                continue
            usable, blocked = [], []
            for ability in attacker.get("abilities") or []:
                if re.search(r"\bgenjutsu\b", json.dumps(ability), re.I):
                    blocked.append(ability)
                else:
                    usable.append(ability)
            attacker["abilities"] = usable
            if blocked:
                attacker["blocked_abilities"] = blocked
                attacker.setdefault("warnings", []).append({"code": "genjutsu_prerequisite_unconfirmed",
                    "message": "Genjutsu excluded: target chakra is not confirmed under simulation rules."})
    return first, second
