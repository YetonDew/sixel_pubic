import datetime as dt
import json
import re
from pathlib import Path
import shutil

from sixel_mail.gmail_client import GmailClient
from sixel_ai.pdf_analyzer import PDFAnalyzer, is_password_protected_pdf
from sixel_core.clients_db import ClientsDB
from sixel_router.path_router import PathRouter
from sixel_core.config_loader import CONFIG
from sixel_utils.file_hash import calculate_pdf_hash
from sixel_db.db import file_already_processed, register_file


# -----------------------------------------------------------------------------
# NORMALIZAR PERIODO
# -----------------------------------------------------------------------------
def _is_valid_yyyymm(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if "-" not in value:
        return False
    parts = value.split("-")
    if len(parts) != 2:
        return False
    y, m = parts
    if len(y) != 4 or not y.isdigit():
        return False
    if len(m) != 2 or not m.isdigit():
        return False
    mi = int(m)
    return 1 <= mi <= 12


def normalize_periodo(periodo: str, meta: dict) -> str:
    """
    Asegura que siempre tengamos YYYY-MM.
    1) Si periodo es válido → usarlo.
    2) Si hay fecha_documento → usar su año/mes.
    3) Fallback extra (URLOP/PAYROLL): buscar fecha en raw_text (dd.mm.yyyy).
    4) Si hay email_date → usar su año/mes (timestamp Unix).
    5) Si no → hoy.
    """
    if _is_valid_yyyymm(periodo):
        return periodo

    fecha = meta.get("fecha_documento", "")
    if isinstance(fecha, str) and "-" in fecha:
        try:
            y, m, *_ = fecha.split("-")
            cand = f"{y}-{m}"
            if _is_valid_yyyymm(cand):
                return cand
        except:
            pass

    # Fallback extra (URLOP/PAYROLL): buscar fecha en raw_text
    raw = meta.get("raw_text") or ""
    # dd.mm.yyyy o dd.mm.yy
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", raw)
    if m:
        d, mth, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        if len(y) == 4:
            mm = str(mth).zfill(2)
            cand = f"{y}-{mm}"
            if _is_valid_yyyymm(cand):
                return cand

    # Fallback: email_date (timestamp Unix en segundos)
    email_ts = meta.get("email_date")
    if isinstance(email_ts, (int, float)) and email_ts > 0:
        try:
            email_date = dt.datetime.fromtimestamp(email_ts).date()
            cand = f"{email_date.year}-{str(email_date.month).zfill(2)}"
            if _is_valid_yyyymm(cand):
                return cand
        except Exception:
            pass

    # Ultimo Fallback:
    today = dt.date.today()
    return f"{today.year}-{today.strftime('%m')}"


# -----------------------------------------------------------------------------
# NORMALIZAR TIPO
# -----------------------------------------------------------------------------
def normalize_tipo(tipo_raw: str | None) -> str:
    """
    Recibe el tipo crudo de la IA y devuelve una categoría estable:
    - FAKTURA
    - FVZ / FVS
    - BANK, PAYROLL, ZUS, etc.
    - OTRO
    """
    if not tipo_raw:
        return "OTRO"

    tipo = tipo_raw.strip().upper()

    if tipo in ["FVZ", "FVS", "PAYROLL", "BANK", "ZUS", "PIT", "CIT", "JPK", "PIT4", "URLOP", "UMOWA_O_PRACE", "UMOWA_ZLECENIE", "UMOWA", "KADRY"]:
        return tipo

    if tipo in ["FAKTURA", "FAKTURA VAT", "INVOICE"]:
        return "FAKTURA"

    return "OTRO"


# -----------------------------------------------------------------------------
# FIJAR FVZ / FVS
# -----------------------------------------------------------------------------
def fix_factura_type(meta: dict, client_entry: dict) -> str:
    """
    Determina FVS (venta) o FVZ (compra) usando nip_comprador / nip_vendedor.
    """

    # NIP del cliente
    client_nip = str(client_entry.get("nip") or "").strip()
    client_nip = "".join(ch for ch in client_nip if ch.isdigit())

    # NIPs detectados
    nip_comprador = str(meta.get("nip_comprador") or "").strip()
    nip_comprador = "".join(ch for ch in nip_comprador if ch.isdigit())

    nip_vendedor = str(meta.get("nip_vendedor") or "").strip()
    nip_vendedor = "".join(ch for ch in nip_vendedor if ch.isdigit())

    # VALIDACIÓN VISUAL (debug)
    print(f"➡️ FIX_FACTURA_TYPE: client={client_nip} | comprador={nip_comprador} | vendedor={nip_vendedor}")

    # 1) COMPRA
    if client_nip and nip_comprador and client_nip == nip_comprador:
        return "FVZ"

    # 2) VENTA
    if client_nip and nip_vendedor and client_nip == nip_vendedor:
        return "FVS"

    # 3) Reglas auxiliares por nombre
    client_name = (client_entry.get("display_name") or "").lower()
    proveedor = (meta.get("proveedor") or "").lower()
    nabywca = (meta.get("cliente") or "").lower()

    if client_name and client_name in proveedor:
        return "FVS"
    if client_name and client_name in nabywca:
        return "FVZ"

    # 4) No determinado
    return "OTRO"


# -----------------------------------------------------------------------------
# RESOLVER TIPO FINAL
# -----------------------------------------------------------------------------
def resolve_tipo(meta: dict, client_entry: dict) -> str:
    """
    Decide si es FVZ, FVS, payroll, bank, zus, etc.
    IMPORTANTE: Ahora usa el tipo NORMALIZADO.
    """

    # Detectar PARAGON por contenido primero
    raw_text = (meta.get("raw_text") or "").lower()
    if "paragon fiskalny" in raw_text or "\nparagon" in raw_text:
        tipo = "PARAGON"
        print("DEBUG final tipo:", tipo)
        return tipo

    # --- URLOPY / ZWOLNIENIA (KADRY) ---
    if any(k in raw_text for k in [
        "wniosek urlopowy",
        "urlop wypoczynkowy",
        "urlop bezpłatny",
        "urlop okolicznościowy",
        "chorobowy",
        "zwolnienie",
        "zwolnienie lekarskie",
        "l4",
    ]):
        tipo = "URLOP"
        print("DEBUG final tipo:", tipo)
        return tipo

    # --- UMOWY (KADRY) ---
    t = raw_text
    # Umowa o pracę
    if "umowa o prac" in t or "umowa o pracę" in t:
        tipo = "UMOWA_O_PRACE"
        print("DEBUG final tipo:", tipo)
        return tipo

    # Umowa zlecenie
    if "umowa zlecen" in t or "umowa zlecenie" in t:
        tipo = "UMOWA_ZLECENIE"
        print("DEBUG final tipo:", tipo)
        return tipo

    # Fallback: hay "umowa" pero no sabemos cuál
    if "umowa" in t and any(k in t for k in ["zawarta", "strony", "pracownik", "zleceniobiorca", "zleceniodawca"]):
        tipo = "UMOWA"
        print("DEBUG final tipo:", tipo)
        return tipo

    # Detectar recordatorios / cobros / deuda
    t = raw_text
    if any(k in t for k in [
        "przypomnienie o płatności",
        "wezwanie do zapłaty",
        "zaległość",
        "wymagalne do zapłaty",
    ]):
        tipo = "PRZYPOMNIENIE"
        print("DEBUG final tipo:", tipo)
        return tipo

    tipo_raw = normalize_tipo(meta.get("tipo_documento", "OTRO"))

    # Casos fiscales
    SPECIALS = ["PAYROLL", "BANK", "ZUS", "PIT", "CIT", "JPK", "PIT4", "PARAGON", "PRZYPOMNIENIE", "URLOP", "UMOWA_O_PRACE", "UMOWA_ZLECENIE", "UMOWA", "KADRY"]
    if tipo_raw in SPECIALS:
        tipo = tipo_raw
        print("DEBUG final tipo:", tipo)
        return tipo

    # ¿Es factura?
    is_invoice = (tipo_raw == "FAKTURA")

    # También detectar por texto
    if "faktura" in (meta.get("raw_text") or "").lower():
        is_invoice = True

    if is_invoice:
        tipo = fix_factura_type(meta, client_entry)
        print("DEBUG final tipo:", tipo)
        return tipo

    tipo = "OTRO"
    print("DEBUG final tipo:", tipo)
    return tipo


# -----------------------------------------------------------------------------
# MAIN PIPELINE
# -----------------------------------------------------------------------------
def main():
    print("\n=== SIXEL pipeline iniciado ===\n")

    # Descargar PDFs
    GmailClient().download_pdfs()

    analyzer = PDFAnalyzer()
    clients_db = ClientsDB()
    router = PathRouter()

    inbox = Path(CONFIG.get("paths.inbox_raw"))
    # Buscar PDFs sin importar mayúsculas/minúsculas
    pdf_files = [p for p in inbox.iterdir() if p.suffix.lower() == ".pdf"]

    duplicates_dir = inbox / "_duplicates"
    duplicates_dir.mkdir(parents=True, exist_ok=True)

    for pdf in pdf_files:

        # Hash para duplicados
        file_hash = calculate_pdf_hash(pdf)

        if file_already_processed(file_hash):
            print(f"[SIXEL] 🟡 Duplicado detectado → {pdf.name}")

            target = duplicates_dir / pdf.name

            # Evitar colisión de nombres
            if target.exists():
                stem = target.stem
                suf = target.suffix
                i = 2
                while (duplicates_dir / f"{stem}__{i}{suf}").exists():
                    i += 1
                target = duplicates_dir / f"{stem}__{i}{suf}"

            # Mover archivo
            shutil.move(str(pdf), str(target))

            print(f"[SIXEL] 🗂️ Movido a duplicates → {target}")
            continue

        # ---------------------------------------------------------------------
        # IGNORAR PDFs PROTEGIDOS / NO LEGIBLES (NO GUARDAR, NO MOVER)
        # ---------------------------------------------------------------------
        if is_password_protected_pdf(pdf):
            print(f"[SIXEL] 🔒 PDF protegido o no legible, ignorado y eliminado → {pdf.name}")

            # borrar también el meta json si existe
            meta_file = Path(str(pdf) + ".meta.json")
            if meta_file.exists():
                try:
                    meta_file.unlink()
                except Exception as e:
                    print(f"[SIXEL] ⚠ No se pudo eliminar meta {meta_file.name}: {e}")

            # registrar como "skipped" para que no vuelva a salir
            # (cliente y tipo marcados como SKIPPED, sin periodo)
            try:
                register_file(
                    hash_value=file_hash,
                    filename=pdf.name,
                    client_code="SKIPPED",
                    tipo="SKIPPED",
                    periodo="",
                    target_path="SKIPPED_PASSWORD_PROTECTED",
                    meta={"skip_reason": "password_or_unreadable"}
                )
            except Exception as e:
                print(f"[SIXEL] ⚠ No se pudo registrar skip en DB: {e}")

            # eliminar el pdf del inbox
            try:
                pdf.unlink()
            except Exception as e:
                print(f"[SIXEL] ⚠ No se pudo eliminar {pdf.name}: {e}")

            continue

        print(f"[SIXEL] Analizando → {pdf.name}")

        # Analizar
        meta = analyzer.analyze(pdf)
        print("DEBUG keys:", meta.keys())
        print("DEBUG nip_comprador:", meta.get("nip_comprador"))
        print("DEBUG nip_vendedor:", meta.get("nip_vendedor"))
        print("DEBUG raw_text sample:", (meta.get("raw_text") or "")[:800])

        # Merge con metadata del email
        meta_file = Path(str(pdf) + ".meta.json")
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                meta.update(json.load(f))

        # --- Detectar PARAGON por contenido (fallback seguro) ---
        def valid_nip_10(v: str | None) -> str:
            d = "".join(ch for ch in str(v or "") if ch.isdigit())
            return d if len(d) == 10 else ""

        raw = (meta.get("raw_text") or "")
        raw_low = raw.lower()

        is_paragon = ("paragon fiskalny" in raw_low) or re.search(r"\bparagon\b", raw_low) is not None

        if is_paragon:
            meta["tipo_documento"] = "PARAGON"

            # En paragon: el NIP repetido "NIP: ..." suele ser el vendedor
            # Forzamos nip_vendedor desde "NIP: 10 digits" si existe
            m_seller = re.search(r"\bNIP\b[:\s]*?(?:PL)?\s*(\d{10})", raw, flags=re.I)
            if m_seller:
                meta["nip_vendedor"] = m_seller.group(1)

            # NIP NABYWCY si existe y es 10 dígitos
            m_buyer = re.search(r"NIP\s*NABYWCY\s*[:\-]?\s*(?:PL)?\s*(\d{10})", raw, flags=re.I)
            if m_buyer:
                meta["nip_comprador"] = m_buyer.group(1)
            else:
                # Si no hay NIP NABYWCY válido, asumimos comprador = cliente actual (si lo tienes)
                # Esto evita que el NIP del vendedor termine como comprador.
                if client_entry := clients_db.match(meta, filename=pdf.name):
                    meta["nip_comprador"] = valid_nip_10(client_entry.get("nip"))

        # Matchear cliente primero
        client_entry = clients_db.match(meta, filename=pdf.name)

        # Si NO hay cliente, no se puede clasificar FVZ/FVS
        if client_entry is None:
            tipo = normalize_tipo(meta.get("tipo_documento", "OTRO"))
            # Si es factura, pero no sabemos a quién pertenece → OTRO
            if tipo == "FAKTURA":
                tipo = "OTRO"
        else:
            tipo = resolve_tipo(meta, client_entry)

        periodo = normalize_periodo(meta.get("periodo", ""), meta)

        print("DEBUG fecha_documento:", meta.get("fecha_documento"))
        print("DEBUG periodo:", meta.get("periodo"))

        # Resolver cliente o poner DESCONOCIDO
        if client_entry:
            client_code = client_entry.get("code")
            client_base = client_entry.get("base_path")
        else:
            print(f"[SIXEL] ⚠ No se encontró cliente → {pdf.name}, usando DESCONOCIDO")
            client_code = "DESCONOCIDO"
            client_base = "symulacja_DSM/DESCONOCIDO"

        # Construcción de ruta final
        target = router.build(client_base, periodo, tipo)
        target.mkdir(parents=True, exist_ok=True)

        shutil.move(str(pdf), target / pdf.name)

        print(f"[SIXEL] Movido {pdf.name} → {target}/{pdf.name}")

        # Registrar
        register_file(
			hash_value=file_hash,
			filename=pdf.name,
			client_code=client_code,
			tipo=tipo,
			periodo=periodo,
			target_path=str(target / pdf.name),
			meta=meta
		)


    print("=== SIXEL finalizado ===")


if __name__ == "__main__":
    main()
