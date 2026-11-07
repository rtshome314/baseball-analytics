import streamlit as st
import anthropic

from utils.style import inject_custom_css, render_nav_back
from utils.sql_assistant import build_connection, load_schema_guide, ask_claude, run_sql, QueryError, MODEL
from config import ANTHROPIC_API_KEY

st.set_page_config(page_title="Ask", page_icon="⚾", layout="wide")
inject_custom_css()
render_nav_back()

st.markdown("## 💬 Ask a Question")
st.markdown(
    "Ask about your data in plain language. Claude writes SQL, runs it on your local files, "
    "and explains the answer. Every query it ran is shown so you can check it."
)


@st.cache_resource(show_spinner="Opening data files…")
def get_connection():
    return build_connection()


@st.cache_resource
def get_client(api_key):
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


con, tables = get_connection()
guide = load_schema_guide()

if "ask_messages" not in st.session_state:
    st.session_state.ask_messages = []   # raw API conversation (for follow-ups)
    st.session_state.ask_turns = []      # what we display: question, answer, queries, usage

with st.sidebar:
    st.markdown("### 💬 Ask")
    if st.button("New conversation", use_container_width=True):
        st.session_state.ask_messages = []
        st.session_state.ask_turns = []
        st.rerun()
    with st.expander("Tables Claude can query"):
        st.caption(", ".join(tables))
    with st.expander("Run your own SQL"):
        manual_sql = st.text_area("DuckDB SELECT", "SELECT Name, HR FROM batting\nWHERE season = 2026 AND Tm IS NOT NULL\nORDER BY HR DESC LIMIT 10", height=140)
        run_manual = st.button("Run", use_container_width=True)


def render_queries(queries, key_prefix):
    if not queries:
        return
    last_ok = next((q for q in reversed(queries) if q["error"] is None), None)
    if last_ok is not None and not last_ok["df"].empty:
        st.dataframe(last_ok["df"], use_container_width=True, hide_index=True)
        if last_ok["truncated"]:
            st.caption("Showing the first 10,000 rows.")
        st.download_button(
            "Download CSV", last_ok["df"].to_csv(index=False).encode("utf-8"),
            file_name="answer.csv", mime="text/csv", key=f"{key_prefix}_dl",
        )
    with st.expander(f"🔎 Queries Claude ran ({len(queries)})"):
        for i, q in enumerate(queries, 1):
            st.markdown(f"**{i}. {q['purpose'] or 'Query'}**")
            st.code(q["sql"], language="sql")
            if q["error"]:
                st.error(q["error"])
            elif q is not last_ok:
                st.dataframe(q["df"].head(200), use_container_width=True, hide_index=True)


# --- Conversation so far ---
for i, turn in enumerate(st.session_state.ask_turns):
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        st.markdown(turn["answer"])
        render_queries(turn["queries"], f"turn{i}")
        u = turn["usage"]
        st.caption(f"{MODEL} · {u['input'] + u['cache_read']:,} input tokens ({u['cache_read']:,} cached) · {u['output']:,} output tokens")

if not st.session_state.ask_turns:
    st.markdown("**Try:** "
                "_Who led MLB in walks in 2025?_ · "
                "_Which pitchers threw the hardest average fastball in 2026 (min 300 fastballs)?_ · "
                "_Compare Cal Raleigh's OPS vs lefties and righties in 2025_ · "
                "_Which fantasy team scored the most points in week 10?_")

question = st.chat_input("Ask about players, teams, splits, Statcast, or your fantasy league…")

if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        status = st.status("Thinking…", expanded=False)

        def on_step(purpose, sql):
            status.update(label=f"Querying: {purpose}")
            status.code(sql, language="sql")

        messages = st.session_state.ask_messages
        n_before = len(messages)
        messages.append({"role": "user", "content": question})
        try:
            result = ask_claude(get_client(ANTHROPIC_API_KEY), con, guide, messages, on_step=on_step)
        except (anthropic.AuthenticationError, TypeError) as e:
            # No key at all raises TypeError("Could not resolve authentication method..."); a bad key raises AuthenticationError
            del messages[n_before:]
            if isinstance(e, TypeError) and "authentication" not in str(e).lower():
                status.update(label="Setup problem", state="error")
                st.error(f"{e}. Try `pip install -U anthropic`.")
                st.stop()
            status.update(label="No valid API key", state="error")
            st.error(
                "Claude needs an Anthropic API key (from console.anthropic.com, billed per use). "
                "Add `\"anthropic_api_key\": \"sk-ant-...\"` to `data/user_settings.json`, or set the "
                "`ANTHROPIC_API_KEY` environment variable, then restart the app. "
                "On Streamlit Cloud, add `ANTHROPIC_API_KEY` to the app's Secrets."
            )
            st.stop()
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError) as e:
            del messages[n_before:]
            status.update(label="Claude API error", state="error")
            st.error(f"Claude API error: {e}")
            st.stop()

        status.update(label=f"Done · {len(result['queries'])} quer{'y' if len(result['queries']) == 1 else 'ies'}", state="complete")
        st.session_state.ask_turns.append({"question": question, **result})
        st.rerun()

if run_manual:
    st.markdown("#### Your query")
    try:
        df, truncated = run_sql(con, manual_sql)
        st.dataframe(df, use_container_width=True, hide_index=True)
    except QueryError as e:
        st.error(str(e))
