"""Deskriptive Kennwerte, Effekte und LAN-Einordnung; keine Signifikanztests."""
from common import *

KEYS = ['person', 'block', 'condition', 'band', 'point', 'protocol']

def run():
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

if __name__ == '__main__':
    run()
