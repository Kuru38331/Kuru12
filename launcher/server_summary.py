"""Whitelisted diagnostics only. Raw game requests are never exported."""
import json
from pathlib import Path

def safe_observations(path):
    from sys import path as search
    search.insert(0,str(Path(__file__).resolve().parent/'server'))
    from server import IMPLEMENTED
    rows=[]
    if Path(path).exists():
        with Path(path).open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row=json.loads(line);route=row.get('route')
                    code=row.get('response_status')
                    if route not in IMPLEMENTED and route!='/health':route='unknown'
                    if type(code) is int:rows.append({'route':route,'response_status':code})
                except (ValueError,UnicodeError,AttributeError):continue
    return rows[-200:]
