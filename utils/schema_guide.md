# Baseball Analytics — SQL schema guide

You query a DuckDB database of read-only views over local parquet files. Seasons available: 2023–2026 (2026 is the current/most recent season; its regular season ended 2026-09-27). Data was last refreshed in mid-October 2026, so it may not include the most recent postseason games.

Use DuckDB SQL. Quote any column whose name has a symbol or starts with a digit: `"2B"`, `"3B"`, `"OPS+"`, `"Rbat+"`, `"ERA+"`, `"W-L%"`, `"SO/BB"`, `"Fantasy Pts"`, `"Pts/PA"`, `"Is FA"`, `"last_name, first_name"`. Column names are case-sensitive when quoted.

## Choosing a table

| Question is about… | Use |
|---|---|
| Season totals: HR, RBI, AVG, OPS, WAR, ERA, IP, wins, saves | `batting` / `pitching` (Baseball Reference) |
| Team totals, team records, standings | `team_batting` / `team_pitching` |
| Postseason totals | `batting_post` / `pitching_post` |
| Anything by date, game, inning, count, pitch type, opponent, exit velocity, launch angle, location | `statcast` (one row per pitch) |
| Splits vs LHP/RHP, home/away, by month (batters only) | `splits` (or `statcast`) |
| Savant percentile rankings (0–100) | `savant_batter_pct` / `savant_pitcher_pct` |
| Savant exit-velo/barrel leaderboards | `savant_batting` / `savant_pitching` |
| The user's Yahoo fantasy league | `fantasy_batters`, `fantasy_pitchers`, `fantasy_weekly` |
| Linking a Baseball Reference player to Statcast/Savant | `player_ids` |

Prefer `batting`/`pitching` for official season totals. Use `statcast` when the question needs a filter those tables can't do.

---

## batting / pitching — Baseball Reference season stats

One row per player per team per season. Column `season` (INTEGER) is added. All stat columns are DOUBLE.

**`batting`**: `season, Rk, Name, Age, Tm, Lg, WAR, G, PA, AB, R, H, "2B", "3B", HR, RBI, SB, CS, BB, SO, BA, OBP, SLG, OPS, "OPS+", rOBA, "Rbat+", TB, GIDP, HBP, SH, SF, IBB, Pos, Awards`

**`pitching`**: `season, Rk, Name, Age, Tm, Lg, WAR, W, L, "W-L%", ERA, G, GS, GF, CG, SHO, SV, IP, H, R, ER, HR, BB, IBB, SO, HBP, BK, WP, BF, "ERA+", FIP, WHIP, H9, HR9, BB9, SO9, "SO/BB", Awards`

**`batting_post` / `pitching_post`**: same as above for the postseason, minus WAR, OPS+, rOBA, Rbat+ (batting) and some advanced columns. Check with `DESCRIBE batting_post` if unsure.

Critical rules:
- **Traded players have several rows.** A player who played for 2+ teams has one row per team PLUS a combined row whose `Tm` is `'2TM'`, `'3TM'` or `'4TM'`. For a player's season total, use the combined row when it exists and the single row otherwise. Never `SUM` over all of a player's rows. Pattern:
  ```sql
  -- one season-total row per player
  SELECT * FROM batting
  QUALIFY ROW_NUMBER() OVER (PARTITION BY season, Name ORDER BY CASE WHEN Tm LIKE '%TM' THEN 0 ELSE 1 END, PA DESC) = 1
  ```
  For team-level totals, do the opposite: exclude `Tm LIKE '%TM'`.
- **Exclude the league-average row**: `Name` = `'MLB Average'` (batting) or `'League Average'` (pitching), with `Tm` NULL. Filter `Tm IS NOT NULL`.
- Batting average is **`BA`**, not `AVG`. Strikeouts are `SO`. Per-9 rates are `SO9`, `BB9`, `HR9`, `H9` (not K/9).
- `Name` is "First Last" (e.g. `'Cal Raleigh'`), with accents kept (`'Eugenio Suárez'`, `'Ronald Acuña Jr.'`). Match names with `ILIKE '%raleigh%'` first if unsure of spelling, then use the exact name.
- `IP` uses baseball notation: 6.1 = 6⅓ innings, 6.2 = 6⅔. To sum innings, convert: `FLOOR(IP) + (IP - FLOOR(IP)) * 10 / 3`.
- `Tm` uses Baseball Reference codes: ARI, ATH, ATL, BAL, BOS, CHC, CHW, CIN, CLE, COL, DET, HOU, KCR, LAA, LAD, MIA, MIL, MIN, NYM, NYY, PHI, PIT, SDP, SEA, SFG, STL, TBR, TEX, TOR, WSN. `Lg` is AL/NL (or e.g. '2LG' on combined rows).
- `Pos` is a string like `'*2/DH'`: `*` marks primary position; digits 1=P 2=C 3=1B 4=2B 5=3B 6=SS 7=LF 8=CF 9=RF, `D`/`DH` = DH. Primary catcher: `Pos LIKE '*2%'`.
- "Qualified" hitters: about 3.1 PA per team game (502 PA over 162 games). Qualified pitchers: 1 IP per team game (162 IP). For the 2026 season, 162 games were played.

## team_batting / team_pitching — Baseball Reference team totals

One row per team per season (30 rows per season, no league-average rows, no duplicates). Identity columns on both: `season, Team` (full name, e.g. 'Seattle Mariners'), `Tm` (Baseball Reference code, matches `batting.Tm`; the A's are 'OAK' in 2023–24 and 'ATH' from 2025), `sc_team` (Statcast code, matches `statcast.home_team`/`away_team`), `Lg` ('AL'/'NL'), `Div` ('AL East', 'AL Central', 'AL West', 'NL East', 'NL Central', 'NL West').

**`team_batting`**: `"#Bat"` (players used), `BatAge`, `"R/G"`, `G, PA, AB, R, H, "2B", "3B", HR, RBI, SB, CS, BB, SO, BA, OBP, SLG, OPS, "OPS+", TB, GDP, HBP, SH, SF, IBB, LOB`
**`team_pitching`**: `"#P"`, `PAge`, `"RA/G"`, `W, L, "W-L%", ERA, G, GS, GF, CG, tSho, cSho, SV, IP, H, R, ER, HR, BB, IBB, SO, HBP, BK, WP, BF, "ERA+", FIP, WHIP, H9, HR9, BB9, SO9, "SO/W", LOB`

- **Team wins/losses are `team_pitching.W` / `.L`.** Runs scored = `team_batting.R`; runs allowed = `team_pitching.R`. Join the two on `(season, Team)`.
- Games behind in a division: `((leader W − W) + (L − leader L)) / 2`.
- Prefer these tables over summing `batting`/`pitching` by team.

## statcast — pitch-level data (all seasons, regular season only)

One row per pitch, roughly 700,000 rows per season. Large: always filter by `game_year` and aggregate; never `SELECT *` without a tight `WHERE` and `LIMIT`.

Key columns:
- `game_year` (season), `game_date` (TIMESTAMP), `game_pk` (game ID), `home_team`, `away_team`, `inning`, `inning_topbot` ('Top'/'Bot'), `outs_when_up`, `balls`, `strikes`, `at_bat_number`, `pitch_number`, `on_1b/on_2b/on_3b` (runner IDs, NULL if empty)
- **`batter`** (MLBAM ID), **`pitcher`** (MLBAM ID), **`player_name` = the PITCHER's name** ("Last, First"). Batter names are not in this table: join `batter_names` on `(season, batter)`.
- `stand` (batter side L/R), `p_throws` (pitcher hand L/R)
- `pitch_type` (FF four-seam, SI sinker, FC cutter, SL slider, ST sweeper, CU curve, KC knuckle-curve, SV slurve, CH changeup, FS splitter, FO forkball, KN knuckleball, EP eephus, CS slow curve, FA other, PO pitchout), `pitch_name` (full name)
- `release_speed` (mph), `effective_speed`, `release_spin_rate` (rpm), `spin_axis`, `release_extension` (ft), `pfx_x`/`pfx_z` (movement, **feet** — multiply by 12 for inches), `plate_x`/`plate_z` (location, ft), `zone` (1–9 in zone, 11–14 outside), `sz_top`/`sz_bot`, `arm_angle`
- `description` (every pitch): ball, called_strike, swinging_strike, swinging_strike_blocked, foul, foul_tip, foul_bunt, missed_bunt, hit_into_play, blocked_ball, hit_by_pitch, automatic_ball, automatic_strike, pitchout
- `type`: 'B' ball, 'S' strike (incl. fouls), 'X' in play
- **`events`** (only on the last pitch of a plate appearance; NULL otherwise): single, double, triple, home_run, walk, intent_walk, strikeout, strikeout_double_play, hit_by_pitch, field_out, force_out, grounded_into_double_play, double_play, triple_play, fielders_choice, fielders_choice_out, field_error, sac_fly, sac_fly_double_play, sac_bunt, catcher_interf, truncated_pa
- `bb_type`: ground_ball, line_drive, fly_ball, popup
- `launch_speed` (exit velocity, mph), `launch_angle` (deg), `hit_distance_sc` (ft), `hc_x`/`hc_y` (spray), `launch_speed_angle` (1 weak, 2 topped, 3 under, 4 flare/burner, 5 solid, **6 barrel**)
- `estimated_ba_using_speedangle` (xBA), `estimated_woba_using_speedangle` (xwOBA), `estimated_slg_using_speedangle` (xSLG), `woba_value`, `woba_denom`, `babip_value`, `iso_value`
- `delta_run_exp` (run value of the pitch, batter's perspective), `delta_home_win_exp`, `bat_score`, `fld_score`, `post_bat_score`
- `bat_speed`, `swing_length`, `attack_angle`, `attack_direction`, `swing_path_tilt` (bat tracking, on swings only)
- `n_thruorder_pitcher` (times through the order), `age_bat`, `age_pit`

Standard definitions (use these):
- Plate appearances: `COUNT(*) FILTER (WHERE events IS NOT NULL AND events <> 'truncated_pa')`
- Hits: events IN ('single','double','triple','home_run')
- Walks: events IN ('walk','intent_walk'); strikeouts: events IN ('strikeout','strikeout_double_play')
- At-bats: PA minus walks, HBP, sac_fly, sac_fly_double_play, sac_bunt, catcher_interf
- Batted balls: `launch_speed IS NOT NULL AND type = 'X'`. Hard hit: launch_speed >= 95. Barrel: `launch_speed_angle = 6`. Sweet spot: launch_angle BETWEEN 8 AND 32.
- Swings: description IN ('swinging_strike','swinging_strike_blocked','foul','foul_tip','foul_bunt','hit_into_play','missed_bunt'); whiffs: description IN ('swinging_strike','swinging_strike_blocked','missed_bunt'). Whiff% = whiffs / swings.
- In zone: zone BETWEEN 1 AND 9. Chase: swing on a pitch with zone > 9.
- wOBA: SUM(woba_value) / SUM(woba_denom).
- Batting team: `CASE WHEN inning_topbot = 'Top' THEN away_team ELSE home_team END`; pitching team is the other one.
- Statcast team codes are Savant-style and differ from Baseball Reference for some teams (check with `SELECT DISTINCT home_team FROM statcast WHERE game_year = 2026`).
- Counts derived from Statcast match Baseball Reference closely but can differ by 1–2 for some players (scoring changes, truncated PAs). Prefer `batting`/`pitching` for official totals.

## batter_names — batter ID → name

`season, batter, batter_name` ("First Last", but oddly cased: 'Ryan Mcmahon', 'Bobby Witt' without Jr.). One row per batter who appeared in that season's Statcast. Join: `statcast s JOIN batter_names n ON n.season = s.game_year AND n.batter = s.batter`. `splits.batter_name` uses these same names.
There is no separate pitcher lookup: use `statcast.player_name` grouped by `pitcher`.

## splits — batter split summary (precomputed from Statcast)

`season, batter_name, p_throws ('L'/'R' pitcher hand), venue ('Home'/'Away'), month_label ('March/April','May','June','July','August','September/October'), PA, AB, H, "1B", "2B", "3B", HR, BB, HBP, SO, SF, batted_ball_count, ev_sum, la_sum, max_ev, hard_hit_count, barrel_count, bip_count, ev_90_count, ev_95_count, ev_100_count, ev_105_count, ev_110_count`

Rows are counts per batter × pitcher hand × venue × month. **SUM counts first, then compute rates**: AVG = SUM(H)/SUM(AB); OBP = (SUM(H)+SUM(BB)+SUM(HBP)) / (SUM(AB)+SUM(BB)+SUM(HBP)+SUM(SF)); SLG = (SUM("1B")+2*SUM("2B")+3*SUM("3B")+4*SUM(HR))/SUM(AB); avg exit velo = SUM(ev_sum)/SUM(batted_ball_count); barrel% = SUM(barrel_count)/SUM(batted_ball_count). BB here includes intentional walks.

## savant_batter_pct / savant_pitcher_pct — Savant percentile ranks

`player_name` ("Last, First"), `player_id` (MLBAM ID, = statcast batter/pitcher), `year` (season).
Values are **percentile ranks 0–100 (higher = better for that player)**, NOT raw stats. NULL means not qualified.
- Batter: xwoba, xba, xslg, xiso, xobp, brl, brl_percent, exit_velocity, max_ev, hard_hit_percent, k_percent, bb_percent, whiff_percent, chase_percent, arm_strength, sprint_speed, oaa, bat_speed, squared_up_rate, swing_length
- Pitcher: xwoba, xba, xslg, xiso, xobp, brl, brl_percent, exit_velocity, max_ev, hard_hit_percent, k_percent, bb_percent, whiff_percent, chase_percent, arm_strength, xera, fb_velocity, fb_spin, curve_spin

## savant_batting / savant_pitching — Savant exit-velocity & barrel leaderboard (raw values)

`season, "last_name, first_name", player_id, attempts (batted balls), avg_hit_angle, anglesweetspotpercent, max_hit_speed, avg_hit_speed, ev50, fbld, gb, max_distance, avg_distance, avg_hr_distance, ev95plus, ev95percent, barrels, brl_percent, brl_pa`
Minimum 50 batted balls. For pitchers these are values allowed. Percent columns are 0–100.

## Fantasy (the user's Yahoo points league, 12 teams, 2026 season)

**`fantasy_batters`**: `Name, "Fantasy Team", "Is FA", "MLB Team", "Fantasy Pts", "Pts/PA", PA, AVG, OBP, SLG, OPS, H, "1B", "2B", "3B", HR, BB, SB, CS, SO, HBP, GIDP` — season-long points from Baseball Reference stats. **`AVG` is always 0 (known bug); compute H/(PA) or use `batting.BA` instead.**
**`fantasy_pitchers`**: `Name, "Fantasy Team", "Is FA", "MLB Team", "Fantasy Pts", "Pts/IP", IP, ERA, WHIP, "K%", SO, BB, HBP, WP, BLK, GIDP`
`"Fantasy Team"` is the owning team (free agents have `"Is FA"` = true).
**`fantasy_weekly`**: `team, week, player, position, lineup_slot, is_pitcher, is_active, fan_pts` — Yahoo's points per rostered player per week. `is_active` = false for bench/IL/NA slots; team weekly score = SUM(fan_pts) WHERE is_active.
Scoring — batters: 1B +1, 2B +2, 3B +3, HR +4, SB +1, CS −1, BB +1, IBB +1, HBP +1, SO −0.5, GIDP −1. Pitchers: out +1 (IP×3), BB −1, IBB −0.5, HBP −1, SO +0.5, WP −1, BK −1, induced GIDP +1, total bases allowed −1.
Fantasy files were last updated in July 2026 and may be stale.

## player_ids — Baseball Reference name → MLBAM ID

`season, Name, mlbam_id, role ('batter'/'pitcher')`. Built by matching `batting`/`pitching` names to Statcast/Savant IDs (accent-, case- and suffix-insensitive). Covers about 99% of players. Names shared by two players in one season (e.g. the two Max Muncys) are deliberately left out.

## Joining tables (important)

- **Use IDs, never names, whenever possible.** Statcast `batter`/`pitcher` = Savant `player_id` = `player_ids.mlbam_id`.
- Baseball Reference ↔ Statcast/Savant: go through `player_ids`:
  ```sql
  SELECT b.Name, b.HR, p.mlbam_id, s.xwoba AS xwoba_pctile
  FROM batting b
  JOIN player_ids p ON p.season = b.season AND p.Name = b.Name AND p.role = 'batter'
  JOIN savant_batter_pct s ON s.year = b.season AND s.player_id = p.mlbam_id
  ```
- To label Statcast batters by name, prefer `player_ids` (proper spelling) and fall back to `batter_names` (its names are oddly cased, e.g. 'Elly De la cruz', 'Tj Friedl', and lack Jr./II).
- Name formats: `batting`/`pitching`/`player_ids`.Name = "First Last"; Savant tables and `statcast.player_name` = "Last, First"; fantasy tables use Yahoo's spelling ("First Last").
- To find a player, search loosely first: `WHERE Name ILIKE '%acuna%' OR Name ILIKE '%acuña%'`.
