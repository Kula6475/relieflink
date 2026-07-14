"""Baseline demand forecasting from historical data.

A real deployment would load actual distribution logs. For the hackathon we generate a
deterministic 90-day daily-demand history per (site, category) with a slow trend, weekly
seasonality (weekend pickups run hotter), and noise, then fit:

    linear trend (least squares)  x  average weekday factor

and project that over the requested horizon. The point is that "baseline demand" comes
from a fitted model, not a hardcoded constant, and swapping in real CSV logs later only
means replacing generate_history().
"""

import random
from datetime import date, timedelta

from shared.config import CATEGORIES

# Typical daily units a mid-sized site moves per category (anchors the synthetic data).
TYPICAL_DAILY = {"canned_goods": 120, "produce": 80, "dairy": 60, "dry_goods": 100}

HISTORY_DAYS = 90

# Mon..Sun demand shape: weekends and Fridays are the busy pickup days.
WEEKDAY_SHAPE = [0.90, 0.85, 0.90, 1.00, 1.10, 1.30, 1.25]


def generate_history(
    site_id: int, category: str, days: int = HISTORY_DAYS, end: date | None = None
) -> list[tuple[date, float]]:
    """Deterministic synthetic daily demand for one (site, category).

    Seeded by (site_id, category) so every run and every teammate sees the same
    history. Returns [(day, units), ...] oldest first.
    """
    end = end or date.today()
    rng = random.Random(site_id * 1000 + CATEGORIES.index(category))

    base = TYPICAL_DAILY[category] * rng.uniform(0.7, 1.3)  # sites differ in size
    trend_per_day = rng.uniform(-0.15, 0.35) * base / days  # slow drift up or down

    history = []
    for i in range(days):
        day = end - timedelta(days=days - i)
        level = base + trend_per_day * i
        seasonal = WEEKDAY_SHAPE[day.weekday()]
        noise = rng.gauss(1.0, 0.08)
        history.append((day, max(0.0, level * seasonal * noise)))
    return history


def fit(history: list[tuple[date, float]]):
    """Fit linear trend + weekday factors. Returns predict(day) -> units."""
    n = len(history)
    ys = [units for _, units in history]
    x_mean = (n - 1) / 2
    y_mean = sum(ys) / n

    slope = sum((x - x_mean) * (y - y_mean) for x, y in enumerate(ys)) / sum(
        (x - x_mean) ** 2 for x in range(n)
    )
    intercept = y_mean - slope * x_mean

    # Average detrended weekday factor, so the profile survives the trend removal.
    totals, counts = [0.0] * 7, [0] * 7
    for x, (day, units) in enumerate(history):
        trend_value = intercept + slope * x
        if trend_value > 0:
            totals[day.weekday()] += units / trend_value
            counts[day.weekday()] += 1
    factors = [totals[w] / counts[w] if counts[w] else 1.0 for w in range(7)]

    start_day = history[0][0]

    def predict(day: date) -> float:
        x = (day - start_day).days
        return max(0.0, (intercept + slope * x) * factors[day.weekday()])

    return predict


def baseline_demand(
    site_id: int, category: str, horizon_hours: int, start: date | None = None
) -> float:
    """Projected units needed over the next horizon_hours under NORMAL conditions.

    Sums the fitted model day by day, taking fractional days at the horizon edge.
    """
    start = start or date.today()
    predict = fit(generate_history(site_id, category, end=start))

    total, hours_left, day = 0.0, horizon_hours, start
    while hours_left > 0:
        take = min(24, hours_left)
        total += predict(day) * take / 24
        hours_left -= take
        day += timedelta(days=1)
    return total
