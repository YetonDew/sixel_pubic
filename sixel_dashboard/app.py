import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = "sixel_db/database.sqlite3"

st.set_page_config(
    page_title="SIXEL Dashboard",
    layout="wide",
    page_icon="📊"
)

st.title("📊 Panel Główny – SIXEL")

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM documents", conn)

# Dokumenty wymagające uwagi
attention_count = df[
    ((df["tipo"].isin(["OTRO", "UNKNOWN", "INNE", "PRZYPOMNIENIE"])) |
    (df["client_code"] == "DESCONOCIDO")) &
    ((df["solved"] == 0))
].shape[0]

# Duplikaty
dups_count = df[df.duplicated("hash", keep=False)].shape[0]

# Ostatnie dokumenty (7 dni)
recent_count = df[
    df["received_at"] >= (pd.Timestamp.now() - pd.Timedelta(days=7)).isoformat()
].shape[0]

c1, c2, c3 = st.columns(3)
c1.metric("⚠️ Dokumenty wymagające uwagi", attention_count)
c2.metric("♻️ Duplikaty", dups_count)
c3.metric("📥 Ostatnie dokumenty (7 dni)", recent_count)

st.write("---")
 # =====================================================
# 📅 ACTIVITY TODAY
# =====================================================
st.subheader("📅 Aktywność dzisiaj")

today = pd.Timestamp.now().date()
df["received_at"] = pd.to_datetime(df["received_at"], errors="coerce")
today_df = df[df["received_at"].dt.date == today]

if today_df.empty:
    st.info("Dzisiaj nie otrzymano żadnych dokumentów.")
else:
    st.dataframe(
        today_df[["received_at", "filename", "client_code", "tipo"]],
        use_container_width=True
    )

st.write("---")
