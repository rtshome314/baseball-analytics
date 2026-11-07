"""
sql_assistant.py
Plain-language questions -> Claude writes DuckDB SQL -> run read-only over data/*.parquet.

Safety: the DuckDB connection can read ONLY the parquet files registered as views below.
File access is locked (allowed_paths + enable_external_access=false + lock_configuration),
so generated SQL cannot read data/user_settings.json, .yahoo_token.json, or write anything.
"""
import os
import re
import glob
import threading
import unicodedata

import duckdb
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
GUIDE_PATH = os.path.join(ROOT, "utils", "schema_guide.md")

MODEL = "claude-opus-5-5"
EFFORT = "medium"          # low | medium | high | xhigh | max — raise if answers are wrong
MAX_TOOL_ROUNDS = 10       # max query rounds per question
ROWS_TO_CLAUDE = 60        # rows of each result shown to Claude
MAX_RESULT_ROWS = 10_000   # rows kept for display
QUERY_TIMEOUT_S = 60

# view name -> (filename regex, add season column from filename)
VIEWS = {
    "batting":           (r"batting_stats_(\d{4})\.parquet", True),
    "pitching":          (r"pitching_stats_(\d{4})\.parquet", True),
    "batting_post":      (r"batting_stats_post_(\d{4})\.parquet", True),
    "pitching_post":     (r"pitching_stats_post_(\d{4})\.parquet", True),
    "statcast":          (r"statcast_(\d{4})\.parquet", False),  # has game_year
    "batter_names":      (r"batter_lookup_(\d{4})\.parquet", True),
    "splits":            (r"split_summary_(\d{4})\.parquet", True),
    "savant_batter_pct": (r"statcast_batter_pcts_(\d{4})\.parquet", False),  # has year
    "savant_pitcher_pct": (r"statcast_pitcher_pcts_(\d{4})\.parquet", False),
    "savant_batting":    (r"statcast_batting_agg_(\d{4})\.parquet", True),
    "savant_pitching":   (r"statcast_pitching_agg_(\d{4})\.parquet", True),
    "fantasy_batters":   (r"fantasy_batters\.parquet", False),
    "fantasy_pitchers":  (r"fantasy_pitchers\.parquet", False),
    "fantasy_weekly":    (r"yahoo_weekly_player_stats\.parquet", False),
}


# Baseball Reference tables are small: load them with pandas so names can be repaired.
BREF_VIEWS = {"batting", "pitching", "batting_post", "pitching_post"}


def _fwd(path):
    return os.path.abspath(path).replace(os.sep, "/")


def fix_mojibake(s):
    """Repair UTF-8 text that was decoded as Latin-1 (e.g. 'JosÃ© RamÃ\xadrez' -> 'José Ramírez')."""
    if not isinstance(s, str) or ("Ã" not in s and "Â" not in s):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv)\b\.?", re.IGNORECASE)


def name_key(name):
    """Loose join key: 'Elly De La Cruz' == 'Elly De la cruz', 'J.T. Realmuto' == 'J. t. Realmuto',
    'Ronald Acuña Jr.' == 'Ronald Acuna'. 'Last, First' is flipped to 'First Last'."""
    if not isinstance(name, str):
        return None
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first} {last}"
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = _SUFFIX_RE.sub(" ", name.lower())
    return re.sub(r"[^a-z]", "", name) or None


def _build_player_ids(con, bref):
    """season, Name (Baseball Reference spelling), mlbam_id, role — matched by loose name key per season.
    Names shared by two different IDs in the same season/role are left unmatched rather than guessed."""
    id_sources = {
        "batter": [
            "SELECT season, batter AS id, batter_name AS nm FROM batter_names",
            "SELECT year AS season, player_id AS id, player_name AS nm FROM savant_batter_pct",
        ],
        "pitcher": [
            "SELECT DISTINCT game_year AS season, pitcher AS id, player_name AS nm FROM statcast",
            "SELECT year AS season, player_id AS id, player_name AS nm FROM savant_pitcher_pct",
        ],
    }
    out = []
    for role, table in (("batter", "batting"), ("pitcher", "pitching")):
        if table not in bref:
            continue
        ids = []
        for q in id_sources[role]:
            try:
                ids.append(con.execute(q).df())
            except Exception:
                pass
        if not ids:
            continue
        ids = pd.concat(ids).dropna()
        ids["key"] = ids["nm"].map(name_key)
        ids = ids.drop_duplicates(["season", "key", "id"])
        unique = ids.groupby(["season", "key"]).filter(lambda g: g["id"].nunique() == 1)
        unique = unique.drop_duplicates(["season", "key"])[["season", "key", "id"]]
        names = bref[table][["season", "Name"]].dropna().drop_duplicates()
        names = names[~names["Name"].str.contains("Average", na=False)]
        names["key"] = names["Name"].map(name_key)
        m = names.merge(unique, on=["season", "key"], how="inner")
        m["role"] = role
        out.append(m[["season", "Name", "id", "role"]].rename(columns={"id": "mlbam_id"}))
    if out:
        df = pd.concat(out, ignore_index=True)
        df["mlbam_id"] = df["mlbam_id"].astype("int64")
        con.register("_player_ids_df", df)
        con.execute("CREATE TABLE player_ids AS SELECT * FROM _player_ids_df")
        con.unregister("_player_ids_df")


def _load_bref(files):
    frames = []
    for f in files:
        df = pd.read_parquet(f)
        df.insert(0, "season", int(re.search(r"(\d{4})\.parquet$", f).group(1)))
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["Name"] = df["Name"].map(fix_mojibake)
    return df


def build_connection():
    """Create an in-memory DuckDB connection with read-only views over the parquet files."""
    all_files = sorted(glob.glob(os.path.join(DATA_DIR, "*.parquet")))
    view_files = {}
    for view, (pattern, _) in VIEWS.items():
        matched = [_fwd(f) for f in all_files if re.fullmatch(pattern, os.path.basename(f))]
        if matched:
            view_files[view] = matched

    con = duckdb.connect(":memory:")
    bref = {}
    for view in BREF_VIEWS & view_files.keys():
        bref[view] = _load_bref(view_files[view])
        con.register(f"_{view}_df", bref[view])
        con.execute(f"CREATE TABLE {view} AS SELECT * FROM _{view}_df")
        con.unregister(f"_{view}_df")

    allowed = [f for v, files in view_files.items() if v not in BREF_VIEWS for f in files]
    con.execute("SET allowed_paths = ?", [allowed])
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")

    for view, files in view_files.items():
        if view in BREF_VIEWS:
            continue
        pattern, add_season = VIEWS[view]
        file_list = ", ".join("'" + f.replace("'", "''") + "'" for f in files)
        src = f"read_parquet([{file_list}], union_by_name = true, filename = true)"
        season_expr = (
            f"CAST(regexp_extract(filename, '(\\d{{4}})\\.parquet$', 1) AS INTEGER) AS season, "
            if add_season else ""
        )
        con.execute(f"CREATE VIEW {view} AS SELECT {season_expr}* EXCLUDE (filename) FROM {src}")

    _build_player_ids(con, bref)
    tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables ORDER BY 1").fetchall()]
    return con, tables


def load_schema_guide():
    with open(GUIDE_PATH, "r", encoding="utf-8") as f:
        return f.read()


class QueryError(Exception):
    pass


def run_sql(con, sql):
    """Run one read-only SELECT. Returns (DataFrame, total_row_count). Raises QueryError."""
    sql = sql.strip().rstrip(";").strip()
    try:
        statements = duckdb.extract_statements(sql)
    except Exception as e:
        raise QueryError(f"Could not parse SQL: {e}")
    if len(statements) != 1:
        raise QueryError("Send exactly one SQL statement.")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise QueryError("Only SELECT queries (including WITH ... SELECT) are allowed.")

    cur = con.cursor()
    timer = threading.Timer(QUERY_TIMEOUT_S, cur.interrupt)
    timer.start()
    try:
        df = cur.execute(f"SELECT * FROM ({sql}) LIMIT {MAX_RESULT_ROWS + 1}").df()
    except Exception as e:
        msg = str(e)
        if "INTERRUPT" in msg.upper():
            msg = f"Query cancelled after {QUERY_TIMEOUT_S}s. Filter statcast by game_year and aggregate."
        raise QueryError(msg)
    finally:
        timer.cancel()
        cur.close()
    truncated = len(df) > MAX_RESULT_ROWS
    return df.head(MAX_RESULT_ROWS), truncated


def _result_for_claude(df, truncated):
    n = f"{MAX_RESULT_ROWS}+ (truncated)" if truncated else str(len(df))
    if df.empty:
        return "Query returned 0 rows."
    shown = df.head(ROWS_TO_CLAUDE)
    text = f"{n} rows. Columns: {', '.join(map(str, df.columns))}\n" + shown.to_csv(index=False, float_format="%.4g")
    if len(df) > ROWS_TO_CLAUDE:
        text += f"\n(Only the first {ROWS_TO_CLAUDE} rows are shown to you; the user sees all rows.)"
    return text


SYSTEM_INSTRUCTIONS = """You answer baseball questions for the owner of a personal analytics app by querying their local data with the run_sql tool.

How to work:
- Always get numbers from run_sql. Never answer from memory, and never invent stats. If the data can't answer the question, say what is missing.
- Check player name spelling with a quick ILIKE query when a name match returns nothing.
- Read the schema guide's rules (traded-player rows, league-average rows, BA vs AVG, pitcher name in statcast) before writing SQL.
- If a result looks wrong (zero rows, duplicates, implausible values), investigate with another query before answering.
- When the question is ambiguous (e.g. which season), use the most recent season (2026) and say so.
- The user sees the full result table of your LAST query under your answer, so make the last query the one that best answers the question (sorted, readable column names via AS, rounded rates).

Answer format: lead with the direct answer in 1-3 sentences, then any caveats (e.g. data source, qualification threshold, approximation). Use plain language. Do not paste the whole table into your answer; mention the key numbers.

# Schema guide

"""

RUN_SQL_TOOL = {
    "name": "run_sql",
    "description": (
        "Run one read-only DuckDB SELECT query against the baseball views described in the schema guide. "
        f"Returns up to {ROWS_TO_CLAUDE} rows as CSV, or an error message to fix and retry."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "A single DuckDB SELECT (or WITH ... SELECT) statement."},
            "purpose": {"type": "string", "description": "One short phrase saying what this query checks, shown to the user."},
        },
        "required": ["sql", "purpose"],
        "additionalProperties": False,
    },
    "strict": True,
}


def ask_claude(client, con, guide, messages, on_step=None):
    """
    Run the tool loop for the conversation in `messages` (last item is the new user question).
    Mutates `messages` (appends assistant turns and tool results) so follow-ups keep context.
    Returns dict: answer (str), queries (list of dicts: purpose, sql, df, truncated, error), usage (dict).
    """
    system = [{"type": "text", "text": SYSTEM_INSTRUCTIONS + guide, "cache_control": {"type": "ephemeral"}}]
    queries = []
    usage = {"input": 0, "output": 0, "cache_read": 0}
    answer = ""

    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=system,
            tools=[RUN_SQL_TOOL],
            output_config={"effort": EFFORT},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=messages,
        )
        u = response.usage
        usage["input"] += u.input_tokens or 0
        usage["output"] += u.output_tokens or 0
        usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            answer = "Claude declined to answer this question."
            break

        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if text:
            answer = text
        if response.stop_reason != "tool_use":
            if response.stop_reason == "max_tokens":
                answer += "\n\n_(Answer was cut off: hit the token limit.)_"
            break

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            sql = block.input.get("sql", "") if isinstance(block.input, dict) else ""
            purpose = block.input.get("purpose", "") if isinstance(block.input, dict) else ""
            if on_step:
                on_step(purpose or "Running query", sql)
            entry = {"purpose": purpose, "sql": sql, "df": None, "truncated": False, "error": None}
            try:
                df, truncated = run_sql(con, sql)
                entry.update(df=df, truncated=truncated)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": _result_for_claude(df, truncated)})
            except QueryError as e:
                entry["error"] = str(e)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": f"Error: {e}", "is_error": True})
            queries.append(entry)
        messages.append({"role": "user", "content": results})
    else:
        answer = answer or "Stopped: too many query rounds without a final answer."

    return {"answer": answer, "queries": queries, "usage": usage}
