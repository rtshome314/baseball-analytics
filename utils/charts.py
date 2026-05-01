import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from utils.data_loader import get_percentile_color


CHART_TEMPLATE = dict(
    paper_bgcolor="#0E1117",
    plot_bgcolor="#1A1D23",
    font=dict(color="#FAFAFA", family="sans-serif"),
    colorway=["#E87A2C", "#5B9BD5", "#C6011F", "#F5C242", "#6ABF69",
              "#9B59B6", "#E74C3C", "#3498DB", "#1ABC9C", "#F39C12"],
)


def create_percentile_chart(player_name, percentiles, metrics_labels, raw_values=None, compact=False):
    """
    Create a polished horizontal percentile bar chart.
    compact=True: smaller version for grid view (3-per-row)
    compact=False: full-width detail view
    """
    metrics = list(metrics_labels.keys())
    labels = list(metrics_labels.values())
    values = [percentiles.get(m, 0) for m in metrics]
    colors = [get_percentile_color(v) for v in values]

    if raw_values:
        custom = []
        for m in metrics:
            rv = raw_values.get(m, "")
            if rv != "" and rv is not None:
                try:
                    rv_f = float(rv)
                    custom.append(f"{rv_f:.3f}".rstrip("0").rstrip(".") if rv_f != int(rv_f) else str(int(rv_f)))
                except (ValueError, TypeError):
                    custom.append(str(rv))
            else:
                custom.append("—")
    else:
        custom = ["—" for _ in metrics]

    fig = go.Figure()

    # Reference lines at 25, 50, 75
    for ref in [25, 50, 75]:
        fig.add_vline(
            x=ref, line_width=1, line_dash="dot",
            line_color="rgba(255,255,255,0.08)"
        )

    fig.add_trace(go.Bar(
        y=labels,
        x=values,
        orientation="h",
        marker=dict(
            color=colors,
            line=dict(width=0),
            cornerradius=3,
        ),
        customdata=[[c] for c in custom],
        text=[f" {int(v)}" for v in values],
        textposition="inside",
        insidetextanchor="start",
        textfont=dict(
            color="white",
            size=11 if compact else 13,
            family="'DM Mono', 'Courier New', monospace",
        ),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Percentile: <b>%{x:.0f}</b><br>"
            "Value: <b>%{customdata[0]}</b>"
            "<extra></extra>"
        ),
    ))

    row_height = 22 if compact else 28
    top_margin = 8 if compact else 12
    bottom_margin = 30 if compact else 35
    label_size = 10 if compact else 12

    fig.update_layout(
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        font=dict(color="#FAFAFA", family="sans-serif"),
        xaxis=dict(
            range=[0, 100],
            showgrid=False,
            zeroline=False,
            tickvals=[25, 50, 75],
            ticktext=["25th", "50th", "75th"],
            tickfont=dict(color="#555A66", size=9),
            showline=False,
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=label_size, color="#B0B3BA"),
            showgrid=False,
            showline=False,
        ),
        height=top_margin + bottom_margin + len(metrics) * row_height,
        margin=dict(l=0, r=8, t=top_margin, b=bottom_margin),
        bargap=0.3,
        showlegend=False,
    )
    return fig


def create_comparison_radar(players_data, metrics_labels):
    categories = list(metrics_labels.values())
    fig = go.Figure()

    for player in players_data:
        values = [player["values"].get(m, 0) for m in metrics_labels.keys()]
        values.append(values[0])

        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories + [categories[0]],
            name=player["name"],
            fill="toself",
            opacity=0.3,
            line=dict(width=2),
        ))

    fig.update_layout(
        **CHART_TEMPLATE,
        polar=dict(
            bgcolor="#1A1D23",
            radialaxis=dict(visible=True, range=[0, 100], showticklabels=True,
                            tickfont=dict(color="#8B8D93", size=9), gridcolor="#2A2D35"),
            angularaxis=dict(tickfont=dict(color="#FAFAFA", size=11), gridcolor="#2A2D35"),
        ),
        showlegend=True,
        legend=dict(font=dict(size=12), bgcolor="rgba(26,29,35,0.8)", bordercolor="#2A2D35"),
        height=500,
        margin=dict(l=60, r=60, t=40, b=40),
    )
    return fig


def create_scatter(df, x_col, y_col, color_col=None, hover_name=None, title=""):
    fig = px.scatter(df, x=x_col, y=y_col, color=color_col,
                     hover_name=hover_name, title=title, trendline="ols")
    fig.update_layout(**CHART_TEMPLATE, height=500, margin=dict(l=60, r=30, t=60, b=50))
    fig.update_traces(marker=dict(size=8, opacity=0.7))
    return fig


def create_distribution(df, col, title="", nbins=30):
    fig = px.histogram(df, x=col, nbins=nbins, title=title, color_discrete_sequence=["#E87A2C"])
    fig.update_layout(**CHART_TEMPLATE, height=400, margin=dict(l=60, r=30, t=60, b=50), bargap=0.05)
    return fig