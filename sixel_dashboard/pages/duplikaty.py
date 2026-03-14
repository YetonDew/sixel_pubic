import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = "sixel_db/database.sqlite3"

st.title("♻️ Duplikaty")

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM documents", conn)

dups = df[df.duplicated("hash", keep=False)].sort_values("hash")

if dups.empty:
    st.success("Brak duplikatów! 👍")
else:
    st.dataframe(dups)
