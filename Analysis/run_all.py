"""In PyCharm diese Datei ausführen. Alle Skripte nutzen denselben Interpreter."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
STEPS=['01_import_pruefen.py','02_vergleiche.py','03_diagramme.py',
       '04_ping_signal.py','05_bericht.py','06_zeitverlauf.py']

if __name__=='__main__':
    for step in STEPS:
        print(f'\n>>> {step}',flush=True)
        subprocess.run([sys.executable,str(ROOT/step)],cwd=ROOT,check=True)
    print('\nFertig. Öffne output_analyse/05_Auswertungsbericht.md und output_analyse/plots.')
