"""MNW Gesamtauswertung – diese eine Datei in PyCharm ausführen.
Installation im Projekt-Terminal: python -m pip install pandas numpy matplotlib tzdata
Sucht data neben dem Skript oder eine Ebene darüber. Optional DATA_OVERRIDE setzen.
Liest Rohdaten direkt; falls keine vorhanden, kann die frühere Einzelwerte.csv dienen.
Ergebnisse: output_gesamt neben diesem Skript. Keine common.py/run_all.py nötig.
Rohdaten bleiben unverändert. Fehlende Werte werden nie als null ergänzt.
Diagramme/Statistiken sind deskriptiv; drei Läufe erlauben keine Kausalitätsbehauptung.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


"""Gemeinsame Pfade, CSV-Helfer und bestätigte Blockzuordnung."""
from pathlib import Path
import json
import math
import re
import pandas as pd

# Optional: absoluten Datenpfad eintragen; sonst automatische Suche.
DATA_OVERRIDE = None  # z.B. r"C:\Users\Zera\PycharmProjects\MWN_NAJS_Analysis\data"
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR
# Unterstützt Skript direkt im Projekt und im Unterordner Analysis.
_candidates = [SCRIPT_DIR / 'data', SCRIPT_DIR.parent / 'data']
DATA = Path(DATA_OVERRIDE) if DATA_OVERRIDE else next(
    (p for p in _candidates if p.is_dir()), _candidates[0])
OUT = SCRIPT_DIR / 'output_gesamt'
# False: zentrale Ergebnisplots und zwei Signal-Zeitverlaufsübersichten. True: zusätzlich alle bisherigen Plots.
ALLE_DIAGRAMME = False
PLOTS = OUT / ('plots_alle' if ALLE_DIAGRAMME else 'plots_auswahl')
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


"""Liest ausschließlich erwartete Messläufe; Fehler bleiben im Prüfprotokoll."""
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict



def step_1():
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



"""Deskriptive Kennwerte, Effekte und LAN-Einordnung; keine Signifikanztests."""


KEYS = ['person', 'block', 'condition', 'band', 'point', 'protocol']

def step_2():
    all_runs = read_csv('01_runs.csv')
    if all_runs.empty:
        raise RuntimeError('Zuerst 01_import_pruefen.py ausführen')
    df = all_runs[all_runs['usable'] == True].copy()
    stats = []
    for key, group in all_runs.groupby(KEYS, dropna=False):
        valid = group[group['usable'] == True]
        for protocol, metric, title, unit in METRICS:
            if key[-1] != protocol:
                continue
            x = valid[metric].dropna()
            stats.append(dict(zip(KEYS, key), metric=metric, title=title, unit=unit,
                n=len(x), expected_n=3, complete=len(x)==3,
                mean=x.mean(), sd=x.std(ddof=1), median=x.median(),
                minimum=x.min(), maximum=x.max(),
                q25=x.quantile(.25), q75=x.quantile(.75),
                iqr=x.quantile(.75)-x.quantile(.25), range_value=x.max()-x.min(),
                cv_pct=(x.std(ddof=1)/x.mean()*100 if len(x)>1 and x.mean()!=0 else None)))
    summary = write_csv('02_summary.csv', stats)
    effects = []
    for _, new in summary[summary['condition'].isin(CONDITIONS[1:])].iterrows():
        base = summary[(summary['person']==new['person']) &
            (summary['band']==new['band']) & (summary['point']==new['point']) &
            (summary['metric']==new['metric']) & (summary['condition']=='Baseline')]
        if base.empty:
            continue
        b = base.iloc[0]
        delta = new['mean'] - b['mean']
        relative = delta/b['mean']*100 if pd.notna(b['mean']) and b['mean']!=0 else None
        effects.append(dict(person=new['person'], band=new['band'], point=new['point'],
            intervention=new['condition'], metric=new['metric'], baseline_mean=b['mean'],
            intervention_mean=new['mean'], delta=delta, delta_unit=new['unit'],
            relative_change_pct=relative, baseline_n=b['n'], intervention_n=new['n'],
            baseline_sd=b['sd'], intervention_sd=new['sd'],
            complete=bool(b['complete'] and new['complete'])))
    write_csv('02_baseline_effects.csv', effects)
    # Paketgewichtete Verlustquote zusätzlich zum arithmetischen Mittel der drei Quoten.
    weighted=[]
    for key,g in df[df['protocol']=='UDP'].groupby(KEYS):
        g=g.dropna(subset=['lost_packets','packets'])
        packets=g['packets'].sum()
        weighted.append(dict(zip(KEYS,key), n=len(g), packets=packets,
            lost_packets=g['lost_packets'].sum(),
            weighted_loss_pct=100*g['lost_packets'].sum()/packets if packets>0 else None))
    write_csv('02_udp_weighted_loss.csv', weighted)
    lan=[]
    tcp=summary[summary.metric=='throughput_mbps']
    for person,g in tcp.groupby('person'):
        ref=g[g.condition=='LAN']
        if ref.empty or not (ref.iloc[0]['mean']>0):
            continue
        r=ref.iloc[0]
        for _,v in g[g.condition!='LAN'].iterrows():
            lan.append(dict(person=person, block=v['block'], condition=v['condition'],
                band=v['band'], point=v['point'], wlan_mean_mbps=v['mean'],
                lan_mean_mbps=r['mean'], wlan_to_lan_pct=100*v['mean']/r['mean'],
                note='Einordnung, keine bewiesene WLAN-Effizienz oder Hardwaregrenze'))
    write_csv('02_lan_context.csv',lan)
    # Vergleichsparameter pro Bedingung; Warnungen bei unterschiedlichen Lasten/Richtungen.
    checks=[]
    for key,g in df.groupby(['person','protocol']):
        for field in ['reverse','target_mbps','stream_count']:
            if field=='target_mbps' and key[1]!='UDP':
                continue
            vals=sorted(g[field].dropna().unique().tolist())
            checks.append(dict(person=key[0],protocol=key[1],parameter=field,
                values=str(vals),missing=int(g[field].isna().sum()),
                review=len(vals)!=1 or g[field].isna().any()))
    write_csv('02_parameter_checks.csv',checks)
    print('Kennwerte, Baseline-Effekte und Parameterprüfung erstellt.')



"""Vergleiche und Heatmaps als PNG/SVG; Einzelwerte und n bleiben sichtbar."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np



def save(fig,name):
    if not ALLE_DIAGRAMME and not (name.startswith('01_vergleich_') or name == '02_heatmap_throughput_mbps' or name.startswith('04_signalverlauf_') or name.startswith('11_deskriptiv_') or name.startswith('13_')):
        plt.close(fig)
        return
    PLOTS.mkdir(exist_ok=True,parents=True)
    for ext in ['png','svg']:
        fig.savefig(PLOTS/f'{stem(name)}.{ext}',dpi=220,bbox_inches='tight')
    plt.close(fig)


def step_3():
    df=read_csv('01_runs.csv'); summary=read_csv('02_summary.csv')
    effects=read_csv('02_baseline_effects.csv')
    if df.empty or summary.empty:
        raise RuntimeError('Zuerst Import und Vergleiche ausführen')
    df=df[df.usable==True]
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    # Einheitliche Achsen pro Band/Kennzahl über beide Wohnungen.
    for person in [p for p,_ in PERSONS]:
        for band in ['2.4 GHz','5 GHz']:
            conditions=CONDITIONS if band=='5 GHz' else CONDITIONS[:2]
            fig,axes=plt.subplots(1,3,figsize=(16,5.1),layout='constrained')
            offsets=np.linspace(-.23,.23,len(conditions))
            for ax,(protocol,metric,title,unit) in zip(axes,METRICS):
                for offset,condition in zip(offsets,conditions):
                    for i,point in enumerate(['TP1','TP2','TP3']):
                        g=df[(df.person==person)&(df.band==band)&(df.point==point)&
                             (df.condition==condition)&(df.protocol==protocol)]
                        x=g[metric].dropna(); pos=i+offset
                        if x.empty:
                            ax.text(pos,.03,'n=0',transform=ax.get_xaxis_transform(),ha='center',fontsize=8)
                            continue
                        ax.scatter(pos+np.linspace(-.035,.035,len(x)),x,color=COLORS[condition],alpha=.6,s=27,zorder=3)
                        ax.errorbar(pos,x.mean(),yerr=x.std(ddof=1) if len(x)>1 else None,
                            fmt='D',color=COLORS[condition],capsize=4,ms=6,zorder=4)
                        ax.annotate(f'n={len(x)}',(pos,x.max()),xytext=(0,9),
                            textcoords='offset points',ha='center',fontsize=8)
                s=summary[(summary.band==band)&(summary.metric==metric)]
                upper=(s['mean']+s['sd'].fillna(0)).max()
                raw=df.loc[(df.band==band)&(df.protocol==protocol),metric].max()
                ymax=max(upper if pd.notna(upper) else 0,raw if pd.notna(raw) else 0)
                ax.set_ylim(0,ymax*1.28 if ymax>0 else 1)
                ax.set_xticks(range(3),['TP1','TP2','TP3']); ax.set_xlim(-.5,2.5)
                ax.set_title(title); ax.set_ylabel('%' if metric=='loss_pct' else unit)
                ax.grid(axis='y',alpha=.2)
            axes[0].legend(handles=[Line2D([0],[0],marker='D',ls='',color=COLORS[c],label=c) for c in conditions],fontsize=9)
            fig.suptitle(f'{person} | {band}\nIndividual runs and mean ±1 SD; descriptive results',fontsize=16)
            save(fig,f'01_vergleich_{person}_{band}')
    if not effects.empty:
        for protocol,metric,title,unit in METRICS:
            g=effects[effects.metric==metric].copy()
            if g.empty:
                continue
            g['label']=g.person+' | '+g.band+' | '+g.intervention
            field='relative_change_pct' if protocol=='TCP' else 'delta'
            matrix=g.pivot(index='label',columns='point',values=field).reindex(columns=['TP1','TP2','TP3'])
            arr=matrix.to_numpy(dtype=float); finite=arr[np.isfinite(arr)]
            limit=max(abs(finite)) if finite.size else 1
            limit=limit or 1
            cmap=plt.get_cmap('RdBu' if protocol=='TCP' else 'RdBu_r').copy(); cmap.set_bad('#EEEEEE')
            fig,ax=plt.subplots(figsize=(11,5),layout='constrained')
            im=ax.imshow(np.ma.masked_invalid(arr),aspect='auto',cmap=cmap,vmin=-limit,vmax=limit)
            for i,label in enumerate(matrix.index):
                for j,point in enumerate(matrix.columns):
                    v=arr[i,j]; match=g[(g.label==label)&(g.point==point)]
                    incomplete=not match.empty and not bool(match.iloc[0]['complete'])
                    labeltext='n/a' if not np.isfinite(v) else f'{v:+.2f}'+('*' if incomplete else '')
                    ax.text(j,i,labeltext,ha='center',va='center',color='white' if np.isfinite(v) and abs(v)>.55*limit else 'black')
            ax.set_xticks(range(3),matrix.columns);ax.set_yticks(range(len(matrix)),matrix.index)
            units='%' if protocol=='TCP' else unit
            ax.set_title(f'{title}: change vs own baseline ({units})\nBlue = improvement; red = deterioration; * fewer than 3 valid runs',pad=14)
            fig.colorbar(im,ax=ax,shrink=.8);save(fig,f'02_heatmap_{metric}')
    # TP3 im Verhältnis zu TP1: Ortsvergleich, nicht Änderung der Versorgungsgrenze.
    s=summary[(summary.metric=='throughput_mbps')&(summary.band!='LAN')]
    rows=[]
    for key,g in s.groupby(['person','band','condition']):
        a=g[g.point=='TP1'];b=g[g.point=='TP3']
        if len(a) and len(b) and a.iloc[0]['mean']>0:
            rows.append(dict(person=key[0],band=key[1],condition=key[2],
                tp3_to_tp1_pct=100*b.iloc[0]['mean']/a.iloc[0]['mean']))
    write_csv('03_tp3_retention.csv',rows)
    if rows:
        r=pd.DataFrame(rows);r['label']=r.person+' | '+r.band+' | '+r.condition
        fig,ax=plt.subplots(figsize=(11,6),layout='constrained')
        ax.barh(r.label,r.tp3_to_tp1_pct,color=[COLORS[c] for c in r.condition])
        ax.axvline(100,color='gray',ls='--');ax.set_xlabel('TCP throughput at TP3 / TP1 (%)')
        ax.set_title('Throughput retained at the most distant test point\nNot a measurement of how far the coverage edge moved')
        save(fig,'03_tp3_throughput_retention')
    print(f'Diagramme: {PLOTS}')



"""Ergänzende Daten; unbekannte Ping-Formate werden ausdrücklich gekennzeichnet."""
import re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt



def parse_ping(text):
    # Windows-Ping Deutsch/Englisch, keine RTT aus TTL oder Zusammenfassung ableiten.
    sent=re.search(r'(?:Gesendet|Sent)\s*=\s*(\d+)',text,re.I)
    received=re.search(r'(?:Empfangen|Received)\s*=\s*(\d+)',text,re.I)
    lost=re.search(r'(?:Verloren|Lost)\s*=\s*(\d+)',text,re.I)
    samples=[]
    for line in text.splitlines():
        if not re.search(r'\bTTL\s*=',line,re.I):
            continue
        m=re.search(r'(?:Zeit|time)\s*([=<])\s*([\d.,]+)\s*ms',line,re.I)
        if m:
            samples.append((float(m[2].replace(',','.')),m[1]=='<'))
    result=dict(sent=int(sent[1]) if sent else None,
                received=int(received[1]) if received else None,
                lost=int(lost[1]) if lost else None,
                parsed_replies=len(samples),
                less_than_samples=sum(c for _,c in samples),
                status='ok' if sent and received and lost else 'format_review')
    result['loss_pct']=100*result['lost']/result['sent'] if result['sent'] and result['lost'] is not None else None
    vals=np.array([v for v,_ in samples],dtype=float)
    result['rtt_mean_upper_bound_ms']=float(vals.mean()) if len(vals) else None
    result['rtt_p95_upper_bound_ms']=float(np.percentile(vals,95)) if len(vals) else None
    # <1 ms wird nur als obere Grenze 1 ms behandelt, nicht als exakte 1 ms.
    for pattern,key in [(r'(?:Mittelwert|Average)\s*=\s*([\d.,]+)\s*ms','reported_mean_ms'),
                        (r'(?:Minimum)\s*=\s*([\d.,]+)\s*ms','reported_min_ms'),
                        (r'(?:Maximum)\s*=\s*([\d.,]+)\s*ms','reported_max_ms')]:
        m=re.search(pattern,text,re.I);result[key]=float(m[1].replace(',','.')) if m else None
    return result


def step_4():
    pings,signals,samples=[],[],[]
    PLOTS.mkdir(parents=True,exist_ok=True)
    for meta in blocks():
        folder=DATA/meta['person']/meta['block']
        candidates=[p for p in folder.glob('*') if p.name.lower()=='ping_ergebnis.txt']
        row=dict(meta,status='missing')
        if candidates:
            try:
                row.update(parse_ping(read_text(candidates[0])))
                if row['sent'] is not None and row['sent']!=100:
                    row['status']='count_review'
            except (OSError,ValueError) as e:
                row.update(status='error',note=str(e))
        pings.append(row)
        candidates=[folder/f"{meta['block']}.json",
            DATA/meta['person']/'Signalstärke'/f"{meta['block']}.json"]
        candidates=[p for p in candidates if p.exists()]
        row=dict(meta,status='missing',source='',sample_count=0,
            signal_mean_pct=None,signal_min_pct=None,signal_max_pct=None,
            signal_n=0,signal_median_pct=None,signal_sd_pct=None,
            log_start_s=None,log_end_s=None,
            rssi_median_dbm=None,rssi_min_dbm=None,rssi_max_dbm=None,
            rssi_unique_count=0,note='')
        if candidates:
            path=candidates[0];row['source']=str(path.relative_to(DATA))
            try:
                points=read_json(path)['datenpunkte']
                for point in points:
                    samples.append(dict(meta,**{k:point.get(k) for k in ['sekunde','signal_prozent','rssi_dbm']}))
                s=[p['signal_prozent'] for p in points if number(p.get('signal_prozent')) and 0<=p['signal_prozent']<=100]
                r=[p['rssi_dbm'] for p in points if number(p.get('rssi_dbm')) and -127<=p['rssi_dbm']<0]
                row.update(status='review_source',sample_count=len(points),
                    signal_mean_pct=np.mean(s) if s else None,
                    signal_n=len(s),signal_median_pct=np.median(s) if s else None,
                    signal_sd_pct=np.std(s,ddof=1) if len(s)>1 else None,
                    log_start_s=min([p['sekunde'] for p in points if number(p.get('sekunde'))],default=None),
                    log_end_s=max([p['sekunde'] for p in points if number(p.get('sekunde'))],default=None),
                    signal_min_pct=min(s) if s else None,signal_max_pct=max(s) if s else None,
                    rssi_median_dbm=np.median(r) if r else None,
                    rssi_min_dbm=min(r) if r else None,rssi_max_dbm=max(r) if r else None,
                    rssi_unique_count=len(set(r)))
                notes=['RSSI-Herkunft und zeitliche Zuordnung zu Läufen nicht verifiziert']
                if len(set(r))==1 and len(set(s))>1:
                    notes.append('RSSI konstant trotz veränderlicher Prozentwerte; Erfassung prüfen')
                if meta['band']=='LAN':
                    notes.append('Signalwerte bei LAN-Referenz nicht als LAN-Metrik interpretieren')
                if len(candidates)>1:
                    notes.append('Zwei Signaldateien vorhanden; erste verwendet, Duplikat prüfen')
                row['note']=' | '.join(notes)
                if ALLE_DIAGRAMME and meta['band']!='LAN' and points:
                    fig,ax=plt.subplots(figsize=(9,3.6),layout='constrained')
                    t=[p.get('sekunde',np.nan) for p in points]
                    values=[p.get('signal_prozent',np.nan) for p in points]
                    ax.plot(t,values,color='#245580');ax.set_ylim(0,100)
                    ax.set_xlabel('Elapsed time in signal log (s)');ax.set_ylabel('Signal (%)')
                    ax.set_title(f"{meta['person']} {meta['block']} | {meta['band']} | {meta['point']}\nSignal quality as logged; not aligned to individual iperf runs")
                    for ext in ['png','svg']:
                        fig.savefig(PLOTS/f"04_signal_{meta['block']}.{ext}",dpi=180)
                    plt.close(fig)
            except (OSError,ValueError,KeyError,TypeError) as e:
                row.update(status='error',note=str(e))
        signals.append(row)
    write_csv('04_ping_summary.csv',pings)
    write_csv('04_signal_summary.csv',signals)
    write_csv('04_signal_samples.csv',samples)
    print('Ping und Signal ausgewertet; Hinweise in 04_*_summary.csv beachten.')



"""Erstellt einen vollständigen deskriptiven Textbericht und Zeitprüfung."""


QUESTION='Wie verändern sich TCP-Durchsatz, UDP-Jitter und Paketverlust gegenüber der jeweiligen Ausgangskonfiguration bei einem WLAN-Kanalwechsel und einer zusätzlichen Abschirmung in zwei unterschiedlichen Wohnumgebungen, wenn die Messsessions jeweils ab 22 Uhr beginnen?'

def fmt(v):
    return f'{v:.3f}' if pd.notna(v) else 'nicht verfügbar'


def step_5():
    runs=read_csv('01_runs.csv');effects=read_csv('02_baseline_effects.csv')
    summary=read_csv('02_summary.csv');checks=read_csv('02_parameter_checks.csv')
    if runs.empty:
        raise RuntimeError('Zuerst den Import ausführen')
    lines=['# MNW Auswertung', '', QUESTION,'',
        '## Datenqualität',f'- Erwartete Läufe: {len(runs)}',
        f'- Auswertbar laut Import: {int((runs.usable==True).sum())}',
        f'- Fehlend: {int((runs.status=="missing").sum())}',
        f'- Fehler oder Prüffälle: {int((~runs.status.isin(["ok","missing"])).sum())}',
        '- Fehler und fehlende Dateien werden nicht durch Nullwerte ersetzt.',
        '- n wird pro Kennzahl gezählt; abweichende Dauer (außerhalb 29–32 s) wird vorläufig ausgeschlossen.',
        '- Warnungen zu Last, Richtung, Streams und Messparametern müssen vor dem Interpretieren geprüft werden.',
        '', '## Alle Baseline-Vergleiche',
        'Änderung = Mittelwert Intervention minus Mittelwert Baseline. Keine gepaarten Läufe vorausgesetzt.',
        'Durchsatz: positiv günstiger. Jitter/Verlust: negativ günstiger. Keine Signifikanzbehauptung.','']
    if not effects.empty:
        for _,r in effects.iterrows():
            relative=f"; relativ {fmt(r.relative_change_pct)} %" if r.metric=='throughput_mbps' else ''
            lines.append(f"- {r.person} | {r.band} | {r.point} | {r.intervention} | {r.metric}: "
                f"{fmt(r.baseline_mean)} → {fmt(r.intervention_mean)}; "
                f"Δ {fmt(r.delta)} {r.delta_unit}{relative}; "
                f"n={int(r.baseline_n)}/{int(r.intervention_n)} (Baseline/Intervention).")
    lines += ['', '## Parameterprüfung']
    if not checks.empty:
        for _,r in checks.iterrows():
            lines.append(f'- {r.person}/{r.protocol}: {r.parameter}={r["values"]}; fehlend={r["missing"]}; prüfen={r.review}')
    times=runs[['person','block','protocol','run','timestamp_vienna','start_hour']].copy()
    write_csv('05_run_times.csv',times)
    lines += ['', '## Zeitfenster ab 22 Uhr',
        'Die Startzeiten einzelner Tests stehen in 05_run_times.csv (Europe/Vienna, sofern Epoch-Zeit vorhanden).',
        'Das ist kein Nachweis des Sessionbeginns: Eine ab 22 Uhr begonnene Session kann nach Mitternacht fortgesetzt werden.',
        'Sessiongrenzen sind anhand der eigenen Messprotokolle zu prüfen; Uhrzeit wird nicht als experimentell getesteter Einfluss interpretiert.',
        '', '## Hinweise zur Schlussfolgerung',
        '- Ergebnisse zunächst innerhalb jeder Wohnung vergleichen. Hardware- und Umweltunterschiede sind vermischt.',
        '- Drei zeitnah aufeinanderfolgende Läufe sind keine drei unabhängigen Messabende.',
        '- ±1 SD zeigt Streuung und keine statistische Signifikanz oder Konfidenzintervalle.',
        '- UDP bewertet die Qualität bei der protokollierten Senderate, nicht die maximale Kapazität.',
        '- Ein kleiner Baseline-Durchsatz kann sehr große relative Änderungen erzeugen; absolute Werte immer mitberichten.',
        '- Ein fester TP3 zeigt die Leistung an diesem Ort, nicht wie viele Meter eine Versorgungsgrenze verschoben wurde.',
        '- Signalzeitreihen sind ohne gemeinsame Zeitreferenz keinem einzelnen TCP-/UDP-Lauf sicher zuzuordnen.',
        '- RSSI-Herkunft prüfen; Prozentwerte nicht ohne belegte Umrechnung als dBm behandeln.',
        '- Keine synthetischen Ergebnisse oder automatisch als bewiesen formulierten Conclusions.',
        '', '## Dateien',
        '01_* Rohimport und Prüfung; 02_* Kennwerte und Effekte; 03_* TP3; 04_* Ping/Signal; plots/* Diagramme.',
        'Ping: Bei Antworten <1 ms beruhen Stichprobenmittel/P95 auf oberen Grenzen; die Windows-Zusammenfassung wird separat gespeichert.']
    (OUT/'05_Auswertungsbericht.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Bericht: {OUT / "05_Auswertungsbericht.md"}')



"""Sekundenintervalle als Diagnostik; nicht als unabhängige Wiederholungen."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt



def step_6():
    d=read_csv('01_intervals.csv')
    if d.empty:
        print('Keine Intervallwerte vorhanden.');return
    PLOTS.mkdir(exist_ok=True,parents=True)
    for (person,band,condition),g in d[(d.protocol=='TCP')&(d.band!='LAN')].groupby(['person','band','condition']):
        fig,axes=plt.subplots(1,3,figsize=(14,4),layout='constrained')
        for ax,point in zip(axes,['TP1','TP2','TP3']):
            for rep,x in g[g.point==point].groupby('run'):
                x=x[x.omitted!=True].sort_values('end_s')
                ax.plot(x.end_s,x.throughput_mbps,label=f'Run {rep}',lw=1.5)
            ax.set_title(point);ax.set_xlabel('Elapsed time (s)');ax.set_ylabel('Mbit/s');ax.set_ylim(bottom=0)
            if len(g[g.point==point]):ax.legend(fontsize=8)
        fig.suptitle(f'{person} | {band} | {condition}\nTCP interval sums as stored (sender/receiver side in CSV); diagnostics only')
        for ext in ['png','svg']:
            fig.savefig(PLOTS/f'05_{stem(person+band+condition)}_intervals.{ext}',dpi=180)
        plt.close(fig)
    print('TCP-Zeitverläufe erstellt (Seite der Intervallsumme siehe 01_intervals.csv).')



def csv_fallback():
    """Frühere Exportdatei verwenden, wenn kein Rohdatenordner vorhanden ist."""
    candidates=[SCRIPT_DIR/'output'/'Einzelwerte.csv',
        SCRIPT_DIR.parent/'output'/'Einzelwerte.csv',SCRIPT_DIR/'Einzelwerte.csv']
    source=next((p for p in candidates if p.is_file()),None)
    if source is None:
        raise FileNotFoundError(
            f'Kein Datenordner gefunden: {DATA}\n'
            'Setze DATA_OVERRIDE oben im Skript oder lege data neben das Skript.\n'
            'Alternativ wird output/Einzelwerte.csv im Projekt gesucht.')
    original=pd.read_csv(source,sep=';')
    rename={'Person':'person','Block':'block','Protokoll':'protocol','Lauf':'run',
        'Dauer_s':'seconds','Reverse':'reverse','Senderate_Mbit_s':'target_mbps',
        'Durchsatz_Mbit_s':'throughput_mbps','Jitter_ms':'jitter_ms',
        'Paketverlust_Prozent':'loss_pct'}
    original=original.rename(columns=rename)
    for c in ['person','block','protocol','run','throughput_mbps']:
        if c not in original:raise ValueError(f'CSV-Spalte fehlt: {c}')
    original['block']=original.block.astype(str).str.upper()
    original['protocol']=original.protocol.astype(str).str.upper()
    original['run']=pd.to_numeric(original.run,errors='coerce')
    if original.duplicated(['person','block','protocol','run']).any():
        raise ValueError('Doppelte Messläufe im CSV. Vor Zusammenfassung prüfen.')
    records=[];issues=[]
    for meta in blocks():
        for protocol in ['TCP','UDP']:
            for rep in [1,2,3]:
                matches=original[(original.person==meta['person'])&
                    (original.block==meta['block'])&(original.protocol==protocol)&(original.run==rep)]
                row=dict(meta,protocol=protocol,run=rep,status='missing',usable=False,
                    throughput_mbps=None,jitter_ms=None,loss_pct=None,
                    lost_packets=None,packets=None,seconds=None,reverse=None,
                    target_mbps=None,timestamp_vienna=None,start_hour=None,
                    stream_count=None,source=str(source),notes='CSV-Fallback: Rohdaten nicht erneut prüfbar')
                if not matches.empty:
                    src=matches.iloc[0]
                    for c in ['throughput_mbps','jitter_ms','loss_pct','seconds','reverse','target_mbps']:
                        value=pd.to_numeric(src.get(c),errors='coerce')
                        row[c]=value if pd.notna(value) else None
                    if number(row['throughput_mbps']) and row['throughput_mbps']>=0:
                        row.update(status='ok',usable=True)
                    else:row['status']='error'
                    for c in ['jitter_ms','loss_pct']:
                        value=row[c]
                        if value is not None and (value<0 or (c=='loss_pct' and value>100)):
                            row[c]=None
                    if row['seconds'] is not None and not 29<=row['seconds']<=32:
                        row.update(status='duration_review',usable=False)
                records.append(row)
                if not row['usable']:issues.append(dict(meta,protocol=protocol,run=rep,note=row['status']))
    write_csv('01_runs.csv',records);write_csv('01_issues.csv',issues)
    write_csv('00_block_mapping.csv',list(blocks()))
    # Alte Intervall-Exporte nicht versehentlich mit neuen CSV-Daten mischen.
    write_csv('01_intervals.csv',[])
    print(f'CSV-Fallback: {source}. Ping, Signal und Testzeitpunkte sind damit nicht auswertbar.')


def extra_plots():
    summary=read_csv('02_summary.csv');runs=read_csv('01_runs.csv')
    effects=read_csv('02_baseline_effects.csv')
    tcp=summary[(summary.metric=='throughput_mbps')&(summary.band!='LAN')]
    persons=['Ahmet','Nemanja'];person_colors={'Ahmet':'#245580','Nemanja':'#DE8035'}
    points=['TP1','TP2','TP3']
    # Bisheriger wohnungsübergreifender Baseline-Plot bleibt erhalten.
    for band in ['2.4 GHz','5 GHz']:
        fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained')
        for ax,(protocol,metric,title,unit) in zip(axes,METRICS):
            for person,offset in zip(persons,[-.12,.12]):
                for x,point in enumerate(points):
                    v=runs.loc[(runs.usable==True)&(runs.person==person)&(runs.band==band)&
                        (runs.point==point)&(runs.protocol==protocol)&(runs.condition=='Baseline'),metric].dropna()
                    if v.empty:continue
                    pos=x+offset
                    ax.scatter(pos+np.linspace(-.025,.025,len(v)),v,color=person_colors[person],alpha=.5)
                    ax.errorbar(pos,v.mean(),yerr=v.std(ddof=1) if len(v)>1 else None,
                        fmt='D',color=person_colors[person],capsize=4,label=person if x==0 else None)
                    ax.annotate(f'n={len(v)}',(pos,v.max()),xytext=(0,8),textcoords='offset points',ha='center',fontsize=8)
            ax.set_xticks(range(3),points);ax.set_xlim(-.5,2.5);ax.set_ylim(bottom=0)
            ax.margins(y=.22);ax.set_title(title);ax.set_ylabel('%' if metric=='loss_pct' else unit)
            ax.grid(axis='y',alpha=.2)
        handles=[Line2D([0],[0],marker='D',ls='',color=person_colors[p],label=p) for p in persons]
        axes[0].legend(handles=handles)
        fig.suptitle(f'Baseline comparison | {band}\nMean ±1 SD and individual runs; different hardware and locations')
        save(fig,f'06_baseline_wohnungen_{band}')
    # Neuer Bandvergleich: Verhältnis von Mittelwerten, keine Run-Paarung.
    ratios=[]
    for (person,condition,point),g in tcp[tcp.condition.isin(CONDITIONS[:2])].groupby(['person','condition','point']):
        a=g[g.band=='2.4 GHz'];b=g[g.band=='5 GHz']
        if a.empty or b.empty:continue
        a,b=a.iloc[0],b.iloc[0]
        ratios.append(dict(person=person,condition=condition,point=point,
            mean_24_mbps=a['mean'],mean_5_mbps=b['mean'],n_24=a['n'],n_5=b['n'],
            factor_5_vs_24=b['mean']/a['mean'] if a['mean']>0 else None))
    ratio=write_csv('07_bandvergleich.csv',ratios)
    if not ratio.empty:
        fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True,layout='constrained')
        for ax,person in zip(axes,persons):
            for cond,offset in zip(CONDITIONS[:2],[-.17,.17]):
                g=ratio[(ratio.person==person)&(ratio.condition==cond)].set_index('point').reindex(points)
                x=np.arange(3)+offset;ax.bar(x,g.factor_5_vs_24,width=.3,color=COLORS[cond],label=cond)
                for pos,(_,r) in zip(x,g.iterrows()):
                    v=r.factor_5_vs_24
                    if pd.notna(v):
                        mark='*' if r.n_24<3 or r.n_5<3 else ''
                        ax.annotate(f'{v:.2f}×{mark}',(pos,v),xytext=(0,5),textcoords='offset points',ha='center')
                    else:ax.text(pos,.03,'n/a',transform=ax.get_xaxis_transform(),ha='center')
            ax.axhline(1,color='gray',ls='--');ax.set_title(person);ax.set_xticks(range(3),points)
            ax.set_ylabel('TCP mean 5 GHz / mean 2.4 GHz');ax.grid(axis='y',alpha=.2);ax.margins(y=.22)

        finite=ratio.factor_5_vs_24.dropna()
        ymax=max(1.0,finite.max() if len(finite) else 1.0)*1.5
        for ax in axes:ax.set_ylim(0,ymax)
        axes[0].legend(loc='upper left');fig.suptitle('Band advantage across test points\nRatio of means; 1 = equal throughput; * incomplete repetitions')
        save(fig,'07_bandvergleich')
    # TCP-Streuung: CV nur bei positivem Mittelwert; n<2 keine Aussage.
    fig,axes=plt.subplots(1,2,figsize=(13,5),sharey=True,layout='constrained')
    for ax,person in zip(axes,persons):
        for band,ls in [('2.4 GHz','--'),('5 GHz','-')]:
            for condition in CONDITIONS:
                g=tcp[(tcp.person==person)&(tcp.band==band)&(tcp.condition==condition)].set_index('point').reindex(points)
                if g['n'].notna().sum()==0:continue
                y=g.cv_pct.where(g['n']>=2)
                ax.plot(range(3),y,marker='o',ls=ls,color=COLORS[condition],label=f'{band} | {condition}')
        ax.set_title(person);ax.set_xticks(range(3),points);ax.set_ylim(bottom=0)
        ax.set_ylabel('TCP coefficient of variation (%)');ax.grid(axis='y',alpha=.2)
        ax.legend(fontsize=8)
    fig.suptitle('Variation between repeated TCP runs\nSD / mean × 100; descriptive only; unstable near zero mean')
    save(fig,'08_tcp_streuung_cv')
    # Effektvergleich als divergende Balken, zusätzlich zu Heatmaps.
    if not effects.empty:
        for protocol,metric,title,unit in METRICS:
            for condition in CONDITIONS[1:]:
                g=effects[(effects.metric==metric)&(effects.intervention==condition)]
                if g.empty:continue
                bands=['2.4 GHz','5 GHz'] if condition=='Channel change' else ['5 GHz']
                fig,axes=plt.subplots(1,len(bands),figsize=(6*len(bands),4.8),squeeze=False,layout='constrained')
                for ax,band in zip(axes.flat,bands):
                    for person,offset in zip(persons,[-.16,.16]):
                        rows=g[(g.person==person)&(g.band==band)].set_index('point').reindex(points)
                        # TCP relativ, UDP immer absolute Änderung (ms/Prozentpunkte).
                        field='relative_change_pct' if protocol=='TCP' else 'delta'
                        vals=rows[field];positions=np.arange(3)+offset
                        ax.bar(positions,vals,width=.28,color=person_colors[person],label=person)
                        for pos,(_,r) in zip(positions,rows.iterrows()):
                            v=r[field]
                            if pd.notna(v):
                                mark='*' if r.baseline_n<3 or r.intervention_n<3 else ''
                                ax.annotate(f'{v:+.2f}{mark}',(pos,v),xytext=(0,4 if v>=0 else -13),
                                    textcoords='offset points',ha='center',fontsize=9)
                    ax.axhline(0,color='black',lw=.8);ax.set_xticks(range(3),points)
                    ax.set_title(band);ax.set_ylabel('Change (%)' if protocol=='TCP' else f'Change ({unit})')
                    ax.grid(axis='y',alpha=.2)
                    finite=g.loc[g.band==band,'relative_change_pct' if protocol=='TCP' else 'delta'].dropna()
                    lo=min(0.0,finite.min()) if len(finite) else 0.0
                    hi=max(0.0,finite.max()) if len(finite) else 0.0
                    pad=(hi-lo)*.35 if hi>lo else .1
                    ax.set_ylim(lo-pad,hi+pad)
                    ax.legend(loc='upper right')
                fig.suptitle(f'{title} | {condition}\nChange vs own baseline; * incomplete runs; no significance claim')
                save(fig,f'09_effekte_{metric}_{condition}')


def descriptive_report():
    summary=read_csv('02_summary.csv')
    # Lesbare CSV mit deutschen Spaltennamen; getrennt je Bedingung/Kennzahl.
    summary.rename(columns={'person':'Person','block':'Block','condition':'Zustand',
        'band':'Band','point':'Messpunkt','protocol':'Protokoll','metric':'Kennzahl',
        'unit':'Einheit','n':'Anzahl','mean':'Mittelwert','sd':'Standardabweichung',
        'median':'Median','minimum':'Minimum','maximum':'Maximum',
        'q25':'Quartil_25','q75':'Quartil_75','iqr':'Interquartilsabstand',
        'range_value':'Spannweite','cv_pct':'Variationskoeffizient_Prozent'
    }).to_csv(OUT/'Deskriptive_Statistik.csv',sep=';',index=False,encoding='utf-8-sig')
    lines=['# Deskriptive Statistik','',
        'Eine Zeile pro Wohnung, Band, Messpunkt, Zustand und Kennzahl.',
        'Es werden keine heterogenen Messbedingungen zu einem Gesamtmittelwert vermischt.',
        'SD = Stichprobenstandardabweichung (ddof=1). Quartile/IQR sind bei n=2/3 nur deskriptiv.',
        'CV = SD/Mittelwert ×100; für nahezu null liegende Mittelwerte empfindlich.',
        'Werte mit n=0 fehlen; bei n=1 ist keine SD verfügbar. Keine Signifikanztests.','',
        '| Wohnung | Block | Kennzahl | n | Mittel | SD | Median | Min | Max |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for _,r in summary.iterrows():
        lines.append(f'| {r.person} | {r.block} | {r.metric} | {int(r.n)} | {fmt(r["mean"])} | {fmt(r.sd)} | {fmt(r["median"])} | {fmt(r.minimum)} | {fmt(r.maximum)} |')
    (OUT/'Deskriptive_Statistik.md').write_text('\n'.join(lines),encoding='utf-8')



def collect_signal_quality():
    """Signalwerte gemeinsam je Block; keine erfundene Zuordnung zu Lauf 1/2/3."""
    signals=read_csv('04_signal_summary.csv')
    runs=read_csv('01_runs.csv')
    if signals.empty:
        print('Keine Signalübersicht vorhanden.');return
    combined=signals.copy()
    for protocol in ['TCP','UDP']:
        counts=runs[(runs.protocol==protocol)&(runs.usable==True)].groupby(['person','block']).size()
        combined[f'{protocol.lower()}_valid_runs']=[int(counts.get((r.person,r.block),0)) for _,r in combined.iterrows()]
    combined['scope']='whole measurement block; not individual TCP/UDP run'
    write_csv('10_Signalqualitaet_Messbloecke.csv',combined)
    # Kontext zu jedem tatsächlich vorhandenen Lauf; Signalspalten heißen bewusst block_signal_*.
    cols=['person','block','source','status','signal_n','signal_mean_pct','signal_median_pct',
        'signal_sd_pct','signal_min_pct','signal_max_pct','rssi_median_dbm','note']
    context=signals[cols].rename(columns={c:f'block_signal_{c}' for c in cols if c not in ['person','block']})
    joined=runs[runs.status!='missing'].merge(context,on=['person','block'],how='left',validate='many_to_one')
    joined['signal_assignment']='block context only; no run-specific signal measurement'
    write_csv('10_Laeufe_mit_Signalkontext.csv',joined)
    effects=[]
    for _,r in combined[combined.condition.isin(CONDITIONS[1:])].iterrows():
        base=combined[(combined.person==r.person)&(combined.band==r.band)&
            (combined.point==r.point)&(combined.condition=='Baseline')]
        if base.empty:continue
        b=base.iloc[0]
        effects.append(dict(person=r.person,band=r.band,point=r.point,intervention=r.condition,
            baseline_signal_mean_pct=b.signal_mean_pct,intervention_signal_mean_pct=r.signal_mean_pct,
            change_percentage_points=r.signal_mean_pct-b.signal_mean_pct,
            baseline_signal_samples=b.signal_n,intervention_signal_samples=r.signal_n,
            note='Descriptive block-level signal quality; different adapters may report differently'))
    write_csv('10_Signalqualitaet_Baselinevergleich.csv',effects)
    fig,axes=plt.subplots(2,2,figsize=(13,8),sharey=True,layout='constrained')
    points=['TP1','TP2','TP3']
    for row,person in enumerate(['Ahmet','Nemanja']):
        for col,band in enumerate(['2.4 GHz','5 GHz']):
            ax=axes[row,col]
            conditions=CONDITIONS[:2] if band=='2.4 GHz' else CONDITIONS
            for offset,condition in zip(np.linspace(-.22,.22,len(conditions)),conditions):
                part=combined[(combined.person==person)&(combined.band==band)&
                    (combined.condition==condition)].set_index('point').reindex(points)
                for i,point in enumerate(points):
                    r=part.loc[point];v=r.signal_mean_pct
                    if pd.isna(v):
                        ax.text(i+offset,3,'n/a',ha='center',fontsize=8,color=COLORS[condition])
                        continue
                    ax.errorbar(i+offset,v,
                        yerr=np.array([[max(0,v-r.signal_min_pct)],[max(0,r.signal_max_pct-v)]]),
                        fmt='D',color=COLORS[condition],capsize=4,markersize=6)
            ax.set_title(f'{person} | {band}');ax.set_xticks(range(3),points)
            ax.set_xlim(-.5,2.5);ax.set_ylim(0,105);ax.set_ylabel('Logged signal quality (%)')
            ax.grid(axis='y',alpha=.2)
    handles=[Line2D([0],[0],marker='D',ls='',color=COLORS[c],label=c) for c in CONDITIONS]
    axes[0,1].legend(handles=handles,fontsize=9,loc='lower left')
    fig.suptitle('Signal quality across both residential environments\nDiamonds: block mean; whiskers: min–max over time (not SD of test runs)\nAdapter-reported percentages; cross-device comparability is limited',fontsize=14)
    if ALLE_DIAGRAMME:
        save(fig,'10_signal_quality_beide_wohnungen')
    else:
        plt.close(fig)
    explanation=[
        '# Signalqualität Ahmet und Nemanja','',
        '10_Signalqualitaet_Messbloecke.csv: alle 32 Blöcke mit Mittelwert, Median, SD, Minimum, Maximum und Zahl gültiger Signalwerte.',
        'Fehlende Signaldateien bleiben fehlend. LAN-Signalwerte sind Kontext, keine Eigenschaft der LAN-Strecke.',
        '10_Laeufe_mit_Signalkontext.csv: Verknüpfung jedes vorhandenen TCP-/UDP-Laufs mit seinem BLOCK-Kontext.',
        'Die wiederholten block_signal_* Werte sind KEINE separat pro Lauf gemessenen Werte und dürfen nicht als unabhängige Replikationen gezählt werden.',
        '10_Signalqualitaet_Baselinevergleich.csv: Signaländerung in Prozentpunkten innerhalb derselben Wohnung/Band/TP.',
        'Der Plot zeigt arithmetische Mittelwerte der gültigen Samples und zeitliche Min–Max-Spannweiten, keine Streuung von drei Testläufen.',
        'Signal-Samples sind zeitlich abhängig. n der Samples ist nicht n unabhängiger Versuche.',
        'Ohne gemeinsame Startzeit/Intervallzuordnung ist keine sichere Zuordnung zu TCP_Lauf_1/2/3 bzw. UDP_Lauf_1/2/3 möglich.',
        'Prozentwerte verschiedener Adapter sind nicht kalibriert vergleichbar. Vorzugsweise Änderungen innerhalb jeder Wohnung interpretieren.',
        'RSSI wird nicht aus Prozentwerten abgeleitet und wegen ungeklärter Herkunft nicht geplottet.',
        'Konstante RSSI-Werte trotz variierender Prozentwerte werden im ursprünglichen Signalexport markiert.',
        'Eine Signaländerung beweist nicht die Ursache einer Durchsatzänderung. Hintergrundaktivität und Interferenzen können mitwirken.',
    ]
    (OUT/'10_Signalqualitaet_Hinweise.md').write_text('\n'.join(explanation),encoding='utf-8')
    print('Gemeinsame Signalqualität und Lauf-Kontext erstellt.')



def signal_time_grids():
    """Je Wohnung 2×3 Teilplots: Bänder × TP; Zustände mit eigenem Median."""
    samples=read_csv('04_signal_samples.csv')
    if not samples.empty:
        for column in ['sekunde','signal_prozent']:
            samples[column]=pd.to_numeric(samples[column],errors='coerce')
        samples.loc[~samples.signal_prozent.between(0,100),'signal_prozent']=np.nan
        samples.loc[samples.sekunde<0,'sekunde']=np.nan
    median_rows=[]
    for person,prefix in PERSONS:
        fig,axes=plt.subplots(2,3,figsize=(16,8),sharex=True,sharey=True,layout='constrained')
        person_samples=samples[(samples.person==person)&(samples.band!='LAN')].copy() if not samples.empty else pd.DataFrame()
        max_time=person_samples.sekunde.max() if not person_samples.empty else np.nan
        for row,band in enumerate(['2.4 GHz','5 GHz']):
            for col,point in enumerate(['TP1','TP2','TP3']):
                ax=axes[row,col]
                conditions=CONDITIONS[:2] if band=='2.4 GHz' else CONDITIONS
                handles=[]
                for condition in conditions:
                    g=person_samples[(person_samples.band==band)&(person_samples.point==point)&
                        (person_samples.condition==condition)].sort_values('sekunde') if not person_samples.empty else pd.DataFrame()
                    valid=g.dropna(subset=['sekunde','signal_prozent']) if not g.empty else g
                    color=COLORS[condition]
                    label={'Baseline':'Baseline','Channel change':'I1 channel change','Foil shielding':'I2 foil shielding'}[condition]
                    if valid.empty:
                        handles.append(Line2D([0],[0],color=color,lw=1,label=f'{label}: no log'))
                        median_rows.append(dict(person=person,band=band,point=point,condition=condition,
                            samples=0,median_pct=None,scope='whole block signal log'))
                        continue
                    median=valid.signal_prozent.median()
                    # Jeden Verlauf an seinem tatsächlichen Ende beenden, keine Extrapolation.
                    ax.plot(g.sekunde,g.signal_prozent,color=color,lw=1.3,alpha=.55,zorder=2)
                    ax.hlines(median,valid.sekunde.min(),valid.sekunde.max(),
                        colors=color,linestyles='--',lw=2,zorder=3)
                    handles.append(Line2D([0],[0],color=color,lw=2,ls='--',
                        label=f'{label}: median {median:.1f}%'))
                    median_rows.append(dict(person=person,band=band,point=point,condition=condition,
                        samples=len(valid),median_pct=median,scope='whole block signal log'))
                ax.set_title(f'{band} | {point}',fontsize=13)
                ax.set_ylim(0,105);ax.set_yticks([0,25,50,75,100]);ax.grid(alpha=.2)
                if pd.notna(max_time) and max_time>0:ax.set_xlim(0,max_time*1.02)
                else:ax.set_xlim(0,1)
                ax.legend(handles=handles,fontsize=8,loc='lower left',framealpha=.9)
        fig.suptitle(f'{person}: signal quality over time by condition\n'
            'Transparent lines: recorded signal; dashed lines: median of each block log\n'
            'Elapsed time restarts per condition; recordings are not simultaneous',fontsize=15)
        fig.supxlabel('Elapsed time within each signal log (s)')
        fig.supylabel('Logged signal quality (%)')
        save(fig,f'04_signalverlauf_{person}_Baender_TP_Median')
    write_csv('04_signal_medianlinien.csv',median_rows)
    print('Signalvergleich mit Medianlinien: zwei 2×3-Übersichten erstellt.')


def descriptive_plots():
    """Mittelwert, Median, SD und Min–Max aus Wiederholungen, je Bedingung."""
    summary=read_csv('02_summary.csv')
    if summary.empty:return
    combinations=[]
    for band in ['2.4 GHz','5 GHz']:
        for condition in (CONDITIONS[:2] if band=='2.4 GHz' else CONDITIONS):
            for point in ['TP1','TP2','TP3']:
                combinations.append((band,condition,point))
    short={'Baseline':'Baseline','Channel change':'Channel','Foil shielding':'Foil'}
    labels=[f'{b} | {short[c]} | {p}' for b,c,p in combinations]
    for protocol,metric,title,unit in METRICS:
        unit='%' if metric=='loss_pct' else unit
        fig,axes=plt.subplots(1,2,figsize=(19,10),sharex=True,sharey=True,layout='constrained')
        totals=summary[(summary.metric==metric)&(summary.band!='LAN')]
        high=pd.concat([totals['maximum'],totals['mean']+totals.sd.fillna(0)]).max()
        high=high*1.13 if pd.notna(high) and high>0 else 1
        for ax,person in zip(axes,['Ahmet','Nemanja']):
            part=totals[totals.person==person]
            ax.set_yticks(range(len(labels)),labels)
            for y,(band,condition,point) in enumerate(combinations):
                g=part[(part.band==band)&(part.condition==condition)&(part.point==point)]
                if g.empty or g.iloc[0]['n']==0:
                    ax.text(1.02,y,'n=0 | missing',transform=ax.get_yaxis_transform(),va='center',fontsize=9)
                    continue
                r=g.iloc[0];color=COLORS[condition]
                ax.hlines(y,r.minimum,r.maximum,color=color,lw=1.3,alpha=.65)
                ax.plot([r.minimum,r.maximum],[y,y],ls='',marker='|',ms=8,color=color)
                if pd.notna(r.sd):
                    ax.hlines(y,r['mean']-r.sd,r['mean']+r.sd,color=color,lw=5,alpha=.45)
                ax.plot(r['mean'],y,'o',color=color,ms=6,zorder=4)
                ax.plot(r['median'],y,marker='x',ls='',color='black',ms=7,zorder=5)
                sd=f'{r.sd:.3f}' if pd.notna(r.sd) else 'n/a'
                ax.text(1.02,y,f'n={int(r.n)}  {r["mean"]:.3f} ± {sd}  |  {r["median"]:.3f}',
                    transform=ax.get_yaxis_transform(),va='center',fontsize=9)
            ax.text(1.02,1.025,'n    Mean ± SD   |   Median',transform=ax.transAxes,fontsize=10,fontweight='bold')
            low=(totals['mean']-totals.sd.fillna(0)).min()
            # SD kann rechnerisch über den physikalisch möglichen Bereich hinausreichen.
            ax.set_xlim(min(0,low) if pd.notna(low) else 0,high)
            ax.set_ylim(len(labels)-.4,-.9);ax.set_title(person,fontsize=16,pad=25)
            ax.set_xlabel(f'{title} ({unit})');ax.grid(axis='x',alpha=.2)
            for boundary in [2.5,5.5,8.5,11.5]:ax.axhline(boundary,color='#dddddd',lw=.8)
        legend=[
            Line2D([0],[0],color='#245580',lw=1.3,marker='|',label='Thin line: observed min–max'),
            Line2D([0],[0],color='#245580',lw=5,alpha=.45,label='Thick line: mean ±1 SD'),
            Line2D([0],[0],ls='',marker='o',color='#245580',label='Mean'),
            Line2D([0],[0],ls='',marker='x',color='black',label='Median')]
        fig.suptitle(f'Descriptive statistics | {title}\n'
            'Separate conditions; SD describes variation between runs, not statistical significance',fontsize=17)
        fig.legend(handles=legend,loc='outside lower center',ncol=4,fontsize=11)
        save(fig,f'11_deskriptiv_{metric}')
    print('Drei deskriptive Statistikgrafiken mit Zahlen erstellt.')



def campaign_overview():
    """Zeiten, Vollständigkeit, Extrema und sichtbare Nachbarzugangspunkte."""
    runs=read_csv('01_runs.csv')
    if runs.empty:return
    valid=runs[runs.usable==True].copy()
    counts=[]
    for (person,protocol),g in runs.groupby(['person','protocol']):
        counts.append(dict(person=person,protocol=protocol,expected_runs=len(g),
            usable_runs=int((g.usable==True).sum()),missing_runs=int((g.status=='missing').sum()),
            review_or_error_runs=int((~g.status.isin(['ok','missing'])).sum()),
            actual_duration_min_s=g.loc[g.usable==True,'seconds'].min(),
            actual_duration_max_s=g.loc[g.usable==True,'seconds'].max(),
            udp_target_rates_mbps=str(sorted(g.target_mbps.dropna().unique().tolist())) if protocol=='UDP' else 'not applicable'))
    write_csv('12_Kampagne_Umfang.csv',counts)
    # Nur echte Dateiinhalte/iperf-Zeitstempel; keine Dateisystemzeiten als Messzeit ausgeben.
    times=[]
    for person,g in runs.groupby('person'):
        dated=g.dropna(subset=['timestamp_vienna']).copy()
        if dated.empty:
            times.append(dict(person=person,date_vienna=None,first_test_start=None,last_test_start=None,
                runs_with_timestamp=0,runs_without_timestamp=len(g),note='Keine Testzeitstempel verfügbar'))
            continue
        dated['date']=dated.timestamp_vienna.str.slice(0,10)
        for day,part in dated.groupby('date'):
            times.append(dict(person=person,date_vienna=day,
                first_test_start=part.timestamp_vienna.min(),last_test_start=part.timestamp_vienna.max(),
                runs_with_timestamp=len(part),runs_without_timestamp=None,
                starts_before_22=int((part.start_hour<22).sum()),
                note='Teststart-Zeiten, keine Sessiongrenzen; nach Mitternacht fortgesetzte Sessions möglich'))
        times.append(dict(person=person,date_vienna='TOTAL',first_test_start=None,last_test_start=None,
            runs_with_timestamp=len(dated),runs_without_timestamp=len(g)-len(dated),
            note='Fehlende Läufe haben naturgemäß keinen Zeitstempel'))
    write_csv('12_Kampagne_Uhrzeiten.csv',times)
    extrema=[]
    metrics=METRICS+[('UDP','throughput_mbps','UDP received throughput','Mbit/s')]
    for (person,band),g in valid.groupby(['person','band']):
        for protocol,metric,title,unit in metrics:
            x=g[g.protocol==protocol].dropna(subset=[metric])
            if x.empty:continue
            low,high=x[metric].min(),x[metric].max()
            row=dict(person=person,band=band,protocol=protocol,metric=title,unit='%' if metric=='loss_pct' else unit,
                n=len(x),minimum=low,maximum=high,median=x[metric].median(),mean=x[metric].mean(),
                note='Über alle Zustände/TP dieses Bands; nicht als Interventionseffekt interpretieren')
            for label,value in [('minimum',low),('maximum',high)]:
                tied=x[x[metric]==value]
                row[f'{label}_locations']=' | '.join(
                    f'{r.block}/{r.point}/{r.condition}/run{int(r.run)}' for _,r in tied.iterrows())
                row[f'{label}_ties']=len(tied)
            if metric=='loss_pct':row['runs_with_loss']=int((x[metric]>0).sum())
            extrema.append(row)
    write_csv('12_Kennzahlen_Extrema.csv',extrema)
    # Nachbarscans: in data rekursiv gespeicherte Windows-netsh-Textausgaben.
    # CSV optional: relative_path;person;block;own_channel;own_bssid;scan_time
    meta_path=DATA/'scan_zuordnung.csv'
    scan_meta=pd.read_csv(meta_path,sep=';').fillna('') if meta_path.is_file() else pd.DataFrame()
    scan_rows=[];access_points=[];scan_issues=[]
    for path in sorted(DATA.rglob('*')) if DATA.is_dir() else []:
        if not path.is_file() or path.suffix.lower() not in ['.txt','.log']:continue
        rel=str(path.relative_to(DATA)).replace('\\','/')
        try:text=read_text(path)
        except (OSError,ValueError) as e:
            if any(w in path.name.lower() for w in ['scan','neigh','nachbar','wlan']):
                scan_issues.append(dict(source=rel,status='read_error',note=str(e)))
            continue
        if not re.search(r'BSSID\s+\d+\s*:',text,re.I):
            if any(w in path.name.lower() for w in ['scan','neigh','nachbar']):
                scan_issues.append(dict(source=rel,status='format_review',note='Kein unterstütztes netsh-BSSID-Format erkannt'))
            continue
        ssid=None;ap=None;found=[]
        for line in text.splitlines():
            m=re.match(r'\s*SSID\s+\d+\s*:\s*(.*)',line,re.I)
            if m:ssid=m[1].strip()
            m=re.match(r'\s*BSSID\s+\d+\s*:\s*([0-9a-f:-]{17})',line,re.I)
            if m:
                if ap:found.append(ap)
                ap=dict(ssid=ssid,bssid=m[1].lower().replace('-',':'),channel=None,signal_pct=None)
            if ap:
                m=re.match(r'\s*(?:Channel|Kanal)\s*:\s*(\d+)',line,re.I)
                if m:ap['channel']=int(m[1])
                m=re.match(r'\s*Signal\s*:\s*(\d+)\s*%',line,re.I)
                if m:ap['signal_pct']=int(m[1])
        if ap:found.append(ap)
        # Eine BSSID pro Scan einmal zählen; doppelte Interface-Ausgaben nicht aufsummieren.
        found=list({a['bssid']:a for a in found}.values())
        person=next((p for p,_ in PERSONS if p.lower() in rel.lower()),'unknown')
        match=re.search(r'(?:^|/)([AN]\d{2})(?:/|[._-]|$)',rel,re.I)
        block=match[1].upper() if match else ''
        own_channel=None;own_bssid='';scan_time=''
        if not scan_meta.empty and 'relative_path' in scan_meta:
            matching=scan_meta[scan_meta.relative_path.astype(str).str.replace('\\','/',regex=False)==rel]
            if not matching.empty:
                info=matching.iloc[0]
                person=info.get('person') or person;block=info.get('block') or block
                c=pd.to_numeric(info.get('own_channel'),errors='coerce')
                own_channel=int(c) if pd.notna(c) else None
                own_bssid=str(info.get('own_bssid','')).lower().replace('-',':')
                scan_time=str(info.get('scan_time',''))
        others=[a for a in found if not own_bssid or a['bssid']!=own_bssid]
        scan_rows.append(dict(source=rel,person=person,block=block,scan_time=scan_time,
            visible_unique_bssids=len(found),visible_unique_nonempty_ssids=len({a['ssid'] for a in found if a['ssid']}),
            own_bssid_excluded=bool(own_bssid),other_visible_bssids=len(others) if own_bssid else None,
            own_channel=own_channel,
            visible_bssids_same_channel=sum(a['channel']==own_channel for a in others) if own_channel is not None else None,
            note='Sichtbare APs, keine Kanalauslastung; ohne eigene BSSID enthält Zählung ggf. eigenen AP; gleiche Kanalnummer allein identifiziert bei 6 GHz das Band nicht eindeutig'))
        for a in found:access_points.append(dict(source=rel,person=person,block=block,**a))
    write_csv('12_Neighbour_Scans.csv',scan_rows,columns=None if scan_rows else ['source','person','block','visible_unique_bssids','note'])
    # BSSIDs/SSIDs nur im lokalen technischen Export; für Präsentation aggregierte Tabelle verwenden.
    write_csv('12_Neighbour_AP_Details.csv',access_points)
    write_csv('12_Neighbour_Pruefung.csv',scan_issues)
    write_csv('12_Scan_Zuordnung_Vorlage.csv',[dict(relative_path=r['source'],person=r['person'],block=r['block'],
        own_channel='',own_bssid='',scan_time='') for r in scan_rows],
        columns=['relative_path','person','block','own_channel','own_bssid','scan_time'])
    lines=['# Kampagnenübersicht','',
        '12_Kampagne_Umfang.csv: Anzahl erwarteter, auswertbarer, fehlender und auffälliger Läufe; Dauern und UDP-Lasten.',
        '12_Kampagne_Uhrzeiten.csv: erster/letzter TESTSTART je Wohnung und Datum (Europe/Vienna). Keine ausgedachten Sessiongrenzen.',
        '12_Kennzahlen_Extrema.csv: höchste/niedrigste Lauf-Gesamtraten, Jitter und Verlust mit allen Fundstellen bei Gleichstand. LAN separat.',
        'Bandweite Extrema vermischen absichtlich mehrere dokumentierte Bedingungen zur Übersicht. Interventionen weiterhin anhand eigener Baseline vergleichen.',
        'UDP-Durchsatz ist Empfang bei angebotener Last, keine maximale WLAN-Kapazität.',
        f'Erkannte gespeicherte netsh-Nachbarscans: {len(scan_rows)}.',
        '12_Neighbour_Scans.csv zählt eindeutige BSSIDs pro Scan; SSIDs und BSSIDs sind nicht gleichzusetzen.',
        'Fehlender Scan ist keine Beobachtung von null Nachbarnetzen. Unbekannte Formate stehen, sofern am Namen erkennbar, in 12_Neighbour_Pruefung.csv.',
        'Falls keine Scans erkannt werden: tatsächliche netsh-Ausgaben als .txt oder .log unter data ablegen. Es wird kein Scan auf dem Analyse-PC durchgeführt.',
        'Eigener Kanal und Scanzeit sind aus dem Messprotokoll zu ergänzen, nicht aus Dateisystemzeiten zu raten.',
        'Dafür 12_Scan_Zuordnung_Vorlage.csv ausfüllen und als data/scan_zuordnung.csv speichern; erneut ausführen.',
        'Ohne eigene BSSID sind auch eigene Zugangspunkte in der Gesamtzahl enthalten. Ohne eigenen Kanal bleibt die Gleichkanal-Zählung leer.',
        'Gleiche Kanalnummern werden gezählt, nicht überlappende Kanalbreiten. Bei 6-GHz-Netzen ist zusätzlich eine Bandprüfung erforderlich.',
        'AP-Details enthalten lokale Netzkennungen; für geteilte Folien nur aggregierte Werte verwenden.',
        'Keine Rückschlüsse auf tatsächliche Airtime/Kanalauslastung aus der Anzahl sichtbarer APs.',
    ]
    (OUT/'12_Kampagnenuebersicht.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Kampagnenübersicht erstellt; {len(scan_rows)} gespeicherte Nachbarscans erkannt.')



def campaign_plots():
    """Grafischer deskriptiver Überblick zur tatsächlich eingelesenen Kampagne."""
    runs=read_csv('01_runs.csv')
    if runs.empty:return
    valid=runs[runs.usable==True]
    persons=['Ahmet','Nemanja']
    status_colors=['#119C86','#DE8035','#B7BDC5']
    fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    ax=axes[0,0]
    for i,person in enumerate(persons):
        counts=runs[runs.person==person].groupby('block').usable.sum()
        parts=[int((counts==6).sum()),int(((counts>0)&(counts<6)).sum()),int((counts==0).sum())]
        bottom=0
        for v,c,label in zip(parts,status_colors,['6 valid runs','1–5 valid runs','No valid runs']):
            ax.bar(i,v,bottom=bottom,color=c,label=label if i==0 else None)
            if v:ax.text(i,bottom+v/2,str(v),ha='center',va='center')
            bottom+=v
    ax.set_xticks(range(2),persons);ax.set_ylim(0,20);ax.set_ylabel('Measurement blocks')
    ax.set_title('Block completeness | 16 planned per flat');ax.legend(fontsize=8)
    for ax,protocol in [(axes[0,1],'TCP'),(axes[1,0],'UDP')]:
        for i,person in enumerate(persons):
            g=runs[(runs.person==person)&(runs.protocol==protocol)]
            counts=[int((g.usable==True).sum()),int(((g.usable!=True)&(g.status!='missing')).sum()),int((g.status=='missing').sum())]
            bottom=0
            for v,c,label in zip(counts,status_colors,['Usable','Excluded / review','Missing']):
                ax.bar(i,v,bottom=bottom,color=c,label=label if i==0 else None)
                if v>=4:ax.text(i,bottom+v/2,str(v),ha='center',va='center')
                bottom+=v
        ax.text(i,51,f'{counts[0]} valid / {counts[1]} review / {counts[2]} missing',ha='center',fontsize=8)
        ax.set_xticks(range(2),persons);ax.set_ylim(0,58);ax.set_ylabel('Individual test runs')
        ax.set_title(f'{protocol} runs | 48 planned per flat');ax.legend(fontsize=8)
    ax=axes[1,1];ax.axis('off')
    seconds=valid.seconds.dropna();signals=read_csv('04_signal_summary.csv');pings=read_csv('04_ping_summary.csv')
    existing=int((runs.status!='missing').sum())
    text=['CAMPAIGN AT A GLANCE', '',
        '2 residential environments · 3 fixed test points each',
        '2.4 GHz and 5 GHz · LAN reference reported separately',
        f'Expected runs: {len(runs)} | Files present: {existing}',
        f'Usable runs: {len(valid)} | Missing files: {int((runs.status=="missing").sum())}',
        'Planned: 3 × 30 s per protocol and measurement block']
    if len(seconds):text.append(f'Observed usable run duration: {seconds.min():.2f}–{seconds.max():.2f} s')
    if not signals.empty:text.append(f'Signal logs available: {int((signals.sample_count>0).sum())} / 32 block slots')
    if not pings.empty:
        sent=pd.to_numeric(pings.get('sent'),errors='coerce') if 'sent' in pings else pd.Series(dtype=float)
        if len(sent.dropna()):text.append(f'Ping requests recorded in parsed summaries: {int(sent.sum())}')
    text+=['','Counts describe the imported dataset, not independent sessions.']
    ax.text(0,1,'\n'.join(text),va='top',fontsize=11,linespacing=1.6)
    fig.suptitle('Measurement campaign | descriptive overview',fontsize=18)
    save(fig,'13_01_messkampagne_anzahl_vollstaendigkeit')
    # Uhrzeiten: je Datum und Wohnung eine Zeile, keine Sessiongrenzen unterstellen.
    timed=runs.dropna(subset=['timestamp_vienna']).copy()
    fig,ax=plt.subplots(figsize=(13,max(4, .65*timed.timestamp_vienna.astype(str).str[:10].nunique()*2)),layout='constrained')
    if timed.empty:
        ax.axis('off');ax.text(.5,.5,'No recorded test timestamps available\nRun times cannot be reconstructed from the CSV alone.',ha='center',va='center',transform=ax.transAxes)
    else:
        timed['day']=timed.timestamp_vienna.str[:10]
        timed['hour_decimal']=timed.timestamp_vienna.map(lambda t: int(t[11:13])+int(t[14:16])/60+float(t[17:19])/3600)
        labels=[]
        for i,((person,day),g) in enumerate(timed.groupby(['person','day'])):
            labels.append(f'{person} | {day}')
            for protocol,offset,color in [('TCP',-.10,'#245580'),('UDP',.10,'#DE8035')]:
                v=g[g.protocol==protocol]
                ax.scatter(v.hour_decimal,[i+offset]*len(v),s=25,color=color,alpha=.6)
            visible=int(g.hour_decimal.between(19,24).sum())
            ax.text(1.01,i,f'n={visible} shown / {len(g)} total',transform=ax.get_yaxis_transform(),va='center',fontsize=9)
        ax.set_yticks(range(len(labels)),labels);ax.set_xlim(19,24);ax.set_xticks(range(19,25),['19:00','20:00','21:00','22:00','23:00','00:00'])
        ax.axvline(22,color='gray',ls='--',label='22:00 reference')
        ax.legend(handles=[Line2D([0],[0],marker='o',ls='',color='#245580',label='TCP start'),
            Line2D([0],[0],marker='o',ls='',color='#DE8035',label='UDP start'),
            Line2D([0],[0],ls='--',color='gray',label='22:00 reference')],fontsize=9)
        ax.set_xlabel('Local clock time | Europe/Vienna');ax.grid(axis='x',alpha=.2)
    ax.set_title('Recorded test start times\nCalendar dates shown separately; after-midnight tests may belong to the previous evening session',pad=18)
    save(fig,'13_02_messzeiten')
    # Extremwerte nur WLAN, LAN wird weiter separat in CSV geführt.
    fig,axes=plt.subplots(1,3,figsize=(17,5.5),layout='constrained')
    combinations=[(p,b) for p in persons for b in ['2.4 GHz','5 GHz']]
    for ax,(protocol,metric,title,unit) in zip(axes,METRICS):
        for i,(person,band) in enumerate(combinations):
            x=valid[(valid.person==person)&(valid.band==band)&(valid.protocol==protocol)][metric].dropna()
            if x.empty:
                ax.text(.02,i,'missing',transform=ax.get_yaxis_transform());continue
            lo,hi=x.min(),x.max();mean=x.mean()
            ax.hlines(i,lo,hi,color='#245580',lw=2)
            ax.plot([lo,hi],[i,i],ls='',marker='|',color='#245580',ms=13)
            ax.plot(mean,i,'o',color='#119C86')
            ax.annotate(f'{lo:.3g} – {hi:.3g}  (n={len(x)})',(hi,i),xytext=(7,5),textcoords='offset points',fontsize=9)
        ax.set_yticks(range(4),[p+' | '+b for p,b in combinations]);ax.set_ylim(3.6,-.6)
        ax.set_xlabel('%' if metric=='loss_pct' else unit);ax.set_title(title);ax.grid(axis='x',alpha=.2)
        ax.margins(x=.5)
    fig.suptitle('Observed WLAN ranges across all test points and conditions\nLine: minimum–maximum of run results · Green dot: pooled mean for overview only\nDifferent conditions are mixed here; use baseline comparisons to assess interventions',fontsize=14)
    save(fig,'13_03_hoechste_niedrigste_werte')
    scans=read_csv('12_Neighbour_Scans.csv')
    fig,ax=plt.subplots(figsize=(12,max(4,.4*len(scans))),layout='constrained')
    if scans.empty:
        ax.axis('off');ax.text(.5,.5,'No supported neighbour-scan logs found\nMissing scan data does not mean zero neighbouring networks.\nSave netsh scan outputs as .txt or .log under data.',ha='center',va='center',transform=ax.transAxes,fontsize=13)
    else:
        labels=[f'{r.person} | {r.block if pd.notna(r.block) else "no block"} | scan {i+1}' for i,(_,r) in enumerate(scans.iterrows())]
        ax.barh(range(len(scans)),scans.visible_unique_bssids,color='#245580')
        for i,v in enumerate(scans.visible_unique_bssids):ax.text(v+.1,i,str(int(v)),va='center')
        ax.set_yticks(range(len(scans)),labels);ax.invert_yaxis();ax.set_xlabel('Unique visible BSSIDs per scan (may include own access points)');ax.margins(x=.15)
    ax.set_title('Neighbour scan overview\nVisible access points, not channel utilisation',pad=16)
    save(fig,'13_04_neighbour_scans')
    print('Vier grafische Kampagnenübersichten erstellt (Anzahl, Uhrzeiten, Wertebereiche, Nachbarscans).')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    print(f'Daten: {DATA}\nAusgabe: {OUT}',flush=True)
    if DATA.is_dir():
        step_1()
        raw=True
    else:
        csv_fallback()
        raw=False
    step_2()
    step_3()
    if raw:
        step_4()
        collect_signal_quality()
        signal_time_grids()
        if ALLE_DIAGRAMME:
            step_6()
    else:
        print('Ping-/Signal-/Intervallanalyse übersprungen: keine Rohdaten.')
    step_5()
    if ALLE_DIAGRAMME:
        extra_plots()
    descriptive_report()
    descriptive_plots()
    campaign_overview()
    campaign_plots()
    print(f'\nFERTIG. Öffne {PLOTS}')
    print('Statistik: Deskriptive_Statistik.csv und .md; Bericht: 05_Auswertungsbericht.md')


if __name__=='__main__':
    main()
