"""
make_slim_statcast.py
Creates a small, plate-appearance-level copy of a season's Statcast file so it can be
shared/analysed easily. READ-ONLY on your existing data: it never modifies statcast_{season}.parquet.

Usage (from the project folder):
    python scripts/make_slim_statcast.py            # defaults to 2026
    python scripts/make_slim_statcast.py 2025

Output: data/statcast_slim_{season}.parquet
Also prints a column report (which wanted columns exist / how filled they are).
"""
import os
import sys
import pyarrow.parquet as pq
import pandas as pd

season = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(root, "data", f"statcast_{season}.parquet")
dst = os.path.join(root, "data", f"statcast_slim_{season}.parquet")

WANTED = [
    "game_pk", "game_date", "at_bat_number", "pitch_number", "inning", "inning_topbot",
    "home_team", "away_team", "outs_when_up", "bat_score", "post_bat_score",
    "batter", "pitcher", "player_name", "stand", "p_throws",
    "events", "description", "type", "bb_type",
    "launch_speed", "launch_angle", "launch_speed_angle",
    "estimated_slg_using_speedangle", "estimated_woba_using_speedangle", "woba_value",
]

if not os.path.exists(src):
    sys.exit(f"Not found: {src}")

names = pq.ParquetFile(src).schema.names
present = [c for c in WANTED if c in names]
missing = [c for c in WANTED if c not in names]

df = pq.read_table(src, columns=present).to_pandas()
total_rows = len(df)

# Keep only the pitch that ended each plate appearance
df = df[df["events"].notna()].copy()

df.to_parquet(dst, index=False)

print(f"Season {season}: {total_rows:,} pitches -> {len(df):,} plate-appearance rows")
print(f"Wrote {dst}  ({os.path.getsize(dst) / 1024 / 1024:.1f} MB)")
print("Missing columns:", missing if missing else "none")
for c in ["estimated_slg_using_speedangle", "launch_speed", "pitcher", "game_pk"]:
    if c in df.columns:
        print(f"  {c}: {df[c].notna().mean() * 100:.1f}% filled")
