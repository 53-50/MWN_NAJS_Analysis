"""Gemeinsame Pfade, CSV-Helfer und bestätigte Blockzuordnung."""
from pathlib import Path
import json
import math
import re
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
OUT = ROOT / "output_analyse"
PLOTS = OUT / "plots"
PERSONS = [('Ahmet', 'A'), ('Nemanja', 'N')]
CONDITIONS = ['Baseline', 'Channel change', 'Foil shielding']
COLORS = dict(zip(CONDITIONS, ['#245580', '#119C86', '#DE8035']))
METRICS = [
    ('TCP', 'throughput_mbps', 'TCP throughput', 'Mbit/s'),
    ('UDP', 'jitter_ms', 'UDP jitter', 'ms'),
    ('UDP', 'loss_pct', 'UDP packet loss', 'percentage points'),
]

def mapping(n):
    if n == 1:
        return 'LAN', 'LAN', 'LAN'
    for start, condition, band in [
        (2, 'Baseline', '2.4 GHz'), (5, 'Baseline', '5 GHz'),
        (8, 'Channel change', '2.4 GHz'), (11, 'Channel change', '5 GHz'),
        (14, 'Foil shielding', '5 GHz')
    ]:
        if start <= n <= start + 2:
            return condition, band, f'TP{n-start+1}'
    raise ValueError(n)

def blocks():
    for person, prefix in PERSONS:
        for n in range(1, 17):
            condition, band, point = mapping(n)
            yield dict(person=person, block=f'{prefix}{n:02d}',
                       condition=condition, band=band, point=point)

def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def read_json(path):
    raw = path.read_bytes()
    # Windows PowerShell kann UTF-16-Dateien schreiben.
    encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    return json.loads(raw.decode(encoding))

def read_text(path):
    raw = path.read_bytes()
    for enc in (['utf-16'] if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ['utf-8-sig', 'cp1252']):
        try:
            return raw.decode(enc)
        except UnicodeError:
            pass
    raise ValueError('Text-Encoding nicht erkannt')

def write_csv(name, rows, columns=None):
    OUT.mkdir(exist_ok=True)
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows, columns=columns)
    frame.to_csv(OUT / name, sep=';', index=False, encoding='utf-8-sig')
    return frame

def read_csv(name):
    p = OUT / name
    try:
        return pd.read_csv(p, sep=';') if p.exists() else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

def stem(text):
    return re.sub(r'[^A-Za-z0-9_-]+', '_', text)
