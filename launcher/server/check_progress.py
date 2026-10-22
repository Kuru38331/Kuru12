"""Offline, read-only summary of the latest local test session."""
import json
from pathlib import Path

ROUTES = {
    '/live/player/authen': 'Login',
    '/live/player/inventory/getAll': 'Character inventory',
    '/live/player/characterslot/get': 'Read selection',
    '/live/player/characterslot/edit': 'Save selection',
    '/live/player/curserelic/get': 'Curse / Relic inventory',
    '/live/store/list': 'Skin store',
}


def summarize(path):
    records, invalid = [], 0
    if path.exists():
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError()
                    records.append(row)
                except (ValueError, UnicodeError):
                    invalid += 1
    # Earlier launches must not count as evidence for the current launch.
    starts = [i for i, row in enumerate(records)
              if row.get('route') == '/live/player/authen']
    if starts:
        records = records[starts[-1]:]
    result = []
    for route, label in ROUTES.items():
        rows = [r for r in records if r.get('route') == route]
        success = sum(type(r.get('response_status')) is int and
                      200 <= r['response_status'] < 300 for r in rows)
        failed = sum(type(r.get('response_status')) is int and
                     r['response_status'] >= 400 for r in rows)
        result.append(f'{label}: requests={len(rows)}, HTTP success={success}, errors={failed}')
    unknown = sum(r.get('route') == 'unknown' or r.get('response_status') == 501
                  for r in records)
    result += [f'Unimplemented requests: {unknown}', f'Unreadable records skipped: {invalid}',
               'HTTP success does not prove that the character changed inside the game.']
    return '\n'.join(result)


if __name__ == '__main__':
    print(summarize(Path(__file__).resolve().parent/'observations.jsonl'))
