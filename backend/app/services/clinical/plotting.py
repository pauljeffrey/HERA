"""Render simple charts for the chat agent, saved as PNGs for static serving."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PLOTS_DIR = Path(__file__).resolve().parents[1] / "data" / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

ChartType = Literal["bar", "line", "scatter"]


def render_chart(
    chart_type: ChartType,
    labels: list[str],
    values: list[float],
    title: str,
    *,
    x_label: str = "",
    y_label: str = "",
) -> Path:
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)

    if chart_type == "bar":
        ax.bar(labels, values, color="#047857")
    elif chart_type == "line":
        ax.plot(labels, values, color="#047857", marker="o")
    elif chart_type == "scatter":
        ax.scatter(labels, values, color="#047857")
    else:
        raise ValueError(f"Unsupported chart_type: {chart_type!r}")

    ax.set_title(title)
    if x_label:
        ax.set_xlabel(x_label)
    if y_label:
        ax.set_ylabel(y_label)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()

    path = PLOTS_DIR / f"{uuid.uuid4()}.png"
    fig.savefig(path)
    plt.close(fig)
    return path
