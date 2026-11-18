"""Sekundenintervalle als Diagnostik; nicht als unabhängige Wiederholungen."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import *


def run():
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
            fig.savefig(PLOTS/f'{stem(person+band+condition)}_intervals.{ext}',dpi=180)
        plt.close(fig)
    print('TCP-Zeitverläufe erstellt (Seite der Intervallsumme siehe 01_intervals.csv).')

if __name__=='__main__':
    run()
