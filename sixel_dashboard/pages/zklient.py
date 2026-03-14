import streamlit as st
import sqlite3
from pathlib import Path
import pandas as pd

from utils.open_path import open_path

DB_PATH = "sixel_db/database.sqlite3"

st.title("👤 Klient – szczegóły")

# --- Połączenie z DB ---
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM documents", conn)

if df.empty:
    st.warning("Brak dokumentów w bazie.")
    st.stop()

# --- Lista klientów ---
clients = sorted(c for c in df["client_code"].dropna().unique() if c != "DESCONOCIDO")

selected_client = st.selectbox("Wybierz klienta:", clients, index=0)

# --- Dane tego klienta ---
client_df = df[df["client_code"] == selected_client].copy()

st.subheader(f"📌 Klient: {selected_client}")

# --- LISTA PERIODO ---
all_periods = sorted(client_df["periodo"].dropna().unique())

selected_period = st.selectbox("Wybierz okres (YYYY-MM):", all_periods, index=len(all_periods)-1)

# --- FILTR okresu ---
period_df = client_df[client_df["periodo"] == selected_period]

st.write(f"### 📅 Dokumenty za okres **{selected_period}**")

# --- STATYSTYKI ---
fvz = (period_df["tipo"] == "FVZ").sum()
fvs = (period_df["tipo"] == "FVS").sum()

zus = (period_df["tipo"] == "ZUS").sum()
pit = (period_df["tipo"] == "PIT").sum()
pit4 = (period_df["tipo"] == "PIT4").sum()
cit = (period_df["tipo"] == "CIT").sum()
jpk = (period_df["tipo"] == "JPK").sum()
vat = (period_df["tipo"] == "VAT").sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("FVZ (zakupowe)", fvz)
c2.metric("FVS (sprzedażowe)", fvs)
c3.metric("ZUS", zus)
c4.metric("PIT / PIT4", pit + pit4)
c5.metric("JPK / VAT", jpk + vat)

st.write("---")

# --- OBOWIĄZKI MIESIĘCZNE (tabela najważniejsza dla księgowej) ---

st.subheader("🧾 Obowiązki miesięczne")

OBOWIAZKI = {
    "ZUS": zus > 0,
    "PIT-4": pit4 > 0,
    "PIT": pit > 0,
    "JPK_VAT": jpk > 0,
    "VAT7": vat > 0,
}

ob_df = pd.DataFrame({
    "Dokument": OBOWIAZKI.keys(),
    "Status": ["✔ Otrzymano" if val else "❌ Brak" for val in OBOWIAZKI.values()]
})

st.table(ob_df)

# --- OSTATNIE DOKUMENTY W OKRESIE ---
st.subheader(f"📥 Dokumenty za {selected_period}")

view_df = period_df.copy()

st.dataframe(
    view_df[["received_at", "filename", "tipo", "target_path"]],
    use_container_width=True,
)

st.caption("Przyciski poniżej wywołują otwarcie lokalne tak jak w 'ostatnie'.")

for _, row in view_df.iterrows():
    with st.expander(f"{row['received_at']} — {row['filename']}"):
        st.write(f"📄 Typ: {row['tipo']}")
        st.write(f"📂 Ścieżka: {row['target_path']}")

        file_path = Path(row.get("full_path", row["target_path"])).expanduser()
        folder_path = file_path.parent

        col_file, col_folder = st.columns(2)
        if col_file.button("📄 Otwórz plik", key=f"open-file-{row['id']}"):
            open_path(file_path)
        if col_folder.button("📁 Otwórz folder", key=f"open-folder-{row['id']}"):
            open_path(folder_path)

# --- Kiedy klient zwykle wysyła dokumenty ---
st.subheader("📊 Kiedy klient zwykle wysyła dokumenty?")

client_df["received_at_dt"] = pd.to_datetime(client_df["received_at"], errors="ignore")
valid = client_df["received_at_dt"].dropna()

if valid.empty:
    st.info("Brak wystarczających danych.")
else:
    day = valid.dt.day
    st.write(
        f"Klient zwykle wysyła dokumenty pomiędzy dniem "
        f"**{int(day.min())}** a **{int(day.max())}** każdego miesiąca."
    )
    st.write(
        f"Średnio około **{day.mean():.1f} dnia**, mediana: **{int(day.median())}**."
    )
