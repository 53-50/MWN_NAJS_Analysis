"""Ergänzende Daten; unbekannte Ping-Formate werden ausdrücklich gekennzeichnet."""
import re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import *


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


def run():
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
                if meta['band']!='LAN' and points:
                    fig,ax=plt.subplots(figsize=(9,3.6),layout='constrained')
                    t=[p.get('sekunde',np.nan) for p in points]
                    values=[p.get('signal_prozent',np.nan) for p in points]
                    ax.plot(t,values,color='#245580');ax.set_ylim(0,100)
                    ax.set_xlabel('Elapsed time in signal log (s)');ax.set_ylabel('Signal (%)')
                    ax.set_title(f"{meta['person']} {meta['block']} | {meta['band']} | {meta['point']}\nSignal quality as logged; not aligned to individual iperf runs")
                    for ext in ['png','svg']:
                        fig.savefig(PLOTS/f"signal_{meta['block']}.{ext}",dpi=180)
                    plt.close(fig)
            except (OSError,ValueError,KeyError,TypeError) as e:
                row.update(status='error',note=str(e))
        signals.append(row)
    write_csv('04_ping_summary.csv',pings)
    write_csv('04_signal_summary.csv',signals)
    write_csv('04_signal_samples.csv',samples)
    print('Ping und Signal ausgewertet; Hinweise in 04_*_summary.csv beachten.')

if __name__=='__main__':
    run()
