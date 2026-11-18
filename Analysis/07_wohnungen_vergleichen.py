import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from common import read_csv, PLOTS

df = read_csv("01_runs.csv")

if df.empty:
    raise RuntimeError("Bitte zuerst run_all.py ausführen.")

df = df[
    (df["usable"] == True)
    & (df["condition"] == "Baseline")
]

personen = ["Ahmet", "Nemanja"]
farben = {"Ahmet": "#245580", "Nemanja": "#DE8035"}

metriken = [
    ("TCP", "throughput_mbps", "TCP throughput", "Mbit/s"),
    ("UDP", "jitter_ms", "UDP jitter", "ms"),
    ("UDP", "loss_pct", "UDP packet loss", "%"),
]

PLOTS.mkdir(parents=True, exist_ok=True)

for band in ["2.4 GHz", "5 GHz"]:
    fig, axes = plt.subplots(
        1, 3,
        figsize=(16, 5),
        layout="constrained"
    )

    for ax, (protokoll, spalte, titel, einheit) in zip(
        axes, metriken
    ):
        for person, offset in zip(personen, [-0.12, 0.12]):
            for x, punkt in enumerate(["TP1", "TP2", "TP3"]):
                werte = df.loc[
                    (df["person"] == person)
                    & (df["band"] == band)
                    & (df["point"] == punkt)
                    & (df["protocol"] == protokoll),
                    spalte
                ].dropna()

                if werte.empty:
                    continue

                position = x + offset

                ax.scatter(
                    position + np.linspace(-0.025, 0.025, len(werte)),
                    werte,
                    color=farben[person],
                    alpha=0.5,
                    s=30
                )

                ax.errorbar(
                    position,
                    werte.mean(),
                    yerr=werte.std(ddof=1) if len(werte) > 1 else None,
                    fmt="D",
                    color=farben[person],
                    capsize=4,
                    markersize=7,
                    label=person if x == 0 else None
                )

                ax.annotate(
                    f"n={len(werte)}",
                    (position, werte.max()),
                    xytext=(0, 10),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8
                )

        ax.set_title(titel)
        ax.set_ylabel(einheit)
        ax.set_xticks([0, 1, 2], ["TP1", "TP2", "TP3"])
        ax.set_xlim(-0.5, 2.5)
        ax.set_ylim(bottom=0)
        ax.margins(y=0.2)
        ax.grid(axis="y", alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)

    axes[0].legend()

    fig.suptitle(
        f"Baseline comparison | {band}\n"
        "Individual runs and mean ±1 SD · Different hardware and environments",
        fontsize=15
    )

    name = f"baseline_comparison_{band.replace(' ', '').replace('.', '_')}"

    for endung in ["png", "svg"]:
        fig.savefig(
            PLOTS / f"{name}.{endung}",
            dpi=220,
            bbox_inches="tight"
        )

    plt.close(fig)

print(f"Fertig! Diagramme liegen in:\n{PLOTS}")