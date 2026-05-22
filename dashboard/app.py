"""Streamlit dashboard for KAG stock forecasting outputs."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from kag.config import Settings
from kag.dashboard.data import (
    build_investment_simulation,
    load_correlations,
    load_model_metrics,
    load_prediction_rows,
    load_price_history,
    load_sector_counts,
    load_stock_options,
    prediction_label,
)
from kag.graph.client import Neo4jClient


st.set_page_config(
    page_title="IHSG KAG Forecasting",
    page_icon="chart_with_upwards_trend",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=60)
def cached_predictions() -> list[dict]:
    return load_prediction_rows()


@st.cache_data(ttl=60)
def cached_metrics() -> dict:
    return load_model_metrics()


@st.cache_data(ttl=60)
def cached_graph_data() -> tuple[list[dict], list[dict]]:
    settings = Settings.from_env()
    with Neo4jClient(settings) as client:
        return load_stock_options(client), load_sector_counts(client)


@st.cache_data(ttl=60)
def cached_stock_graph_data(ticker: str) -> tuple[list[dict], list[dict]]:
    settings = Settings.from_env()
    with Neo4jClient(settings) as client:
        return load_price_history(client, ticker), load_correlations(client, ticker)


def main() -> None:
    st.title("IHSG KAG Forecasting Dashboard")

    predictions = cached_predictions()
    metrics_payload = cached_metrics()
    stock_options, sector_counts = cached_graph_data()

    if not stock_options:
        st.error("Neo4j has no Stock nodes. Run the ingestion scripts first.")
        return

    prediction_by_ticker = {row["ticker"]: row for row in predictions}
    selected_ticker = render_sidebar(stock_options)
    selected_stock = next(stock for stock in stock_options if stock["ticker"] == selected_ticker)
    price_history, correlations = cached_stock_graph_data(selected_ticker)

    render_market_overview(predictions, stock_options, sector_counts, metrics_payload)
    render_stock_detail(selected_stock, prediction_by_ticker.get(selected_ticker), price_history)
    render_investment_simulator(selected_ticker, prediction_by_ticker.get(selected_ticker), price_history)
    render_graph_context(correlations, sector_counts)


def render_sidebar(stock_options: list[dict]) -> str:
    st.sidebar.header("Controls")
    priced_stock_options = [stock for stock in stock_options if stock.get("has_price")]
    show_all_stocks = st.sidebar.checkbox("Show all IDX stocks", value=True)
    visible_stock_options = (
        stock_options if show_all_stocks or not priced_stock_options else priced_stock_options
    )
    ticker_labels = {
        f"{stock['ticker']} - {stock.get('name') or stock['ticker']}": stock["ticker"]
        for stock in visible_stock_options
    }
    selected_label = st.sidebar.selectbox("Stock", options=list(ticker_labels), index=0)
    st.sidebar.caption(
        f"Data source: Neo4j graph + yfinance historical prices. "
        f"{len(priced_stock_options)} of {len(stock_options)} stocks have price history."
    )
    return ticker_labels[selected_label]


def render_market_overview(
    predictions: list[dict],
    stock_options: list[dict],
    sector_counts: list[dict],
    metrics_payload: dict,
) -> None:
    prediction_frame = pd.DataFrame(predictions)
    sector_frame = pd.DataFrame(sector_counts)
    metrics = metrics_payload.get("metrics", {})

    top_cols = st.columns(4)
    top_cols[0].metric("Stocks", len(stock_options))
    top_cols[1].metric("Sectors", len(sector_counts))
    top_cols[2].metric("Predictions", len(predictions))
    top_cols[3].metric("ROC AUC", f"{metrics.get('roc_auc', 0):.3f}")

    chart_cols = st.columns([1.15, 0.85])
    with chart_cols[0]:
        st.subheader("Latest Direction Probabilities")
        if prediction_frame.empty:
            st.info("No prediction CSV found yet.")
        else:
            prediction_frame = prediction_frame.sort_values("probability_up", ascending=False)
            fig = px.bar(
                prediction_frame,
                x="ticker",
                y="probability_up",
                color="sector",
                range_y=[0, 1],
                labels={"probability_up": "Probability Up", "ticker": "Ticker"},
            )
            fig.update_layout(height=360, margin=dict(l=8, r=8, t=24, b=8))
            st.plotly_chart(fig, use_container_width=True)

    with chart_cols[1]:
        st.subheader("Sector Coverage")
        if sector_frame.empty:
            st.info("No sector data available.")
        else:
            fig = px.bar(
                sector_frame,
                x="stocks",
                y="sector",
                orientation="h",
                labels={"stocks": "Stocks", "sector": "Sector"},
            )
            fig.update_layout(height=360, margin=dict(l=8, r=8, t=24, b=8))
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Model Evaluation")
    metric_cols = st.columns(5)
    for column, metric_name in zip(
        metric_cols,
        ["accuracy", "precision", "recall", "f1", "roc_auc"],
        strict=True,
    ):
        column.metric(metric_name.replace("_", " ").title(), f"{metrics.get(metric_name, 0):.3f}")
    if metrics_payload:
        st.caption(
            f"Train: {metrics_payload.get('train_start_date')} to {metrics_payload.get('train_end_date')} - "
            f"Test: {metrics_payload.get('test_start_date')} to {metrics_payload.get('test_end_date')} - "
            f"Model: {metrics_payload.get('model_type')}"
        )


def render_stock_detail(selected_stock: dict, prediction: dict | None, price_history: list[dict]) -> None:
    st.subheader(f"{selected_stock['ticker']} - {selected_stock.get('name') or selected_stock['ticker']}")

    info_cols = st.columns(4)
    info_cols[0].metric("Sector", selected_stock.get("sector", "UNKNOWN"))
    if prediction:
        probability = prediction.get("probability_up") or 0
        direction = prediction_label(prediction.get("predicted_direction"))
        info_cols[1].metric("Prediction", direction)
        info_cols[2].metric("Probability Up", f"{probability:.1%}")
        info_cols[3].metric("Latest Close", f"{prediction.get('close') or 0:,.0f}")
    else:
        info_cols[1].metric("Prediction", "Missing")
        info_cols[2].metric("Probability Up", "n/a")
        info_cols[3].metric("Latest Close", "n/a")

    price_frame = pd.DataFrame(price_history)
    if price_frame.empty:
        st.info("No price history available for this stock.")
        return

    price_frame["date"] = pd.to_datetime(price_frame["date"])
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=price_frame["date"],
            open=price_frame["open"],
            high=price_frame["high"],
            low=price_frame["low"],
            close=price_frame["close"],
            name="OHLC",
        )
    )
    fig.add_trace(
        go.Bar(
            x=price_frame["date"],
            y=price_frame["volume"],
            name="Volume",
            yaxis="y2",
            marker_color="rgba(110, 130, 150, 0.25)",
        )
    )
    fig.update_layout(
        height=480,
        margin=dict(l=8, r=8, t=24, b=8),
        xaxis_rangeslider_visible=False,
        yaxis=dict(title="Price"),
        yaxis2=dict(title="Volume", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_investment_simulator(
    ticker: str,
    prediction: dict | None,
    price_history: list[dict],
) -> None:
    st.subheader("Investment Simulator")
    st.caption(
        "Scenario view only. Historical sections use realized prices; future sections use a simple model-adjusted projection."
    )

    price_frame = pd.DataFrame(price_history)
    if price_frame.empty:
        st.info("No price data available for simulation.")
        return

    price_frame["date"] = pd.to_datetime(price_frame["date"])
    min_date = price_frame["date"].min().date()
    latest_date = price_frame["date"].max().date()
    default_entry = max(min_date, latest_date - timedelta(days=30))
    default_exit = latest_date + timedelta(days=30)

    with st.form(f"investment-simulator-{ticker}"):
        cols = st.columns(3)
        amount = cols[0].number_input(
            "Investment Amount",
            min_value=100_000.0,
            value=10_000_000.0,
            step=100_000.0,
            format="%.0f",
        )
        entry_date = cols[1].date_input(
            "Entry Date",
            value=default_entry,
            min_value=min_date,
            max_value=latest_date,
        )
        exit_date = cols[2].date_input(
            "Exit Date",
            value=default_exit,
            min_value=entry_date,
            max_value=latest_date + timedelta(days=365),
        )
        submitted = st.form_submit_button("Run Simulation")

    if not submitted:
        return

    try:
        simulation = build_investment_simulation(
            price_history,
            amount=amount,
            entry_date=entry_date.isoformat(),
            exit_date=exit_date.isoformat(),
            probability_up=None if prediction is None else prediction.get("probability_up"),
        )
    except ValueError as exc:
        st.warning(str(exc))
        return

    summary_cols = st.columns(4)
    summary_cols[0].metric("Entry Close", f"{simulation['entry_close']:,.0f}")
    summary_cols[1].metric("Shares", f"{simulation['shares']:,.4f}")
    summary_cols[2].metric("Exit Value", f"{simulation['exit_value']:,.0f}")
    summary_cols[3].metric(
        "P/L",
        f"{simulation['profit_loss']:,.0f}",
        f"{simulation['profit_loss_pct']:.2%}",
    )

    simulation_frame = pd.DataFrame(simulation["rows"])
    simulation_frame["date"] = pd.to_datetime(simulation_frame["date"])
    fig = go.Figure()
    historical = simulation_frame[simulation_frame["kind"] == "historical"]
    projected = simulation_frame[simulation_frame["kind"] == "projected"]
    if not historical.empty:
        fig.add_trace(
            go.Scatter(
                x=historical["date"],
                y=historical["value"],
                mode="lines",
                name="Historical Value",
                line=dict(color="#2563eb", width=2),
            )
        )
    if not projected.empty:
        fig.add_trace(
            go.Scatter(
                x=projected["date"],
                y=projected["upper_value"],
                mode="lines",
                name="Projected Upper",
                line=dict(color="rgba(22, 163, 74, 0.25)", width=0),
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=projected["date"],
                y=projected["lower_value"],
                mode="lines",
                name="Projected Range",
                fill="tonexty",
                fillcolor="rgba(22, 163, 74, 0.14)",
                line=dict(color="rgba(22, 163, 74, 0.25)", width=0),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=projected["date"],
                y=projected["value"],
                mode="lines",
                name="Projected Value",
                line=dict(color="#16a34a", width=2, dash="dash"),
            )
        )
    fig.update_layout(
        height=420,
        margin=dict(l=8, r=8, t=24, b=8),
        yaxis=dict(title="Portfolio Value"),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_graph_context(correlations: list[dict], sector_counts: list[dict]) -> None:
    left, right = st.columns([1.2, 0.8])

    with left:
        st.subheader("Correlation Context")
        if not correlations:
            st.info("No correlation relationships passed the current threshold.")
        else:
            correlation_frame = pd.DataFrame(correlations)
            correlation_frame["coefficient"] = correlation_frame["coefficient"].round(4)
            st.dataframe(
                correlation_frame,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "peer_ticker": "Peer",
                    "peer_name": "Name",
                    "coefficient": "Correlation",
                    "observations": "Obs",
                    "first_date": "First",
                    "last_date": "Last",
                },
            )

    with right:
        st.subheader("Graph Snapshot")
        total_stocks = sum(row["stocks"] for row in sector_counts)
        st.metric("Graph Stocks", total_stocks)
        st.metric("Sector Nodes", len(sector_counts))
        st.caption("Correlation relationships use Pearson close returns from yfinance PricePoint nodes.")


if __name__ == "__main__":
    main()
