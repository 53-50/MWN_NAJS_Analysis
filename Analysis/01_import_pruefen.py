"""Liest ausschließlich erwartete Messläufe; Fehler bleiben im Prüfprotokoll."""
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
from common import *


def run():
    if not DATA.is_dir():
        raise FileNotFoundError(f'Datenordner fehlt: {DATA}')
    records, intervals, issues, files = [], [], [], []
    seen = set()
    for meta in blocks():
        folder = DATA / meta['person'] / meta['block']
        lookup = defaultdict(list)
        for p in folder.glob('*'):
            if p.is_file():
                lookup[p.name.lower()].append(p)
        for protocol in ['TCP', 'UDP']:
            for rep in [1, 2, 3]:
                name = f'{protocol}_Lauf_{rep}.json'
                row = dict(meta, protocol=protocol, run=rep, status='missing',
                           usable=False, throughput_mbps=None, jitter_ms=None,
                           loss_pct=None, lost_packets=None, packets=None,
                           seconds=None, reverse=None, target_mbps=None,
                           timestamp_vienna=None, start_hour=None, stream_count=None,
                           source='', receiver_source='')
                notes = []
                paths = lookup.get(name.lower(), [])
                try:
                    if not paths:
                        raise ValueError('Erwartete Datei fehlt')
                    if len(paths) != 1:
                        raise ValueError('Mehrdeutige Dateinamen')
                    path = paths[0]
                    seen.add(path.resolve())
                    row['source'] = str(path.relative_to(DATA))
                    d = read_json(path)
                    if d.get('error'):
                        raise ValueError(f"iperf3: {d['error']}")
                    params = d['start']['test_start']
                    if params.get('protocol') != protocol:
                        raise ValueError('Protokoll stimmt nicht mit Dateinamen überein')
                    receiver = d.get('end', {}).get('sum_received')
                    source = 'sum_received'
                    if not isinstance(receiver, dict):
                        # Ältere UDP-Ausgabe: nur explizit empfangsseitige Summe nutzen.
                        receiver = d.get('end', {}).get('sum')
                        source = 'sum'
                        if not isinstance(receiver, dict) or receiver.get('sender') is not False:
                            raise ValueError('Keine eindeutige Empfängersumme vorhanden')
                    if receiver.get('sender') is True:
                        raise ValueError('Ergebnissumme ist sendeseitig')
                    duration, bps = receiver.get('seconds'), receiver.get('bits_per_second')
                    if not number(duration) or duration <= 0 or not number(bps) or bps < 0:
                        raise ValueError('Ungültiger Durchsatz oder Messdauer')
                    row.update(status='ok', usable=True, seconds=duration,
                               throughput_mbps=bps / 1e6, reverse=params.get('reverse'),
                               stream_count=params.get('num_streams'), receiver_source=source)
                    target = params.get('target_bitrate')
                    row['target_mbps'] = target / 1e6 if number(target) else None
                    if not 29 <= duration <= 32:
                        row.update(status='duration_review', usable=False)
                        notes.append('Dauer außerhalb 29–32 s; vorerst von Kennwerten ausgeschlossen')
                    if params.get('reverse') != 1:
                        notes.append('Reverse ungleich 1; Downloadrichtung prüfen')
                    if params.get('bidir', 0):
                        row.update(status='direction_review', usable=False)
                        notes.append('Bidirektionaler Test statt unidirektionalem Download')
                    if params.get('omit', 0):
                        notes.append('Warm-up/omit gesetzt: Vergleichbarkeit prüfen')
                    if protocol == 'UDP':
                        for key, col in [('jitter_ms', 'jitter_ms'), ('lost_percent', 'loss_pct'),
                                         ('lost_packets', 'lost_packets'), ('packets', 'packets')]:
                            value = receiver.get(key)
                            valid = number(value) and value >= 0
                            if key == 'lost_percent':
                                valid = valid and value <= 100
                            if valid:
                                row[col] = value
                            else:
                                notes.append(f'{key} fehlt/ungültig; für diese Kennzahl ausgeschlossen')
                        if row['target_mbps'] != 10:
                            notes.append('UDP-Senderate weicht von 10 Mbit/s ab oder fehlt')
                    epoch = d.get('start', {}).get('timestamp', {}).get('timesecs')
                    if number(epoch):
                        dt = datetime.fromtimestamp(epoch, ZoneInfo('Europe/Vienna'))
                        row['timestamp_vienna'], row['start_hour'] = dt.isoformat(), dt.hour
                    for i, item in enumerate(d.get('intervals', [])):
                        s = item.get('sum', {})
                        if not s:
                            continue
                        intervals.append(dict(meta, protocol=protocol, run=rep,
                            interval=i, start_s=s.get('start'), end_s=s.get('end'),
                            throughput_mbps=s['bits_per_second']/1e6 if number(s.get('bits_per_second')) else None,
                            omitted=s.get('omitted', False), sender=s.get('sender'),
                            interpretation='interval side as stored; not an independent repetition'))
                except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
                    if paths:
                        row.update(status='error', usable=False)
                    notes.append(str(exc))
                row['notes'] = ' | '.join(notes)
                records.append(row)
                for note in notes:
                    issues.append(dict(meta, protocol=protocol, run=rep, note=note))
    for p in sorted(DATA.rglob('*')):
        if p.is_file():
            files.append(dict(path=str(p.relative_to(DATA)), bytes=p.stat().st_size,
                              used_as_iperf_run=p.resolve() in seen))
    write_csv('01_runs.csv', records)
    write_csv('01_intervals.csv', intervals)
    write_csv('01_issues.csv', issues)
    write_csv('01_file_inventory.csv', files)
    write_csv('00_block_mapping.csv', list(blocks()))
    good = sum(r['usable'] for r in records)
    print(f'Import: {good}/192 auswertbare Läufe; {len(issues)} Hinweise. Siehe 01_issues.csv')

if __name__ == '__main__':
    run()
