"""
ask.py
Query the baseball data from the terminal, without starting the Streamlit app.
Uses the same tables and safety rules as the Ask page (utils/sql_assistant.py).

Usage (from the project folder):
    python scripts/ask.py                         # interactive: type questions or SQL
    python scripts/ask.py "Who led MLB in walks in 2025?"   # one question (needs an API key)
    python scripts/ask.py --sql "SELECT Name, HR FROM batting WHERE season = 2025 ORDER BY HR DESC LIMIT 5"
    python scripts/ask.py --tables                # list tables

Interactive commands:
    sql: SELECT ...   run your own SQL (free, no API key needed)
    new               start a new conversation (forget earlier questions)
    quit              exit
    anything else     a question for Claude (needs an Anthropic API key)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

from utils.sql_assistant import build_connection, load_schema_guide, ask_claude, run_sql, QueryError, MODEL

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 40)

MAX_PRINT_ROWS = 30


def print_df(df, truncated=False):
    if df.empty:
        print("(0 rows)")
        return
    print(df.head(MAX_PRINT_ROWS).to_string(index=False))
    if len(df) > MAX_PRINT_ROWS or truncated:
        print(f"... {len(df):,}{'+' if truncated else ''} rows total, showing {MAX_PRINT_ROWS}")


def do_sql(con, sql):
    try:
        df, truncated = run_sql(con, sql)
        print_df(df, truncated)
    except QueryError as e:
        print(f"SQL error: {e}")


_client = None


def get_client():
    global _client
    if _client is None:
        import anthropic
        from config import ANTHROPIC_API_KEY
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else anthropic.Anthropic()
    return _client


def do_question(con, guide, messages, question):
    import anthropic

    def on_step(purpose, sql):
        print(f"  … {purpose}")

    n_before = len(messages)
    messages.append({"role": "user", "content": question})
    try:
        result = ask_claude(get_client(), con, guide, messages, on_step=on_step)
    except (anthropic.AuthenticationError, TypeError) as e:
        del messages[n_before:]
        if isinstance(e, TypeError) and "authentication" not in str(e).lower():
            raise
        print("No valid Anthropic API key. Add \"anthropic_api_key\": \"sk-ant-...\" to data/user_settings.json "
              "or set the ANTHROPIC_API_KEY environment variable.\n"
              "You can still run your own SQL with  sql: SELECT ...")
        return
    except anthropic.APIError as e:
        del messages[n_before:]
        print(f"Claude API error: {e}")
        return

    print("\n" + result["answer"] + "\n")
    for i, q in enumerate(result["queries"], 1):
        print(f"--- Query {i}: {q['purpose']}")
        print(q["sql"])
        if q["error"]:
            print(f"  error: {q['error']}")
    last_ok = next((q for q in reversed(result["queries"]) if q["error"] is None), None)
    if last_ok is not None:
        print("\n--- Result of last query")
        print_df(last_ok["df"], last_ok["truncated"])
    u = result["usage"]
    print(f"\n[{MODEL}: {u['input'] + u['cache_read']:,} input tokens ({u['cache_read']:,} cached), {u['output']:,} output tokens]")


def main():
    args = sys.argv[1:]
    print("Opening data files…", end=" ", flush=True)
    con, tables = build_connection()
    print("ready.")

    if args[:1] == ["--tables"]:
        print(", ".join(tables))
        return
    if args[:1] == ["--sql"]:
        do_sql(con, " ".join(args[1:]))
        return

    guide = load_schema_guide()
    messages = []
    if args:
        do_question(con, guide, messages, " ".join(args))
        return

    print("Type a question, or  sql: SELECT ...  to run SQL yourself.  'new' = new conversation, 'quit' = exit.")
    print("Tables:", ", ".join(tables))
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ("quit", "exit", "q"):
            break
        if line.lower() == "new":
            messages = []
            print("Started a new conversation.")
        elif line.lower().startswith("sql:"):
            do_sql(con, line[4:])
        else:
            do_question(con, guide, messages, line)


if __name__ == "__main__":
    main()
