# Baseball Query Guide

Ready-to-run SQL for your baseball data. You don't need to know SQL: copy a query, change the parts marked in the notes (a year, a player name, a minimum), and run it.

Three ways to get answers:

1. **Copy a query from this guide** and run it (free).
2. **Ask Claude in a Claude Code session** ("write me a query for…"). Claude writes and runs the SQL for you at no extra cost.
3. **Ask a plain-language question** in `scripts/ask.py` or on the app's Ask page. This needs an Anthropic API key and costs a few cents per question.

For the full list of tables and columns, see [utils/schema_guide.md](utils/schema_guide.md). That file is written for Claude, but you can read it too.

---

## How to run a query

Open a terminal in the project folder and start the query tool:

```bash
python scripts/ask.py
```

At the `>` prompt, type `sql:` and paste the query **as one line** (the tool reads one line at a time, so join a multi-line query with spaces first):

```
> sql: SELECT Name, HR FROM batting WHERE season = 2025 AND Tm IS NOT NULL ORDER BY HR DESC LIMIT 10
```

To run a multi-line query in one go without the prompt, wrap it in quotes:

```bash
python scripts/ask.py --sql "SELECT Name, HR FROM batting WHERE season = 2025 AND Tm IS NOT NULL ORDER BY HR DESC LIMIT 10"
```

The app's **Ask** page also has a **Run your own SQL** box in the sidebar, which accepts multi-line queries as written.

Results show the first 30 rows in the terminal. Add `LIMIT 30` (or fewer) to keep output readable.

---

## SQL in 60 seconds

```sql
SELECT Name, HR, BB          -- which columns to show
FROM batting                 -- which table
WHERE season = 2025          -- which rows to keep
  AND PA >= 300
ORDER BY HR DESC             -- sort (DESC = biggest first)
LIMIT 10                     -- how many rows
```

- Text goes in single quotes: `Name = 'Cal Raleigh'`. For a partial or unsure match use `ILIKE` with `%`: `Name ILIKE '%raleigh%'`.
- Column names with symbols or starting with a number need double quotes: `"2B"`, `"OPS+"`, `"ERA+"`, `"Fantasy Pts"`. Watch out for `2B`: without quotes there's no error, you just get a column of 2s.
- `--` starts a comment; anything after it on that line is ignored.
- Rename a column in the output with `AS`: `ROUND(BA, 3) AS avg`.

---

## Which table to use

| You want… | Table |
|---|---|
| Season totals (HR, RBI, AVG, OPS, WAR, ERA, wins, saves) | `batting`, `pitching` |
| Team totals, records and standings | `team_batting`, `team_pitching` |
| Postseason totals | `batting_post`, `pitching_post` |
| Anything about individual pitches or batted balls: velocity, exit velocity, pitch type, dates, counts, innings, matchups | `statcast` |
| Batter splits by pitcher hand, home/away, month | `splits` |
| Baseball Savant percentile rankings (0–100) | `savant_batter_pct`, `savant_pitcher_pct` |
| Savant exit-velocity/barrel leaderboards | `savant_batting`, `savant_pitching` |
| Your Yahoo fantasy league | `fantasy_batters`, `fantasy_pitchers`, `fantasy_weekly` |

Seasons available: 2023–2026.

## Five rules that prevent wrong answers

1. **Traded players appear more than once** in `batting`/`pitching`: once per team plus a combined row with `Tm` = `'2TM'`, `'3TM'`… For leaderboards, keep `Tm IS NOT NULL` and don't add up a player's rows. The combined row already has his season total.
2. **Each table has a league-average row** (`MLB Average` / `League Average`) with no team. `Tm IS NOT NULL` removes it.
3. **Batting average is `BA`**, not AVG. Strikeouts are `SO`. Strikeouts per 9 is `SO9`.
4. **In `statcast`, `player_name` is the pitcher.** Batter names come from joining `player_ids` (see the Statcast examples).
5. **`statcast` is huge** (about 700,000 pitches per season). Always filter by `game_year` and keep a `LIMIT`.

---

## Season leaderboards

### Home run leaders
Change the year, the stat (`HR` → `RBI`, `SB`, `BB`, `WAR`, `OPS`…) and the row count.

```sql
SELECT Name, Tm, PA, HR, RBI, ROUND(BA, 3) AS BA, ROUND(OPS, 3) AS OPS
FROM batting
WHERE season = 2026 AND Tm IS NOT NULL
ORDER BY HR DESC
LIMIT 15
```

### Batting average leaders, qualified hitters only
Qualified = 502+ plate appearances. Swap `BA` for `OBP`, `SLG` or `OPS`.

```sql
SELECT Name, Tm, PA, ROUND(BA, 3) AS BA, ROUND(OBP, 3) AS OBP, ROUND(SLG, 3) AS SLG
FROM batting
WHERE season = 2026 AND Tm IS NOT NULL AND PA >= 502
ORDER BY BA DESC
LIMIT 15
```

### ERA leaders, qualified pitchers only
Qualified = 162+ innings. For FIP or WHIP, change both `ERA` spots. For strikeout leaders use `ORDER BY SO DESC` and drop the innings minimum.

```sql
SELECT Name, Tm, IP, ERA, FIP, WHIP, SO, SO9
FROM pitching
WHERE season = 2026 AND Tm IS NOT NULL AND IP >= 162
ORDER BY ERA
LIMIT 15
```

### Saves leaders

```sql
SELECT Name, Tm, G, SV, IP, ERA, SO
FROM pitching
WHERE season = 2026 AND Tm IS NOT NULL
ORDER BY SV DESC
LIMIT 15
```

### Standings
Wins and losses are in `team_pitching`; runs scored are in `team_batting`. Change the year, or remove the `Div` line to see all 30 teams.

```sql
SELECT p.Div, p.Team, p.W, p.L, ROUND(p."W-L%", 3) AS pct,
       b.R AS runs_scored, p.R AS runs_allowed, b.R - p.R AS run_diff
FROM team_pitching p
JOIN team_batting b ON b.season = p.season AND b.Team = p.Team
WHERE p.season = 2026
  AND p.Div = 'AL West'
ORDER BY p.Div, p.W DESC
```

### Team batting and pitching leaders
Change the stat to sort by (`HR`, `OPS`, `SB`, `"R/G"`; for pitching `ERA`, `FIP`, `SO9`, `WHIP`).

```sql
SELECT Team, "R/G", HR, SB, ROUND(BA, 3) AS BA, ROUND(OBP, 3) AS OBP, ROUND(OPS, 3) AS OPS, "OPS+"
FROM team_batting
WHERE season = 2026
ORDER BY OPS DESC
LIMIT 10
```

```sql
SELECT Team, W, L, ERA, FIP, WHIP, SO9, BB9, SV
FROM team_pitching
WHERE season = 2026
ORDER BY ERA
LIMIT 10
```

### A team across seasons

```sql
SELECT p.season, p.W, p.L, b.R AS runs_scored, p.R AS runs_allowed, b.HR, ROUND(b.OPS, 3) AS OPS, p.ERA
FROM team_pitching p
JOIN team_batting b ON b.season = p.season AND b.Team = p.Team
WHERE p.Team = 'Seattle Mariners'
ORDER BY p.season
```

### Leaders at a position
`Pos LIKE '*2%'` = primary catcher. Numbers: 2 C, 3 1B, 4 2B, 5 3B, 6 SS, 7 LF, 8 CF, 9 RF; `D` = DH.

```sql
SELECT Name, Tm, Pos, PA, HR, ROUND(OPS, 3) AS OPS, WAR
FROM batting
WHERE season = 2026 AND Tm IS NOT NULL AND Pos LIKE '*6%' AND PA >= 300
ORDER BY WAR DESC
LIMIT 15
```

---

## One player

### Season-by-season stats
Change the name. If nothing comes back, try `Name ILIKE '%raleigh%'` to check the spelling.

```sql
SELECT season, Tm, G, PA, HR, RBI, BB, SO, ROUND(BA, 3) AS BA, ROUND(OPS, 3) AS OPS, "OPS+", WAR
FROM batting
WHERE Name = 'Cal Raleigh'
ORDER BY season, Tm
```

Pitcher version:

```sql
SELECT season, Tm, G, GS, W, L, SV, IP, ERA, FIP, WHIP, SO, BB
FROM pitching
WHERE Name = 'Tarik Skubal'
ORDER BY season, Tm
```

### Compare players side by side

```sql
SELECT Name, Tm, PA, HR, RBI, SB, ROUND(BA, 3) AS BA, ROUND(OPS, 3) AS OPS, WAR
FROM batting
WHERE season = 2025 AND Name IN ('Cal Raleigh', 'Aaron Judge', 'Shohei Ohtani')
ORDER BY WAR DESC
```

### Splits vs left- and right-handed pitchers
`splits` holds counts; the rates are computed from them. Change the name and year. For home/away use `venue` instead of `p_throws`; by month use `month_label`.

```sql
SELECT p_throws AS vs_pitcher_hand,
       SUM(PA) AS PA, SUM(HR) AS HR, SUM(BB) AS BB, SUM(SO) AS SO,
       ROUND(SUM(H) / SUM(AB), 3) AS BA,
       ROUND((SUM(H) + SUM(BB) + SUM(HBP)) / (SUM(AB) + SUM(BB) + SUM(HBP) + SUM(SF)), 3) AS OBP,
       ROUND((SUM("1B") + 2*SUM("2B") + 3*SUM("3B") + 4*SUM(HR)) / SUM(AB), 3) AS SLG
FROM splits
WHERE season = 2025 AND batter_name ILIKE '%raleigh%'
GROUP BY p_throws
```

### Month-by-month

```sql
SELECT month_label AS month, SUM(PA) AS PA, SUM(HR) AS HR,
       ROUND(SUM(H) / SUM(AB), 3) AS BA,
       ROUND(SUM(ev_sum) / SUM(batted_ball_count), 1) AS avg_exit_velo
FROM splits
WHERE season = 2025 AND batter_name ILIKE '%raleigh%'
GROUP BY month_label
ORDER BY MIN(CASE month_label WHEN 'March/April' THEN 1 WHEN 'May' THEN 2 WHEN 'June' THEN 3
                              WHEN 'July' THEN 4 WHEN 'August' THEN 5 ELSE 6 END)
```

### Savant percentile rankings
Values are percentiles (0–100, higher is better), not raw stats. Names are "Last, First". Use `savant_pitcher_pct` for pitchers.

```sql
SELECT year, xwoba, xba, xslg, exit_velocity, brl_percent, hard_hit_percent,
       k_percent, bb_percent, whiff_percent, chase_percent, sprint_speed
FROM savant_batter_pct
WHERE player_name ILIKE '%raleigh%'
ORDER BY year
```

---

## Statcast: pitches and batted balls

### Hardest-hit balls
Change the year and the count. Remove the `AND s.events = 'home_run'` line to include every batted ball.

```sql
SELECT p.Name AS batter, s.game_date::DATE AS date, s.launch_speed AS exit_velo,
       s.launch_angle, s.hit_distance_sc AS distance, s.events, s.player_name AS pitcher
FROM statcast s
LEFT JOIN player_ids p ON p.season = s.game_year AND p.mlbam_id = s.batter AND p.role = 'batter'
WHERE s.game_year = 2026 AND s.launch_speed IS NOT NULL
  AND s.events = 'home_run'
ORDER BY s.launch_speed DESC
LIMIT 15
```

### Barrel and hard-hit leaders
Minimum 200 batted balls; change it in the `HAVING` line.

```sql
SELECT p.Name AS batter,
       COUNT(*) AS batted_balls,
       COUNT(*) FILTER (WHERE s.launch_speed_angle = 6) AS barrels,
       ROUND(100.0 * COUNT(*) FILTER (WHERE s.launch_speed_angle = 6) / COUNT(*), 1) AS barrel_pct,
       ROUND(100.0 * COUNT(*) FILTER (WHERE s.launch_speed >= 95) / COUNT(*), 1) AS hard_hit_pct,
       ROUND(AVG(s.launch_speed), 1) AS avg_exit_velo
FROM statcast s
LEFT JOIN player_ids p ON p.season = s.game_year AND p.mlbam_id = s.batter AND p.role = 'batter'
WHERE s.game_year = 2026 AND s.type = 'X' AND s.launch_speed IS NOT NULL
GROUP BY p.Name
HAVING COUNT(*) >= 200
ORDER BY barrel_pct DESC
LIMIT 20
```

### Hardest-throwing pitchers (average four-seam fastball)
`FF` = four-seam fastball. Try `SI` (sinker) or `FC` (cutter). Minimum 300 pitches.

```sql
SELECT player_name AS pitcher, COUNT(*) AS pitches,
       ROUND(AVG(release_speed), 1) AS avg_mph, MAX(release_speed) AS max_mph,
       ROUND(AVG(release_spin_rate)) AS avg_spin
FROM statcast
WHERE game_year = 2026 AND pitch_type = 'FF'
GROUP BY player_name
HAVING COUNT(*) >= 300
ORDER BY avg_mph DESC
LIMIT 15
```

### A pitcher's pitch mix
Names in `statcast` are "Last, First". Shows usage, velocity, movement in inches, and whiff rate per pitch.

```sql
SELECT pitch_name, COUNT(*) AS pitches,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS usage_pct,
       ROUND(AVG(release_speed), 1) AS mph,
       ROUND(AVG(release_spin_rate)) AS spin,
       ROUND(AVG(pfx_x) * 12, 1) AS horiz_break_in,
       ROUND(AVG(pfx_z) * 12, 1) AS vert_break_in,
       ROUND(100.0 * COUNT(*) FILTER (WHERE description IN ('swinging_strike','swinging_strike_blocked','missed_bunt'))
             / NULLIF(COUNT(*) FILTER (WHERE description IN ('swinging_strike','swinging_strike_blocked','foul','foul_tip','foul_bunt','hit_into_play','missed_bunt')), 0), 1) AS whiff_pct
FROM statcast
WHERE game_year = 2026 AND player_name = 'Skubal, Tarik'
GROUP BY pitch_name
ORDER BY pitches DESC
```

### How a batter does against each pitch type

```sql
SELECT s.pitch_name, COUNT(*) AS pitches_seen,
       COUNT(*) FILTER (WHERE s.events IN ('single','double','triple','home_run')) AS hits,
       COUNT(*) FILTER (WHERE s.events = 'home_run') AS HR,
       ROUND(100.0 * COUNT(*) FILTER (WHERE s.description IN ('swinging_strike','swinging_strike_blocked','missed_bunt'))
             / NULLIF(COUNT(*) FILTER (WHERE s.description IN ('swinging_strike','swinging_strike_blocked','foul','foul_tip','foul_bunt','hit_into_play','missed_bunt')), 0), 1) AS whiff_pct,
       ROUND(SUM(s.woba_value) / NULLIF(SUM(s.woba_denom), 0), 3) AS wOBA
FROM statcast s
JOIN player_ids p ON p.season = s.game_year AND p.mlbam_id = s.batter AND p.role = 'batter'
WHERE s.game_year = 2025 AND p.Name = 'Cal Raleigh'
GROUP BY s.pitch_name
ORDER BY pitches_seen DESC
```

### Batter vs pitcher matchup (all seasons)

```sql
SELECT s.game_year, s.game_date::DATE AS date, s.inning, s.events, s.pitch_name,
       s.launch_speed AS exit_velo
FROM statcast s
JOIN player_ids p ON p.season = s.game_year AND p.mlbam_id = s.batter AND p.role = 'batter'
WHERE p.Name = 'Aaron Judge' AND s.player_name = 'Skubal, Tarik' AND s.events IS NOT NULL
ORDER BY s.game_date, s.at_bat_number
```

### Stats over a date range
Season-total tables can't do dates; Statcast can. Change the dates and the minimum PA.

```sql
SELECT p.Name AS batter,
       COUNT(*) FILTER (WHERE s.events IS NOT NULL AND s.events <> 'truncated_pa') AS PA,
       COUNT(*) FILTER (WHERE s.events = 'home_run') AS HR,
       COUNT(*) FILTER (WHERE s.events IN ('single','double','triple','home_run')) AS H,
       COUNT(*) FILTER (WHERE s.events IN ('walk','intent_walk')) AS BB,
       COUNT(*) FILTER (WHERE s.events IN ('strikeout','strikeout_double_play')) AS SO
FROM statcast s
LEFT JOIN player_ids p ON p.season = s.game_year AND p.mlbam_id = s.batter AND p.role = 'batter'
WHERE s.game_date BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY p.Name
HAVING PA >= 60
ORDER BY HR DESC
LIMIT 15
```

---

## Your fantasy league

Fantasy files were last updated in July 2026, so they may be out of date.

### Top players by fantasy points
`"Is FA" = true` limits it to free agents; remove that line to see everyone. For pitchers use `fantasy_pitchers` and `"Pts/IP"`.

```sql
SELECT Name, "MLB Team", "Fantasy Team", "Fantasy Pts", ROUND("Pts/PA", 3) AS pts_per_pa, PA, HR, SB
FROM fantasy_batters
WHERE "Is FA" = true
ORDER BY "Fantasy Pts" DESC
LIMIT 15
```

### Weekly team scores
Counts only players in active lineup slots, which is how Yahoo scores the week.

```sql
SELECT week, team, ROUND(SUM(fan_pts), 1) AS points
FROM fantasy_weekly
WHERE is_active
GROUP BY week, team
ORDER BY week, points DESC
```

### Season points by team, hitters vs pitchers

```sql
SELECT team,
       ROUND(SUM(fan_pts) FILTER (WHERE NOT is_pitcher), 1) AS hitter_pts,
       ROUND(SUM(fan_pts) FILTER (WHERE is_pitcher), 1) AS pitcher_pts,
       ROUND(SUM(fan_pts), 1) AS total_pts
FROM fantasy_weekly
WHERE is_active
GROUP BY team
ORDER BY total_pts DESC
```

---

## When something goes wrong

| Message or result | What to do |
|---|---|
| 0 rows | Check the name spelling with `ILIKE '%part_of_name%'`, and check the year. |
| `Referenced column "AVG" not found` | Use `BA`. For other columns, run `DESCRIBE batting` (or another table) to list them. |
| `Binder Error ... must appear in the GROUP BY clause` | Every column in `SELECT` must either be in `GROUP BY` or wrapped in `SUM`, `AVG`, `COUNT`, etc. |
| A column named `B` full of 2s (or 3s) | You wrote `2B` without quotes; SQL read it as the number 2. Write `"2B"`. |
| `syntax error at or near "FROM"` after a column like `OPS+` | Put symbol column names in double quotes: `"OPS+"`, `"ERA+"`. |
| Query cancelled after 60s | Add `WHERE game_year = 2026` (or similar) to a `statcast` query. |
| A player shows up two or three times | He was traded; see rule 1 above. |
| `Only SELECT queries are allowed` | The tool is read-only by design. It can't change your data. |
