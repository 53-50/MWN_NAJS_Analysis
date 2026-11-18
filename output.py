import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

einzelwerte = []
warnungen = []


def zahl(wert):
    return (
        isinstance(wert, (int, float))
        and not isinstance(wert, bool)
        and math.isfinite(wert)
    )


def speichern(name, zeilen):
    if not zeilen:
        return

    with (OUTPUT / name).open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=list(zeilen[0]), delimiter=";"
        )
        writer.writeheader()
        writer.writerows(zeilen)


for person, prefix in [("Ahmet", "A"), ("Nemanja", "N")]:
    for nummer in range(1, 17):
        block = f"{prefix}{nummer:02d}"
        ordner = DATA / person / block

        # Dateinamen ohne Beachtung der Groß-/Kleinschreibung
        dateien = {
            p.name.lower(): p
            for p in ordner.glob("*")
            if p.is_file()
        }

        for protokoll in ("TCP", "UDP"):
            for lauf in (1, 2, 3):
                name = f"{protokoll}_Lauf_{lauf}.json"
                datei = dateien.get(name.lower())

                if datei is None:
                    warnungen.append(f"{person}/{block}: {name} fehlt")
                    continue

                try:
                    with datei.open(encoding="utf-8-sig") as f:
                        daten = json.load(f)

                    if daten.get("error"):
                        raise ValueError(daten["error"])

                    parameter = daten["start"]["test_start"]

                    if parameter.get("protocol") != protokoll:
                        raise ValueError("Protokoll passt nicht zum Dateinamen")

                    ergebnis = daten["end"]["sum_received"]
                    bps = ergebnis.get("bits_per_second")
                    dauer = ergebnis.get("seconds")

                    if not zahl(bps) or not zahl(dauer):
                        raise ValueError("Durchsatz oder Dauer fehlt")

                    if dauer <= 0:
                        raise ValueError("Ungültige Messdauer")

                    # Ungewöhnliche Dauer bleibt sichtbar.
                    if not 29 <= dauer <= 32:
                        warnungen.append(
                            f"{person}/{block}/{name}: "
                            f"Messdauer {dauer:.2f} s prüfen"
                        )

                    zeile = {
                        "Person": person,
                        "Block": block,
                        "Protokoll": protokoll,
                        "Lauf": lauf,
                        "Dauer_s": dauer,
                        "Reverse": parameter.get("reverse"),
                        "Senderate_Mbit_s": (
                            parameter["target_bitrate"] / 1_000_000
                            if zahl(parameter.get("target_bitrate"))
                            else None
                        ),
                        "Durchsatz_Mbit_s": bps / 1_000_000,
                        "Jitter_ms": None,
                        "Paketverlust_Prozent": None,
                    }

                    if protokoll == "UDP":
                        for quelle, ziel in [
                            ("jitter_ms", "Jitter_ms"),
                            ("lost_percent", "Paketverlust_Prozent"),
                        ]:
                            wert = ergebnis.get(quelle)

                            if zahl(wert):
                                zeile[ziel] = wert
                            else:
                                warnungen.append(
                                    f"{person}/{block}/{name}: "
                                    f"{quelle} fehlt"
                                )

                    einzelwerte.append(zeile)

                except (OSError, ValueError, KeyError, TypeError) as fehler:
                    warnungen.append(
                        f"{person}/{block}/{name}: {fehler}"
                    )

speichern("Einzelwerte.csv", einzelwerte)

zusammenfassung = []

gruppen = sorted({
    (z["Person"], z["Block"], z["Protokoll"])
    for z in einzelwerte
})

for person, block, protokoll in gruppen:
    laeufe = [
        z for z in einzelwerte
        if (z["Person"], z["Block"], z["Protokoll"])
        == (person, block, protokoll)
    ]

    zeile = {
        "Person": person,
        "Block": block,
        "Protokoll": protokoll,
        "Anzahl_Laeufe": len(laeufe),
    }

    for merkmal in [
        "Durchsatz_Mbit_s",
        "Jitter_ms",
        "Paketverlust_Prozent",
    ]:
        werte = [
            z[merkmal] for z in laeufe
            if zahl(z[merkmal])
        ]

        zeile[f"{merkmal}_n"] = len(werte)
        zeile[f"{merkmal}_Mittelwert"] = (
            mean(werte) if werte else None
        )
        zeile[f"{merkmal}_Standardabweichung"] = (
            stdev(werte) if len(werte) >= 2 else None
        )

    zusammenfassung.append(zeile)

speichern("Zusammenfassung.csv", zusammenfassung)

(OUTPUT / "Warnungen.txt").write_text(
    "\n".join(warnungen) if warnungen else "Keine Warnungen.",
    encoding="utf-8"
)

print(f"Eingelesene TCP-/UDP-Läufe: {len(einzelwerte)}")
print(f"Ausgabeordner: {OUTPUT}")
print(f"Warnungen: {len(warnungen)}")

for warnung in warnungen:
    print("-", warnung)