from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
PLOTS = OUTPUT / "plots"
PLOTS.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(OUTPUT / "Einzelwerte.csv", sep=";")

# Von euch bestätigte Zuordnung der Messblöcke
ZUORDNUNG = {
    1: ("LAN", "LAN", None),
    2: ("Baseline", "2.4 GHz", "TP1"),
    3: ("Baseline", "2.4 GHz", "TP2"),
    4: ("Baseline", "2.4 GHz", "TP3"),
    5: ("Baseline", "5 GHz", "TP1"),
    6: ("Baseline", "5 GHz", "TP2"),
    7: ("Baseline", "5 GHz", "TP3"),
    8: ("Channel change", "2.4 GHz", "TP1"),
    9: ("Channel change", "2.4 GHz", "TP2"),
    10: ("Channel change", "2.4 GHz", "TP3"),
    11: ("Channel change", "5 GHz", "TP1"),
    12: ("Channel change", "5 GHz", "TP2"),
    13: ("Channel change", "5 GHz", "TP3"),
    14: ("Foil shielding", "5 GHz", "TP1"),
    15: ("Foil shielding", "5 GHz", "TP2"),
    16: ("Foil shielding", "5 GHz", "TP3"),
}

nummern = df["Block"].str.extract(r"(\d+)$")[0].astype(int)

df["Condition"] = nummern.map(lambda n: ZUORDNUNG[n][0])
df["Band"] = nummern.map(lambda n: ZUORDNUNG[n][1])
df["Point"] = nummern.map(lambda n: ZUORDNUNG[n][2])

FARBEN = {
    "Baseline": "#245580",
    "Channel change": "#119C86",
    "Foil shielding": "#DE8035",
}

METRIKEN = [
    ("TCP", "Durchsatz_Mbit_s", "TCP throughput", "Mbit/s"),
    ("UDP", "Jitter_ms", "UDP jitter", "ms"),
    ("UDP", "Paketverlust_Prozent", "UDP packet loss", "%"),
]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.titlesize": 15,
    "axes.labelsize": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def speichern(fig, name):
    fig.savefig(PLOTS / f"{name}.png", dpi=220, bbox_inches="tight")
    fig.savefig(PLOTS / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------
# 1. Vergleichsdiagramme
# --------------------------------------------------
for person in sorted(df["Person"].unique()):
    for band in ["2.4 GHz", "5 GHz"]:
        teil = df[
            (df["Person"] == person)
            & (df["Band"] == band)
        ]

        if teil.empty:
            continue

        zustaende = ["Baseline", "Channel change"]
        if band == "5 GHz":
            zustaende.append("Foil shielding")

        fig, axes = plt.subplots(
            1, 3, figsize=(16, 4.8), layout="constrained"
        )

        offsets = np.linspace(-0.23, 0.23, len(zustaende))

        for ax, (protokoll, spalte, titel, einheit) in zip(
            axes, METRIKEN
        ):
            for offset, zustand in zip(offsets, zustaende):
                for x, punkt in enumerate(["TP1", "TP2", "TP3"]):
                    werte = teil.loc[
                        (teil["Condition"] == zustand)
                        & (teil["Point"] == punkt)
                        & (teil["Protokoll"] == protokoll),
                        spalte,
                    ].dropna()

                    if werte.empty:
                        continue

                    position = x + offset
                    mittel = werte.mean()
                    sd = werte.std(ddof=1)

                    # Tatsächliche Einzelmessungen
                    jitter = np.linspace(
                        -0.035, 0.035, len(werte)
                    ) if len(werte) > 1 else [0]

                    ax.scatter(
                        position + np.array(jitter),
                        werte,
                        color=FARBEN[zustand],
                        alpha=0.55,
                        s=28,
                        zorder=3,
                    )

                    # Mittelwert mit Stichprobenstandardabweichung
                    ax.errorbar(
                        position,
                        mittel,
                        yerr=sd if len(werte) > 1 else None,
                        fmt="D",
                        color=FARBEN[zustand],
                        markersize=6,
                        capsize=4,
                        zorder=4,
                    )

                    if len(werte) != 3:
                        ax.annotate(
                            f"n={len(werte)}",
                            (position, werte.max()),
                            xytext=(0, 10),
                            textcoords="offset points",
                            ha="center",
                            fontsize=9,
                        )

            ax.set_title(titel)
            ax.set_ylabel(einheit)
            ax.set_xticks([0, 1, 2], ["TP1", "TP2", "TP3"])
            ax.set_xlim(-0.5, 2.5)
            ax.set_ylim(bottom=0)
            ax.margins(y=0.18)
            ax.grid(axis="y", alpha=0.2)

        handles = [
            Line2D(
                [0], [0],
                marker="D",
                linestyle="",
                color=FARBEN[z],
                label=z,
            )
            for z in zustaende
        ]

        axes[0].legend(handles=handles, fontsize=9)
        fig.suptitle(
            f"{person} | {band}\n"
            "Dots: individual runs · Diamonds: mean · Error bars: ±1 SD",
            fontsize=16,
        )

        band_datei = band.replace(".", "_").replace(" ", "")
        speichern(fig, f"{person}_{band_datei}_comparison")


# --------------------------------------------------
# 2. Änderungen gegenüber der passenden Baseline
# --------------------------------------------------
vergleich = []

for person in sorted(df["Person"].unique()):
    for band in ["2.4 GHz", "5 GHz"]:
        for punkt in ["TP1", "TP2", "TP3"]:
            for zustand in ["Channel change", "Foil shielding"]:
                if band == "2.4 GHz" and zustand == "Foil shielding":
                    continue

                for protokoll, spalte, titel, einheit in METRIKEN:
                    gemeinsam = df[
                        (df["Person"] == person)
                        & (df["Band"] == band)
                        & (df["Point"] == punkt)
                        & (df["Protokoll"] == protokoll)
                    ]

                    baseline = gemeinsam.loc[
                        gemeinsam["Condition"] == "Baseline", spalte
                    ].dropna()

                    intervention = gemeinsam.loc[
                        gemeinsam["Condition"] == zustand, spalte
                    ].dropna()

                    if baseline.empty or intervention.empty:
                        continue

                    basis = baseline.mean()
                    neu = intervention.mean()
                    differenz = neu - basis

                    vergleich.append({
                        "Person": person,
                        "Band": band,
                        "Point": punkt,
                        "Intervention": zustand,
                        "Metric": titel,
                        "Baseline_mean": basis,
                        "Intervention_mean": neu,
                        "Absolute_change": differenz,
                        "Unit": (
                            "percentage points"
                            if spalte == "Paketverlust_Prozent"
                            else einheit
                        ),
                        "Relative_change_percent": (
                            differenz / basis * 100
                            if basis != 0 else np.nan
                        ),
                        "Baseline_n": len(baseline),
                        "Intervention_n": len(intervention),
                    })

vergleich = pd.DataFrame(vergleich)

if vergleich.empty:
    raise ValueError("Keine passenden Baseline-Vergleiche gefunden.")

vergleich.to_csv(
    OUTPUT / "Baseline_Vergleiche.csv",
    sep=";",
    index=False,
    encoding="utf-8-sig",
)

# --------------------------------------------------
# 3. Heatmaps
# --------------------------------------------------
heatmaps = [
    (
        "TCP throughput",
        "Relative_change_percent",
        "TCP throughput change vs baseline (%)",
        "Positive = higher throughput",
        True,
    ),
    (
        "UDP jitter",
        "Absolute_change",
        "UDP jitter change vs baseline (ms)",
        "Negative = lower jitter",
        False,
    ),
    (
        "UDP packet loss",
        "Absolute_change",
        "UDP packet loss change vs baseline (percentage points)",
        "Negative = lower packet loss",
        False,
    ),
]

for metrik, wertspalte, titel, untertitel, positiv_gut in heatmaps:
    teil = vergleich[vergleich["Metric"] == metrik].copy()

    teil["Row"] = (
        teil["Person"] + " | "
        + teil["Band"] + " | "
        + teil["Intervention"]
    )

    matrix = teil.pivot(
        index="Row",
        columns="Point",
        values=wertspalte,
    ).reindex(columns=["TP1", "TP2", "TP3"])

    werte = matrix.to_numpy(dtype=float)
    endlich = werte[np.isfinite(werte)]
    maximum = np.max(np.abs(endlich)) if endlich.size else 0
    grenze = maximum if maximum > 0 else 1

    cmap = plt.get_cmap(
        "RdBu" if positiv_gut else "RdBu_r"
    ).copy()
    cmap.set_bad("#E8E8E8")

    fig, ax = plt.subplots(
        figsize=(10.5, max(3.4, len(matrix) * 0.65)),
        layout="constrained",
    )

    bild = ax.imshow(
        np.ma.masked_invalid(werte),
        cmap=cmap,
        vmin=-grenze,
        vmax=grenze,
        aspect="auto",
    )

    ax.set_xticks(range(3), ["TP1", "TP2", "TP3"])
    ax.set_yticks(range(len(matrix)), matrix.index)
    ax.set_title(f"{titel}\n{untertitel}", pad=16)

    for i in range(werte.shape[0]):
        for j in range(werte.shape[1]):
            wert = werte[i, j]

            text = "n/a" if not np.isfinite(wert) else f"{wert:+.2f}"
            farbe = (
                "white"
                if np.isfinite(wert) and abs(wert) > grenze * 0.55
                else "black"
            )

            ax.text(
                j, i, text,
                ha="center", va="center",
                color=farbe, fontsize=11,
            )

    fig.colorbar(bild, ax=ax, shrink=0.8)
    name = metrik.lower().replace(" ", "_")
    speichern(fig, f"heatmap_{name}")

print(f"Fertig! Diagramme liegen in:\n{PLOTS}")
print(f"Vergleichstabelle:\n{OUTPUT / 'Baseline_Vergleiche.csv'}")