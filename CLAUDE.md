# Baseball Analytics — Project Guide for Claude

Local Streamlit app for exploring MLB data (Statcast pitch-level data, Baseball Reference stats, Baseball Savant percentiles) plus a Yahoo Fantasy Baseball dashboard for the owner's points league. Data is downloaded once into `data/*.parquet` and everything else reads locally.

> Written from a full read of the code on 2026-10-17. Things I could not verify are marked **(unverified)**. Update this file after significant changes.

## Open items

The owner's to-do list. Add items when asked; remove an item (or move it to "Done recently") once it is finished and verified. Keep this list short; if it passes ~12 items, move it to `TODO.md` and leave a pointer here. Numbers in brackets refer to "Known quirks" below.

1. **Test the Ask page with a real API key.** Built 2026-11-06 but never run against the Claude API (no key on the machine). Add `anthropic_api_key` to `data/user_settings.json` or set `ANTHROPIC_API_KEY`, then try the sample questions and check answers against the queries shown.
2. **Merge branch `ask-page-and-name-fix` into `main` and push** when ready. Pushing `main` redeploys the Streamlit Cloud app. `data/yahoo_fantasy_data.json` was left out of the commit on purpose (the local copy is the empty cache from the last refresh).
3. **Fantasy AVG always shows 0**: read `BA` instead of `AVG` in `build_player_scoring_table`. [1]
4. **Player Comparison metrics that never appear** because of FanGraphs-style column names (AVG, wOBA, K/9…). Remap to BRef names or remove. [2]
5. **Empty Yahoo cache** after the last Smart Refresh (`league_info: null`). Find the cause; don't save an empty result over good data. [5]
6. **Slow pages**: add `st.cache_data` to the `load_*` functions, especially Statcast. [10]

Done recently:
- 2026-11-06: BRef accented names fixed (scraper + stored files).
- 2026-11-06: Ask page + name fix committed on branch `ask-page-and-name-fix` (66202c1).

## Run it

- Windows: double-click `START_APP.bat` (runs `python -m streamlit run app.py`, opens http://localhost:8501).
- Install: `pip install -r requirements.txt` (includes `duckdb` and `anthropic` for the Ask page).
- No tests, no linter config, no CI. Verify changes by running the app and exercising the page.
- Theme and server settings: `.streamlit/config.toml` (dark theme, orange accent `#E87A2C`, port 8501).

## Secrets: never read, print, or commit these

- `data/user_settings.json` — Yahoo client ID/secret/league ID (gitignored).
- `.yahoo_token.json` (project root) — Yahoo OAuth token (gitignored).
- `data/user_settings.json` may also hold `anthropic_api_key` (used by the Ask page; also read from env `ANTHROPIC_API_KEY`).
- On Streamlit Cloud these come from `st.secrets` (`YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_LEAGUE_ID`, `ANTHROPIC_API_KEY`).

## Directory map

```
app.py                      Home page: first-run setup wizard, data-freshness banner, nav links, settings panel
config.py                   Reads data/user_settings.json (+ st.secrets). Exposes DEFAULT_SEASON, AVAILABLE_SEASONS, YAHOO_* constants
pages/                      Streamlit multipage app (only top-level files appear in the sidebar)
  1_Player_Comparison.py    Savant-style percentile charts for up to N players; splits; multi-year view; bookmarks
  2_Hitter_Statcast.py      Batted-ball explorer (filters, charts, SQL-style aggregation builder)
  3_Pitches_Statcast_Viewer.py  Pitch-level explorer: strike-zone location, movement profile, pitch mix
  4_Stats_Browser.py        Baseball Reference stats table, league/division/position filters, aggregation builder, custom charts
  7_Fantasy.py              Yahoo fantasy: roster, teams, scoring, standings, weekly trends, draft board, matchups
  8_Data_Manager.py         Data status table, Smart Refresh (incremental) and Full Re-download
  9_Ask.py                  Plain-language questions: Claude writes DuckDB SQL via a run_sql tool, results + queries shown; manual SQL box in sidebar
  hidden/                   5_Team_Comparison.py, 6_Correlations.py — NOT in nav (parked; see "Disabled features")
  archive/                  Dated snapshots of old page versions. Gitignored. Do not edit or import.
utils/
  data_loader.py            ALL downloading, loading, metadata, split-summary building, shared constants (largest file)
  yahoo_auth.py             Yahoo OAuth2 flow (paste-the-redirect-URL), token file load/refresh
  yahoo_data.py             Yahoo API calls (XML), fantasy scoring rules, player scoring tables, roster→bookmark sync
  charts.py                 Plotly helpers: create_percentile_chart (main one), radar, scatter, distribution, CHART_TEMPLATE
  style.py                  CSS injection, header, render_nav_back (back link + Mobile Mode toggle), render_data_status
  setup.py                  First-run wizard + load/save of user_settings.json
  sql_assistant.py          DuckDB views over data/*.parquet (file access locked to those files), player_ids table, Claude tool loop (model/effort constants at top)
  schema_guide.md           Table/column guide sent to Claude as its system prompt. Accuracy of the Ask page depends on it: update it when data shape changes
  archive/                  Old copies of utils (gitignored; ignore)
archive/                    Old app.py/config.py (gitignored; ignore)
data/                       Local data store (see below)
```

## Data sources

| Source | How fetched | Produces |
|---|---|---|
| Statcast pitch-level | `pybaseball.statcast` in 7-day chunks | `statcast_{season}.parquet` (~700k rows, ~100 MB per season) |
| Baseball Reference | scraped with requests + BeautifulSoup from `/leagues/majors/{season}-standard-batting.shtml` and `-pitching.shtml` | `batting_stats_{season}`, `pitching_stats_{season}`, and `_post_` versions for postseason |
| Savant leaderboards | `pybaseball.statcast_batter/pitcher_exitvelo_barrels`, `statcast_batter/pitcher_percentile_ranks` | `statcast_{batting,pitching}_agg_{season}`, `statcast_{batter,pitcher}_pcts_{season}` |
| Player ID lookup | `pybaseball.playerid_reverse_lookup` on batter IDs found in Statcast | `batter_lookup_{season}` (columns `batter`, `batter_name`) |
| Derived | `build_split_summary()` aggregates Statcast by batter × pitcher hand × home/away × month | `split_summary_{season}` (counts and sums, so splits can be recombined exactly) |
| Yahoo Fantasy API | OAuth2, XML responses | `yahoo_fantasy_data.json` (1-hour cache), `yahoo_weekly_player_stats.parquet`, `fantasy_batters/pitchers.parquet`, `fantasy_standings.json` |
| FanGraphs (team stats) | `pybaseball.team_batting/pitching` | `team_{batting,pitching}_{season}` — only 2024/2025 exist; refresh is disabled (see below) |

Other files in `data/`: `metadata.json` (last-refresh timestamps and row counts, keyed like `{dataset}_{season}_last_refresh`; also `statcast_{season}_last_date` for incremental updates), `bookmarks.json` (Player Comparison groups, including auto-generated `Fantasy: <team>` entries), `sb_bookmarks.json` (Stats Browser saved filters), `user_settings.json`.

Seasons supported: 2023–2026 (`AVAILABLE_SEASONS`). Current default: 2026. 2026 Statcast data runs through 2026-09-27 (regular season end).

### Column facts that matter
- BRef batting columns: `Name, Age, Tm, Lg, WAR, G, PA, AB, R, H, 2B, 3B, HR, RBI, SB, CS, BB, SO, BA, OBP, SLG, OPS, OPS+, rOBA, Rbat+, TB, GIDP, HBP, SH, SF, IBB, Pos, Awards`. Note **`BA`, not `AVG`**.
- BRef pitching columns: `... ERA, G, GS, SV, IP, H, R, ER, HR, BB, IBB, SO, HBP, BK, WP, BF, ERA+, FIP, WHIP, H9, HR9, BB9, SO9, SO/BB`. Note `SO9`/`BB9`/`HR9`, not `K/9` etc.
- BRef `Pos` uses the retrosheet-style string like `*6/DH` (`*` = primary, digits = positions: 2=C … 9=RF, D=DH). The Stats Browser parses this.
- Savant agg file name column is `"last_name, first_name"`; Savant percentile files use `player_name` as `"Last, First"`.
- Raw Statcast schema is pybaseball's standard (game_date, batter, player_name [= pitcher], events, description, launch_speed, launch_angle, plate_x/z, pfx_x/z, pitch_type, zone, p_throws, stand, inning_topbot, launch_speed_angle, …). I did not open a Statcast parquet directly **(unverified)**.
- In Statcast, `player_name` is the **pitcher**; batter names only exist after merging `batter_lookup`.

## How the pieces connect

1. **Freshness**: `get_data_status(season)` checks that each dataset file exists and its `metadata.json` timestamp is <24h old. `data_is_fresh` requires *all* of them (including postseason files and split_summary), so the home banner often says "stale" even when the app works.
2. **Refresh**: Data Manager → `refresh_all_data(season, full_statcast)` runs every download in order, finishing with Statcast (incremental by default, resumes from `statcast_{season}_last_date`) and then `build_split_summary`. It then also refreshes Yahoo data if a valid token exists.
3. **Player Comparison** has two modes:
   - Normal: percentiles come from Savant percentile files (already oriented so higher is better) plus percentiles computed in-app from BRef columns via `rank(pct=True)`.
   - Split mode (any hand/venue/month filter active, batters only): stats and percentiles are recomputed from `split_summary` via `combine_split_rows`, restricted to players with `PA >= min_bbe` slider.
4. **Name matching** between BRef (`Name`), Savant (`Last, First`) and the lookup (`batter_name`) is done ad hoc in each page with `unicodedata` normalization, suffix stripping, and a last-name `str.contains` fallback. It is fragile (see quirks).
5. **Fantasy**: scoring is custom (below). Season-long player points are computed from BRef stats (`build_player_scoring_table`); date-range/weekly points are approximated from Statcast (`build_player_scoring_from_statcast`); team/week points and the hitter/pitcher split come from Yahoo's own weekly roster stats (`get_weekly_player_stats`, excludes BN/IL/NA slots).

### Fantasy league rules (in `utils/yahoo_data.py`)
- Batters: 1B +1, 2B +2, 3B +3, HR +4, SB +1, CS −1, BB +1, IBB +1, HBP +1, SO −0.5, GIDP −1.
- Pitchers: Out (IP×3) +1, BB −1, IBB −0.5, HBP −1, SO +0.5, WP −1, BK −1, GIDP induced +1, total bases allowed −1.
- Head-to-head weekly matchups, 12 teams. Edit `BATTER_SCORING` / `PITCHER_SCORING` to change rules; the scoring tab and all tables read from them.

## Conventions and patterns

- **Page skeleton**: `st.set_page_config` → `inject_custom_css()` → `render_nav_back()` → `render_data_status([...keys])` → filters → content. Keep this order.
- **Filter container**: `filters = st.expander(...) if st.session_state.get("mobile_mode") else st.sidebar`, then `with filters:`. Reuse it so Mobile Mode keeps working.
- **Seasons**: always `st.selectbox("Season", AVAILABLE_SEASONS, index=AVAILABLE_SEASONS.index(DEFAULT_SEASON))`.
- **Loading data**: use the `load_*` functions in `data_loader.py`; they return an empty DataFrame when a file is missing, and pages show a "go to Data Manager" warning in that case. Follow this pattern rather than raising.
- **Downloads**: each `download_*` function catches exceptions, shows `st.error`, writes a parquet, and updates `metadata.json` via `_load_metadata/_save_metadata`. New datasets should do the same.
- **Styling**: dark palette `#0E1117` bg, `#1A1D23` cards, `#E87A2C` accent. Use `CHART_TEMPLATE` from `utils/charts.py` for Plotly figures. Percentile colors come from `get_percentile_color`.
- **Persistence**: small JSON files in `data/` (bookmarks), larger tables as parquet. `st.session_state` holds loaded results between reruns.
- **Page file names**: `N_Name.py`, number controls sidebar order. 5 and 6 are intentionally unused in nav.

## Recipes for common changes

- **Add a Savant/BRef stat to Player Comparison**: add its key and label to the relevant dict at the top of `pages/1_Player_Comparison.py` (`BATTER_STATCAST_METRICS`, `BATTER_TRADITIONAL_METRICS`, pitcher equivalents). Savant keys must match columns in `statcast_*_pcts_*.parquet`; traditional keys must match BRef columns. If lower is better, add to `invert_metrics`.
- **Add a split dimension** (e.g., count, inning): add the column to `group_cols` and any needed counts to `agg_dict` in `build_split_summary`, add the field to `combine_split_rows`, then rebuild via Data Manager. Add the filter widget in Player Comparison's Splits section. Store counts/sums, never rates, so rows stay combinable.
- **Add a new page**: copy the skeleton above into `pages/N_Name.py`, add a `st.page_link` in `app.py`.
- **Add a new dataset**: add `download_x`/`load_x` in `data_loader.py`, register it in `get_data_status`'s `datasets` list and `refresh_all_data`, and add a label in `pages/8_Data_Manager.py` (`dataset_labels`) and `render_data_status` (`style.py`).
- **New season rollover**: update `SEASON_DATES` in `data_loader.py`; `default_season`/`available_seasons` in settings (and the hard-coded `[2026, 2025, 2024, 2023]` lists in `config.py`, `utils/setup.py`, the wizard in `setup.py`); and both copies of `WEEK_DATES` (hard-coded 2026 week boundaries) in `pages/7_Fantasy.py`; TEAM_DIVISIONS in the Stats Browser if teams change.
- **Change fantasy scoring**: edit `BATTER_SCORING` / `PITCHER_SCORING`. Re-run Smart Refresh to regenerate `fantasy_*.parquet`.

## Known quirks, bugs, and tech debt

Confirmed by reading code and data:

1. **Fantasy `AVG` is always 0.** `build_player_scoring_table` reads `row.get("AVG")` but BRef calls it `BA`. Confirmed in `fantasy_batters.parquet` (all 726 AVG values are 0.0). Fix: read `BA`.
2. **Several Player Comparison metrics silently never appear.** Batters: `AVG`, `wOBA`, `wRC+`, `ISO`, `BB%`, `K%` don't exist in the BRef files (these were FanGraphs names). Pitchers: `K/9`, `BB/9`, `HR/9`, `K%`, `BB%` (BRef has `SO9`, `BB9`, `HR9`). The code filters to existing columns so nothing errors, but the default-selected list and the "invert" lists reference missing names.
3. **Fixed 2026-11-06: Baseball Reference accented names were mis-encoded** (e.g. `JosÃ© RamÃ­rez`) because the scrapers let `requests` guess Latin-1. Scrapers now set `response.encoding = "utf-8"`, and all 16 stored `batting/pitching_stats*` files were repaired in place. The Ask page still applies `fix_mojibake` as a safety net.
4. **`data_is_fresh` is overly strict** (all datasets incl. postseason, split summary), so the home banner rarely says "up to date".
5. **Last Smart Refresh saved an empty Yahoo cache.** `data/yahoo_fantasy_data.json` currently has `league_info: null, teams: []`, written 2026-10-17 19:54. Cause not determined **(unverified)**; likely a failed Yahoo API call (expired token/auth) followed by `save_yahoo_data` writing the empty result. `refresh_all_data` code path doesn't check for `None` before saving.
6. **Duplicated code**: the Aggregation Builder (WHERE/HAVING/metric pairs) is copy-pasted between `2_Hitter_Statcast.py` and `4_Stats_Browser.py`; bookmark load/save is duplicated in pages 1 and 4 and `yahoo_data.sync_rosters_to_bookmarks`; `WEEK_DATES` appears twice in `7_Fantasy.py`; `normalize()` helpers are redefined inline many times. A shared util would simplify changes.
7. **Name matching is fragile.** Last-name `.str.contains` fallback can match the wrong player (e.g., two batters sharing a surname) when the exact match fails; `strip_name_suffixes` exists only in Player Comparison. Savant-vs-BRef spellings with accents or Jr./Sr. may not match.
8. **Two different barrel definitions.** `build_split_summary` uses Statcast's `launch_speed_angle == 6` per ball in play; `calculate_stats_from_statcast` uses a hand-rolled approximation and appears unused (imported by page 1 but not called).
9. **Statcast-based fantasy points are approximations**: steals taken from `events` (`stolen_base_2b`, `caught_stealing_2b`) are likely incomplete, pitcher outs are estimated from end-of-PA events, and WP/BK/induced-GIDP are set to 0. Season-long BRef-based scoring is accurate; date-range and weekly player views are not.
10. **Performance**: full Statcast parquet files (~100 MB each) are read into memory on every page load; almost nothing uses `st.cache_data` (only a batter lookup in page 3). Adding caching to `load_*` functions would speed up every page.
11. **Season hard-coding**: 2023–2026 and 2026 week dates are scattered through several files (see rollover recipe).
12. `build_split_summary` has a duplicated `ev_90_count` line (harmless). `pages/5` and `6` are parked in `hidden/` and `get_data_status` has team datasets commented out ("re-enable with 5_Team_Comparison"). FanGraphs team data is flagged in code as "likely blocked"; cached 2024/2025 files exist. If re-enabling, check the FanGraphs scrape still works.
13. Player Comparison "qualified" thresholds use 3.1 PA / 1.0 IP per team game, estimated from the max `G` in the table.
14. `data/` is not gitignored and contains ~100 MB parquet files; how the repo handles them (Git LFS? `.gitattributes` exists) **(unverified)**.

## Disabled / parked features

- `pages/hidden/5_Team_Comparison.py` — team batting/pitching/Statcast comparison from FanGraphs team data.
- `pages/hidden/6_Correlations.py` — scatter/distribution/linear-regression explorer with custom `df.eval` columns.
- Both are intact and only need to be moved back into `pages/` (and the team datasets uncommented in `data_loader.py`, `8_Data_Manager.py`) to return.

## Working agreements for Claude

- Prefer small, targeted edits; keep the page skeleton and existing helper patterns.
- When the owner says "add to open items" (or similar), add it to the **Open items** section at the top. When finishing an item, update that list in the same change.
- Never open or echo `data/user_settings.json` or `.yahoo_token.json`.
- Ignore `archive/`, `pages/archive/`, `utils/archive/`.
- Don't re-download data or run the app's refresh without being asked; it hits Baseball Reference and Savant and takes minutes.
- After changes that affect data shape (e.g., `split_summary`), tell the user to run Smart Refresh in Data Manager.
- If asked to add a feature, first state which files will change; for new stats, check the column actually exists in the parquet.
