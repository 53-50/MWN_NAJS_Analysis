"""Vergleiche und Heatmaps als PNG/SVG; Einzelwerte und n bleiben sichtbar."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from common import *


def save(fig,name):
    PLOTS.mkdir(exist_ok=True,parents=True)
    for ext in ['png','svg']:
        fig.savefig(PLOTS/f'{stem(name)}.{ext}',dpi=220,bbox_inches='tight')
    plt.close(fig)


def run():
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
            save(fig,f'{person}_{band}_comparison')
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
            fig.colorbar(im,ax=ax,shrink=.8);save(fig,f'heatmap_{metric}')
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
        save(fig,'tp3_throughput_retention')
    print(f'Diagramme: {PLOTS}')

if __name__=='__main__':
    run()
