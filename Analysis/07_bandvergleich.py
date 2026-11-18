import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from common import read_csv, write_csv, PLOTS

df = read_csv("02_summary.csv")

if df.empty:
    raise RuntimeError("Zuerst run_all.py ausführen.")

tcp = df[
    (df["metric"] == "throughput_mbps")
    & df["condition"].isin(["Baseline", "Channel change"])
]

# Mittelwerte beider Bänder am gleichen Standort zusammenführen
keys = ["person", "condition", "point"]

low = tcp[tcp["band"] == "2.4 GHz"][
    keys + ["mean", "n"]
].rename(columns={"mean": "mbps_24", "n": "n_24"})

high = tcp[tcp["band"] == "5 GHz"][
    keys + ["mean", "n"]
].rename(columns={"mean": "mbps_5", "n": "n_5"})

vergleich = low.merge(high, on=keys, validate="one_to_one")

# Bei null Durchsatz auf 2,4 GHz ist das Verhältnis nicht definiert.
vergleich["factor_5_vs_24"] = (
    vergleich["mbps_5"]
    / vergleich["mbps_24"].where(vergleich["mbps_24"] > 0)
)

write_csv("07_bandvergleich.csv", vergleich)

fig, axes = plt.subplots(
    1, 2, figsize=(12, 5),
    sharey=True, layout="constrained"
)

farben = {
    "Baseline": "#245580",
    "Channel change": "#119C86"
}

for ax, person in zip(axes, ["Ahmet", "Nemanja"]):
    for condition, offset in [
        ("Baseline", -0.17),
        ("Channel change", 0.17)
    ]:
        teil = (
            vergleich[
                (vergleich["person"] == person)
                & (vergleich["condition"] == condition)
            ]
            .set_index("point")
            .reindex(["TP1", "TP2", "TP3"])
        )

        x = np.arange(3) + offset
        werte = teil["factor_5_vs_24"].to_numpy()

        ax.bar(
            x, werte, width=0.30,
            color=farben[condition],
            label=condition
        )

        for position, wert in zip(x, werte):
            if np.isfinite(wert):
                ax.annotate(
                    f"{wert:.2f}×",
                    (position, wert),
                    xytext=(0, 5),
                    textcoords="offset points",
                    ha="center"
                )
            else:
                ax.text(
                    position, 0.04, "n/a",
                    transform=ax.get_xaxis_transform(),
                    ha="center"
                )

    ax.axhline(1, color="black", linestyle="--", linewidth=1)
    ax.set_title(person, fontsize=15)
    ax.set_xticks([0, 1, 2], ["TP1", "TP2", "TP3"])
    ax.set_ylabel("Mean TCP throughput: 5 GHz / 2.4 GHz")
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    ax.margins(y=0.2)
    ax.spines[["top", "right"]].set_visible(False)

axes[0].legend()

fig.suptitle(
    "How does the advantage of 5 GHz change across locations?\n"
    "Ratio of means · Dashed line = equal throughput",
    fontsize=15
)

PLOTS.mkdir(parents=True, exist_ok=True)

for ext in ["png", "svg"]:
    fig.savefig(
        PLOTS / f"07_bandvergleich.{ext}",
        dpi=220, bbox_inches="tight"
    )

plt.close(fig)
print(f"Fertig: {PLOTS / '07_bandvergleich.png'}")