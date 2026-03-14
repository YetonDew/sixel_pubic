from pathlib import Path
from sixel_core.config_loader import CONFIG

MONTHS = {
    "01": "01_Styczeń", "02": "02_Luty", "03": "03_Marzec",
    "04": "04_Kwiecień", "05": "05_Maj", "06": "06_Czerwiec",
    "07": "07_Lipiec", "08": "08_Sierpień", "09": "09_Wrzesień",
    "10": "10_Październik", "11": "11_Listopad", "12": "12_Grudzień",
}

FISCAL_MAPPING = {
    "ZUS": "02_Podatki/ZUS",
    "PIT": "02_Podatki/PIT",
    "PIT4": "02_Podatki/PIT4",
    "CIT": "02_Podatki/CIT",
    "JPK": "02_Podatki/JPK",
    "VAT": "02_Podatki/VAT",
    "VATUE": "02_Podatki/VAT_UE",
    "DEKLARACJA": "02_Podatki/Deklaracje",
    "MELDUNEK": "02_Podatki/Meldunki",
}

class PathRouter:

    def build(self, client_base_path: str, periodo: str, tipo: str) -> Path:

        # NORMALIZACIÓN AGRESIVA DEL TIPO
        t = (
            tipo
            .replace("−", "-")  # guion unicode
            .replace("–", "-")  # guion largo
            .replace(" ", "")
            .replace("\n", "")
            .replace("\t", "")
            .strip()
            .upper()
        )

        # EQUIPARACIONES
        if t.startswith("VAT") and t not in ["VATUE"]:
            t = "VAT"

        if t.replace("-", "") in ["VATUE", "VATUE", "VATUE"]:
            t = "VATUE"

        if t.startswith("PIT4"):
            t = "PIT4"

        year, month = periodo.split("-")
        month_dir = MONTHS[month]

        storage_root = Path(CONFIG.get("paths.storage_root"))
        client_root = storage_root / Path(client_base_path).name

        # --- URLOPY / ZWOLNIENIA (KADRY) ---
        if t == "URLOP":
            return client_root / "03_Kadry_Place" / year / month_dir / "Urlopy"

        # --- FORMULARZE KADROWE ---
        if t == "KADRY":
            return client_root / "03_Kadry_Place" / year / month_dir / "Kadry_Formularze"

        # --- UMOWY (KADRY) ---
        if t == "UMOWA_O_PRACE":
            return client_root / "03_Kadry_Place" / year / month_dir / "Umowy" / "Umowa_o_Prace"

        if t == "UMOWA_ZLECENIE":
            return client_root / "03_Kadry_Place" / year / month_dir / "Umowy" / "Umowa_Zlecenie"

        if t == "UMOWA":
            return client_root / "03_Kadry_Place" / year / month_dir / "Umowy"

        # PAYROLL
        if t == "PAYROLL":
            return client_root / "03_Kadry_Place" / year / month_dir / "Listy_Plac"

        # Fiscales
        if t in FISCAL_MAPPING:
            return client_root / FISCAL_MAPPING[t] / year / month_dir

        # BANK
        if t == "BANK":
            return client_root / "01_Księgowość" / year / month_dir / "03_Banki"

        # PARAGON -> dentro de Zakupy FVZ / Paragony
        if t == "PARAGON":
            return client_root / "01_Księgowość" / year / month_dir / "01_Zakupy_FVZ" / "Paragony"

        # PRZYPOMNIENIE -> recordatorios de pago
        if t == "PRZYPOMNIENIE":
            return client_root / "01_Księgowość" / year / month_dir / "04_Inne" / "Przypomnienia"

        # Facturas
        if t in ["FVZ", "FVS"]:
            factura_map = {"FVZ": "01_Zakupy_FVZ", "FVS": "02_Sprzedaz_FVS"}
            return client_root / "01_Księgowość" / year / month_dir / factura_map[t]

        # Otros
        return client_root / "01_Księgowość" / year / month_dir / "04_Inne"


