"""Central configuration: paths, release schedule and the default knowledge cutoff."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw" / "Veloxa_Hackathon_Release_Packs"
DB_PATH = ROOT / "data" / "veloxa.db"
SCHEMA_VERSION = 3  # bump to force a clean rebuild of the generated SQLite DB

RELEASES = {
    "Day1": "2026-11-16T10:00:00+05:30",
    "Day2": "2026-11-17T10:00:00+05:30",
    "Day3": "2026-11-18T10:00:00+05:30",
    "Day4": "2026-11-19T10:00:00+05:30",
}
DAY_ORDER = ["Day1", "Day2", "Day3", "Day4"]
RELEASE_BY_FOLDER = {
    "Day1_Mon_16Nov": RELEASES["Day1"],
    "Day2_Tue_17Nov": RELEASES["Day2"],
    "Day3_Wed_18Nov": RELEASES["Day3"],
    "Day4_Thu_19Nov": RELEASES["Day4"],
}
DAY_BY_FOLDER = {k: k.split("_")[0] for k in RELEASE_BY_FOLDER}
DEFAULT_AS_OF = "2026-11-20T18:00:00+05:30"  # code freeze: everything released is visible


def ts(value) -> pd.Timestamp:
    """Parse to a timezone-aware timestamp (naive input is treated as IST)."""
    t = pd.Timestamp(value)
    if t.tzinfo is None:
        t = t.tz_localize("Asia/Kolkata")
    return t


def available(as_of: str, day: str) -> bool:
    """True when the release `day` had been handed to the cockpit at `as_of`."""
    return ts(as_of) >= ts(RELEASES[day])


def days_available(as_of: str) -> list[str]:
    return [d for d in DAY_ORDER if available(as_of, d)]
