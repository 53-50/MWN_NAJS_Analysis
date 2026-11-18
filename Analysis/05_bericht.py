"""Erstellt einen vollständigen deskriptiven Textbericht und Zeitprüfung."""
from common import *

QUESTION='Wie verändern sich TCP-Durchsatz, UDP-Jitter und Paketverlust gegenüber der jeweiligen Ausgangskonfiguration bei einem WLAN-Kanalwechsel und einer zusätzlichen Abschirmung in zwei unterschiedlichen Wohnumgebungen, wenn die Messsessions jeweils ab 22 Uhr beginnen?'

def fmt(v):
    return f'{v:.3f}' if pd.notna(v) else 'nicht verfügbar'


def run():
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

if __name__=='__main__':
    run()
