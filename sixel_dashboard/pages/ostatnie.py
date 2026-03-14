import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path

from utils.open_path import open_path

DB_PATH = "sixel_db/database.sqlite3"

st.title("📥 Ostatnie dokumenty")

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("""
    SELECT * FROM documents ORDER BY received_at DESC LIMIT 50
""", conn)

for idx, row in df.iterrows():
    with st.expander(f"{row['received_at']} — {row['filename']}"):
        st.write(f"📄 Typ: {row['tipo']}")
        st.write(f"👤 Klient: {row['client_code']}")
        st.write(f"📂 Ścieżka: {row['target_path']}")

        file_path = Path(row.get("full_path", row["target_path"])).expanduser()
        folder_path = file_path.parent

        col_file, col_folder = st.columns(2)
        if col_file.button("📄 Otwórz plik", key=f"open-file-{row['id']}"):
            open_path(file_path)
        if col_folder.button("📁 Otwórz folder", key=f"open-folder-{row['id']}"):
            open_path(folder_path)
