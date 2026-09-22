"""Conservative source identity matching; ambiguity requires review."""
import re


def normalized(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value).casefold()).strip()


def identity_matches(name, title, franchise):
    if normalized(name) == normalized(title):
        return True
    suffix = {'marvel': 'Marvel Comics', 'dc': 'DC Comics', 'dc comics': 'DC Comics'}.get(str(franchise).casefold())
    return bool(suffix and normalized(title) == normalized(f'{name} ({suffix})'))


def origin_matches(franchise, origin):
    if not origin:
        return True  # Absence is not evidence of a different franchise.
    aliases={'shingeki no kyojin':'attack on titan','kimetsu no yaiba':'demon slayer','boku no hero academia':'my hero academia','dc comics':'dc','marvel comics':'marvel'}
    left=aliases.get(normalized(franchise),normalized(franchise))
    right=aliases.get(normalized(origin),normalized(origin))
    return bool(left and (left==right or set(left.split()) <= set(right.split())))
