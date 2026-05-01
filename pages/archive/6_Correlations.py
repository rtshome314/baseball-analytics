import streamlit as st
import pandas as pd
import numpy as np
from utils.style import inject_custom_css
from utils.data_loader import load_batting_stats, load_pitching_stats
from utils.charts import create_scatter, create_distribution

st.set_page_config(page_title="Correlations", page_icon="⚾", layout="wide")
inject_custom_css()

st.markdown("## 🔗 Stat Correlations & Predictions")

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    season = st.selectbox("Season", [2026, 2025, 2024, 2023], index=1, key="corr_season")
    stat_type = st.radio("Stat Type", ["Batting", "Pitching"], key="corr_type")

if stat_type == "Batting":
    df = load_batting_stats(season)
    df = df[df["PA"] >= 100] if "PA" in df.columns else df
else:
    df = load_pitching_stats(season)
    df = df[df["IP"] >= 30] if "IP" in df.columns else df

if not df.empty:
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    # --- Custom Calculated Columns ---
    with st.expander("➕ Custom Calculated Columns"):
        st.markdown("Create new columns using formulas. Use column names from the data.")
        st.caption(f"Available columns: {', '.join(numeric_cols)}")
        
        if "custom_cols" not in st.session_state:
            st.session_state["custom_cols"] = []
        
        col_name = st.text_input("Column name", placeholder="e.g. HH_minus_Barrel", key="cc_name")
        col_formula = st.text_input("Formula", placeholder="e.g. hard_hit_pct - barrel_pct", key="cc_formula")
        
        if col_name and col_formula and st.button("Add Column", key="cc_add"):
            try:
                # Safely evaluate the formula using only DataFrame columns
                result = df.eval(col_formula)
                df[col_name] = result
                st.session_state["custom_cols"].append({"name": col_name, "formula": col_formula})
                st.success(f"Added '{col_name}' = {col_formula}")
            except Exception as e:
                st.error(f"Formula error: {e}")
        
        # Apply previously created custom columns
        for cc in st.session_state.get("custom_cols", []):
            try:
                df[cc["name"]] = df.eval(cc["formula"])
            except Exception:
                pass
        
        # Show and allow deletion of custom columns
        if st.session_state.get("custom_cols"):
            st.markdown("**Active custom columns:**")
            for i, cc in enumerate(st.session_state["custom_cols"]):
                col_a, col_b = st.columns([3, 1])
                col_a.write(f"`{cc['name']}` = {cc['formula']}")
                if col_b.button("❌", key=f"cc_del_{i}"):
                    st.session_state["custom_cols"].pop(i)
                    st.rerun()
    
    # Refresh numeric cols to include custom columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    tab1, tab2, tab3 = st.tabs(["📈 Scatter Plot", "📊 Distribution", "🤖 Prediction"])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            x_col = st.selectbox("X-Axis", numeric_cols, index=0)
        with col2:
            default_y = min(1, len(numeric_cols) - 1)
            y_col = st.selectbox("Y-Axis", numeric_cols, index=default_y)

        if x_col and y_col:
            valid = df[[x_col, y_col]].dropna()
            corr = valid[x_col].corr(valid[y_col])

            c1, c2, c3 = st.columns(3)
            c1.metric("Correlation (r)", f"{corr:.3f}")
            c2.metric("R²", f"{corr**2:.3f}")
            c3.metric("Sample Size", f"{len(valid)}")

            fig = create_scatter(df, x_col, y_col,
                                 hover_name="Name" if "Name" in df.columns else None,
                                 title=f"{y_col} vs {x_col} (r = {corr:.3f})")
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        dist_col = st.selectbox("Select stat", numeric_cols, key="dist_col")
        if dist_col:
            col_data = df[dist_col].dropna()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Mean", f"{col_data.mean():.3f}")
            c2.metric("Median", f"{col_data.median():.3f}")
            c3.metric("Std Dev", f"{col_data.std():.3f}")
            c4.metric("Count", f"{len(col_data)}")
            fig = create_distribution(df, dist_col, title=f"Distribution of {dist_col}")
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.markdown("#### Quick Linear Prediction")
        st.markdown("Select input metrics to predict an output metric.")

        target = st.selectbox("Predict (target)", numeric_cols, key="pred_target")
        available_features = [c for c in numeric_cols if c != target]
        features = st.multiselect("Using these inputs", available_features,
                                   default=available_features[:3] if len(available_features) >= 3 else available_features)

        if features and target:
            from sklearn.linear_model import LinearRegression
            from sklearn.model_selection import cross_val_score

            model_df = df[[target] + features].dropna()

            if len(model_df) >= 20:
                X = model_df[features]
                y = model_df[target]

                model = LinearRegression()
                model.fit(X, y)
                scores = cross_val_score(model, X, y, cv=5, scoring="r2")

                st.markdown(f"**Model R² (5-fold CV): {scores.mean():.3f}** ± {scores.std():.3f}")

                importance = pd.DataFrame({
                    "Feature": features,
                    "Coefficient": model.coef_,
                    "Abs Importance": np.abs(model.coef_),
                }).sort_values("Abs Importance", ascending=False)
                st.dataframe(importance, use_container_width=True)

                st.markdown("---")
                st.markdown("#### Try a Prediction")
                input_vals = {}
                pred_cols = st.columns(min(4, len(features)))
                for i, feat in enumerate(features):
                    with pred_cols[i % len(pred_cols)]:
                        median_val = float(model_df[feat].median())
                        input_vals[feat] = st.number_input(feat, value=median_val, key=f"pred_{feat}")

                if st.button("🔮 Predict", type="primary"):
                    input_array = pd.DataFrame([input_vals])
                    prediction = model.predict(input_array)[0]
                    st.success(f"**Predicted {target}: {prediction:.3f}**")
            else:
                st.warning("Not enough data points (need at least 20) for modeling.")
else:
    st.warning("No stats loaded. Head to **Data Manager** to download data first.")