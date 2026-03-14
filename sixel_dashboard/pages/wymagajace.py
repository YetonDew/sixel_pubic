import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path
import sys
import shutil

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sixel_core.config_loader import CONFIG
from sixel_router.path_router import PathRouter
from utils.open_path import open_path


# ✅ DB correcta
DB_PATH = "sixel_db/database.sqlite3"

st.title("⚠️ Dokumenty wymagające uwagi")

TIPOS_UWAGA = ("OTRO", "UNKNOWN", "INNE", "PRZYPOMNIENIE")


# -----------------------
# Data loading (FAST)
# -----------------------
@st.cache_data(ttl=10)
def load_clients(db_path: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            """
            SELECT DISTINCT client_code
            FROM documents
            WHERE client_code IS NOT NULL
              AND client_code <> ''
              AND client_code <> 'DESCONOCIDO'
            ORDER BY client_code
            """,
            conn,
        )
        return df["client_code"].tolist()
    finally:
        conn.close()


@st.cache_data(ttl=10)
def load_attention_docs(db_path: str, limit: int, order: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        order = "ASC" if order == "ASC" else "DESC"  # only allow two values
        # ✅ Filtra en SQL + trae solo columnas necesarias
        q = f"""
        SELECT id, filename, tipo, client_code, target_path, received_at, periodo
        FROM documents
        WHERE solved = 0
          AND (
                tipo IN ({",".join(["?"] * len(TIPOS_UWAGA))})
                OR client_code = 'DESCONOCIDO'
              )
        ORDER BY received_at {order}
        LIMIT ?
        """
        params = list(TIPOS_UWAGA) + [limit]
        return pd.read_sql_query(q, conn, params=params)
    finally:
        conn.close()


def move_and_fix_document(db_path: str, row, new_client: str, new_tipo: str, new_periodo: str):
    """
    Mover archivo + actualizar DB (misma DB del dashboard).
    """
    conn = sqlite3.connect(db_path)
    try:
        old_path = Path(row["target_path"]).expanduser()

        storage_root = Path(CONFIG.get("paths.storage_root")).resolve()
        client_base_path = str(storage_root / new_client)

        router = PathRouter()
        target_dir = router.build(
            client_base_path=client_base_path,
            periodo=new_periodo,
            tipo=new_tipo,
        )
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        new_path = target_dir / old_path.name

        # Evitar colisión
        if new_path.exists():
            stem = new_path.stem
            suf = new_path.suffix
            i = 2
            while (target_dir / f"{stem}__{i}{suf}").exists():
                i += 1
            new_path = target_dir / f"{stem}__{i}{suf}"

        # 1) mover archivo
        shutil.move(str(old_path), str(new_path))

        # 2) actualizar DB
        cur = conn.execute(
            """
            UPDATE documents
            SET client_code = ?, tipo = ?, periodo = ?, target_path = ?, solved = 1
            WHERE id = ?
            """,
            (new_client, new_tipo, new_periodo, str(new_path), int(row["id"])),
        )
        conn.commit()

        if cur.rowcount != 1:
            raise RuntimeError(f"DB update rowcount={cur.rowcount} (expected 1).")

    finally:
        conn.close()


# -----------------------
# UI controls
# -----------------------
limit = st.slider("Ilość dokumentów do pokazania", 20, 500, 100, 20)
sort_choice = st.radio(
    "Kolejność sortowania",
    ("Najnowsze (DESC)", "Najstarsze (ASC)"),
    horizontal=True,
)
order = "ASC" if "ASC" in sort_choice else "DESC"

all_clients = load_clients(DB_PATH)
attention_df = load_attention_docs(DB_PATH, limit, order)

if attention_df.empty:
    st.success("Brak dokumentów wymagających uwagi 👍")
    st.stop()


# -----------------------
# Render docs
# -----------------------
for _, row in attention_df.iterrows():
    with st.expander(f"{row['filename']} – {row['tipo']}"):

        st.write(f"**📄 Plik:** {row['filename']}")
        st.write(f"**👤 Klient:** {row['client_code']}")
        st.write(f"**📂 Ścieżka:** {row['target_path']}")
        st.write(f"**📅 Otrzymano:** {row['received_at']}")
        st.write("---")

        file_path = Path(row["target_path"]).expanduser()
        folder_path = file_path.parent

        col_file, col_folder = st.columns([1, 1])

        if col_file.button("📄 Otwórz plik", key=f"open-file-{row['id']}"):
            open_path(file_path)

        if col_folder.button("📁 Otwórz folder", key=f"open-folder-{row['id']}"):
            open_path(folder_path)

        with st.form(key=f"form_{row['id']}"):
            st.write("### ✏️ Korekta ręczna")

            c1, c2, c3 = st.columns(3)

            with c1:
                idx_client = all_clients.index(row["client_code"]) if row["client_code"] in all_clients else 0
                new_client = st.selectbox(
                    "Klient",
                    options=all_clients,
                    index=idx_client,
                )

            with c2:
                tipos = [
                    "FVZ", "FVS", "BANK", "PARAGON",
                    "ZUS", "PIT", "CIT", "JPK",
                    "PAYROLL", "URLOP", "UMOWA",
                    "PRZYPOMNIENIE", "OTRO",
                ]
                idx_tipo = tipos.index(row["tipo"]) if row["tipo"] in tipos else tipos.index("OTRO")
                new_tipo = st.selectbox(
                    "Typ dokumentu",
                    options=tipos,
                    index=idx_tipo,
                )

            with c3:
                new_periodo = st.text_input(
                    "Okres (YYYY-MM)",
                    value=(row["periodo"] or ""),
                )

            submitted = st.form_submit_button("💾 Zapisz i przenieś")

            if submitted:
                try:
                    move_and_fix_document(
                        DB_PATH,
                        row,
                        new_client=new_client,
                        new_tipo=new_tipo,
                        new_periodo=new_periodo,
                    )
                    # ✅ limpiar caches para que desaparezca sin "pantalla eterna"
                    load_attention_docs.clear()
                    load_clients.clear()
                    st.success("✅ Dokument poprawiony i przeniesiony.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Błąd podczas przenoszenia: {e}")
