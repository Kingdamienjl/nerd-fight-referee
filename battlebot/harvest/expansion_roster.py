"""Export legacy expansion seeds for evidence harvesting, without promoting them."""
import argparse
import csv
from pathlib import Path
import unicodedata

import yaml


def roster_rows(root: Path):
    seen = set()
    for path in sorted(root.rglob('*.yaml')):
        data = yaml.load(path.read_text(encoding='utf-8'), Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))
        if not isinstance(data, dict) or data.get('profile_status') != 'expansion_seed':
            continue
        name = data.get('name')
        franchise = data.get('franchise')
        category = data.get('category')
        if not all(isinstance(value, str) and value.strip() for value in (name, franchise, category)):
            continue
        values = [unicodedata.normalize('NFKC', value).strip() for value in (category, franchise, name)]
        key = tuple(value.casefold() for value in values)
        if key in seen:
            continue
        seen.add(key)
        yield dict(zip(('category', 'franchise', 'name'), values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    rows = list(roster_rows(args.root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects an existing curated roster or previous export.
    with args.output.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['category', 'franchise', 'name'])
        writer.writeheader()
        writer.writerows(rows)
    print(f'Exported {len(rows)} evidence-harvesting targets to {args.output}')


if __name__ == '__main__':
    main()
