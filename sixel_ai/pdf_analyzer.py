import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from httpx import ReadTimeout
from openai import OpenAI
from pypdf import PdfReader

from sixel_core.config_loader import CONFIG
from sixel_ai.sixel_ocr import ocr_pdf_google_vision  # tu módulo Vision OCR

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM = """
Eres un analista contable experto en documentos polacos.
Tu tarea: leer el PDF, identificar el tipo de documento y extraer SOLO los datos necesarios para archivarlo en carpetas contables.

MUY IMPORTANTE:
- NO decidas si es FVZ o FVS. Eso lo hará otro sistema.
- Tu trabajo es:
  - identificar si el documento es una factura u otro tipo especial (BANK, ZUS, PAYROLL, etc.)
  - encontrar el NIP del COMPRADOR y del VENDEDOR
  - devolver un JSON limpio con los campos indicados.

DEVUELVE SIEMPRE SOLO ESTE JSON EXACTO (MISMAS CLAVES):

{
  "tipo_documento": "",
  "fecha_documento": "",
  "periodo": "",
  "nip_comprador": "",
  "nip_vendedor": "",
  "cliente": "",
  "proveedor": "",
  "raw_text": ""
}

REGLAS PARA CADA CAMPO:

1) "tipo_documento"
   Valores permitidos (en MAYÚSCULAS):

   - "FAKTURA"      → para cualquier factura VAT o invoice estándar
   - "FAKTURA VAT"  → también factura, si lo prefieres
   - "PARAGON"      → paragon fiskalny / paragon / ticket
   - "PRZYPOMNIENIE" → przypomnienie o płatności / wezwanie do zapłaty / payment reminder

   - "PAYROLL"      → nóminas, listy płac, wynagrodzenia
   - "BANK"         → wyciąg bankowy, potwierdzenie z banku
   - "ZUS"          → deklaracje / potwierdzenia ZUS
   - "PIT"          → deklaracje PIT (impuesto personal)
   - "CIT"          → deklaracje CIT (impuesto sociedades)
   - "JPK"          → pliki JPK
   - "PIT4"         → declaraciones PIT-4
   - "URLOP" → wyłącznie wnioski urlopowe (urlop wypoczynkowy, bezpłatny, okolicznościowy) oraz zwolnienia lekarskie (L4)
   - "KADRY" → dokumenty kadrowe niebędące urlopem, np. kwestionariusz osobowy, dane pracownika, formularze personalne, onboarding


   Si no encaja en nada anterior → "OTRO".

   MUY IMPORTANTE:
   - NO uses "FVZ" ni "FVS" en "tipo_documento".
   - Si tienes dudas, usa "OTRO".

2) "fecha_documento"
   - Fecha de emisión del documento.
   - Formato obligatorio: "YYYY-MM-DD" (por ejemplo "2025-01-31").
   - Si hay varias fechas, usa la FECHA DE EMISIÓN de la factura/documento.
   - Si no puedes encontrar ninguna fecha clara → cadena vacía "".

3) "periodo"
   - Periodo contable al que corresponde el documento.
   - Formato obligatorio: "YYYY-MM" (por ejemplo "2025-01").
   - Normalmente coincide con el mes de la "fecha_documento".
   - Si es un documento de un periodo concreto (por ejemplo: JPK, ZUS, PIT):
     - Usa el año-mes indicado en el documento.
   - Si no puedes deducirlo con seguridad → deja "" (vacío).

4) "nip_comprador"
   - NIP de la empresa que figura como COMPRADOR / NABYWCA.
   - Busca bloques de texto con etiquetas como:
     - "Nabywca", "Kupujący", "Odbiorca", "Buyer", "Odbiorca faktury"
   - Dentro de ese bloque localiza el NIP.
   - Devuelve el NIP completo tal como aparece (por ejemplo "PL1234567890" o "123-456-78-90").
   - Si no encuentras el NIP del comprador → "" (vacío).

5) "nip_vendedor"
   - NIP de la empresa que figura como VENDEDOR / SPRZEDAWCA.
   - Busca bloques de texto con etiquetas como:
     - "Sprzedawca", "Wystawca", "Seller", "Dostawca", "Fakturowca"
   - Dentro de ese bloque localiza el NIP.
   - Devuelve el NIP completo tal como aparece (por ejemplo "PL0987654321" o "098-765-43-21").
   - Si no encuentras el NIP del vendedor → "" (vacío).

   NOTA: Si solo encuentras un NIP en todo el documento y está claramente bajo "Nabywca"/"Buyer" → ponlo en "nip_comprador" y deja "nip_vendedor" vacío.
         Si solo lo encuentras bajo "Sprzedawca"/"Seller" → ponlo en "nip_vendedor" y deja "nip_comprador" vacío.

6) "cliente"
   - Nombre de la empresa COMPRADORA (nabywca).
   - Extrae el texto de nombre de empresa que acompaña a "Nabywca" / "Kupujący" / "Buyer".
   - Devuelve un texto corto, limpio, sin direcciones largas ni líneas innecesarias.

7) "proveedor"
   - Nombre de la empresa VENDEDORA (sprzedawca).
   - Extrae el texto de nombre de empresa que acompaña a "Sprzedawca" / "Seller" / "Wystawca".
   - Devuelve un texto corto, limpio, sin direcciones largas ni líneas innecesarias.

8) "raw_text"
   - Texto plano del documento.
   - Puede ser todo el contenido o una parte representativa.
   - Quita elementos muy repetitivos si quieres (pie de página, publicidad), pero incluye lo suficiente para que otro sistema reconozca el documento.

REGLAS GENERALES:

- El resultado debe ser SIEMPRE un JSON VÁLIDO con EXACTAMENTE las claves:
  ["tipo_documento", "fecha_documento", "periodo", "nip_comprador", "nip_vendedor", "cliente", "proveedor", "raw_text"]

- No añadas más campos.
- No devuelvas explicaciones, ni comentarios, ni texto fuera del JSON.
- No escribas nada antes ni después del JSON.
- Si tienes dudas en algún campo, deja una cadena vacía "" para ese campo.
- Si ves "PARAGON FISKALNY" o "PARAGON", usa tipo_documento = "PARAGON".
Si ves "NIP NABYWCY:" y luego un NIP, úsalo como nip_comprador.

"""


def is_password_protected_pdf(pdf_path: Path) -> bool:
    """
    Devuelve True si el PDF está encriptado / protegido / no se puede leer.
    Usa pypdf y es MUY rápido (no OCR, no IA).
    """
    try:
        reader = PdfReader(str(pdf_path))

        if getattr(reader, "is_encrypted", False):
            try:
                ok = reader.decrypt("")  # algunos PDFs abren con password vacío
                if not ok:
                    return True
            except Exception:
                return True

        if len(reader.pages) > 0:
            _ = reader.pages[0].extract_text() or ""

        return False

    except Exception:
        return True

def _valid_nip_10(value: str | None) -> str:
    """NIP PL válido = 10 dígitos. Elimina PL, guiones, espacios; descarta EANs."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits if len(digits) == 10 else ""


def _extract_nip_nabywcy_from_text(text: str) -> str:
    """Captura NIP NABYWCY del texto: 'NIP NABYWCY: PL5731082788' o 'NIP NABYWCY: 5731082788'"""
    m = re.search(r"NIP\s*NABYWCY\s*[:\-]?\s*(?:PL)?\s*(\d{10})", text, flags=re.I)
    return m.group(1) if m else ""


def _pdf_has_embedded_text(pdf: Path, min_chars: int = 80) -> bool:
    """
    True si el PDF parece tener texto real embebido (no sólo imágenes).
    No es perfecto, pero es robusto y barato.
    """
    try:
        reader = PdfReader(str(pdf))
        sample = []
        for i, page in enumerate(reader.pages[:2]):  # basta 1-2 páginas
            text = (page.extract_text() or "").strip()
            if text:
                sample.append(text)
        joined = " ".join(sample).strip()
        return len(joined) >= min_chars
    except Exception:
        return False


def _call_openai_on_file(pdf: Path) -> dict:
    """Tu flujo actual: subir PDF y pedir JSON."""
    try:
        uploaded = client.files.create(
            file=open(pdf, "rb"),
            purpose="user_data"
        )
    except Exception as e:
        print(f"[SIXEL] ❌ Error subiendo archivo {pdf}: {e}")
        return PDFAnalyzer()._empty()

    MAX_RETRIES = 3
    WAIT = 2

    for attempt in range(MAX_RETRIES):
        try:
            completion = client.chat.completions.create(
                model=CONFIG.get("openai.model"),
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": [
                            {"type": "file", "file": {"file_id": uploaded.id}},
                            {"type": "text", "text": "Analiza este documento y devuelve SOLO el JSON indicado."}
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                timeout=50
            )
            return json.loads(completion.choices[0].message.content)

        except ReadTimeout:
            print(f"[SIXEL] ⚠ Timeout analizando {pdf.name}, intento {attempt+1}/3…")
            time.sleep(WAIT)

        except Exception as e:
            print(f"[SIXEL] ❌ Error analizando {pdf.name}: {e}")
            if attempt == MAX_RETRIES - 1:
                return PDFAnalyzer()._empty()
            time.sleep(WAIT)

    return PDFAnalyzer()._empty()


def _call_openai_on_text(raw_text: str) -> dict:
    """
    Para scans: ya tenemos OCR. Mucho más estable que subir el PDF al modelo.
    """
    MAX_RETRIES = 3
    WAIT = 2

    for attempt in range(MAX_RETRIES):
        try:
            completion = client.chat.completions.create(
                model=CONFIG.get("openai.model"),
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            "Este es el texto OCR del documento (puede contener EAN/REGON). "
                            "Extrae los campos y devuelve SOLO el JSON indicado.\n\n"
                            f"OCR_TEXT:\n{raw_text}"
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                timeout=50
            )
            return json.loads(completion.choices[0].message.content)

        except ReadTimeout:
            print(f"[SIXEL] ⚠ Timeout analizando OCR text, intento {attempt+1}/3…")
            time.sleep(WAIT)

        except Exception as e:
            print(f"[SIXEL] ❌ Error analizando OCR text: {e}")
            if attempt == MAX_RETRIES - 1:
                return PDFAnalyzer()._empty()
            time.sleep(WAIT)

    return PDFAnalyzer()._empty()


class PDFAnalyzer:
    def analyze(self, pdf: Path) -> dict:
        """
        Opción B (PRO):
        - Si el PDF tiene texto embebido -> usar el flujo actual (archivo directo al modelo)
        - Si es scan (sin texto) -> Google Vision OCR -> modelo interpreta SOLO el texto OCR
        - Validación final de NIPs (10 dígitos) para evitar EANs.
        """
        pdf = Path(pdf)

        if is_password_protected_pdf(pdf):
            print(f"[SIXEL] PDF protegido (password), se omite -> {pdf.name}")
            return self._empty()

        has_text = _pdf_has_embedded_text(pdf)
        if has_text:
            meta = _call_openai_on_file(pdf)
            # (aun así, normalizamos NIPs)
            meta["nip_comprador"] = _valid_nip_10(meta.get("nip_comprador"))
            meta["nip_vendedor"] = _valid_nip_10(meta.get("nip_vendedor"))

            # Extraer NIP NABYWCY de PARAGON si no se encontró antes
            raw = meta.get("raw_text") or ""
            if (meta.get("tipo_documento") or "").upper() == "PARAGON" and not meta.get("nip_comprador"):
                found = _extract_nip_nabywcy_from_text(raw)
                if found:
                    meta["nip_comprador"] = found

            return meta

        # Scan / imagen -> OCR Google Vision
        try:
            raw_text, ocr_debug = ocr_pdf_google_vision(pdf, cleanup=False)
        except Exception as e:
            print(f"[SIXEL] ❌ Vision OCR falló para {pdf.name}: {e}")
            return self._empty()

        # Interpretación por modelo usando texto OCR
        meta = _call_openai_on_text(raw_text)

        # Asegurar que raw_text final sea el OCR (fuente de verdad)
        meta["raw_text"] = raw_text

        # Guardar debug para troubleshooting
        meta["_ocr_debug"] = ocr_debug  # si NO quieres este campo, lo quitas o lo guardas fuera

        # Validación NIP (clave para no confundir EAN)
        meta["nip_comprador"] = _valid_nip_10(meta.get("nip_comprador"))
        meta["nip_vendedor"] = _valid_nip_10(meta.get("nip_vendedor"))

        # Extraer NIP NABYWCY de PARAGON si no se encontró antes
        raw = meta.get("raw_text") or ""
        if (meta.get("tipo_documento") or "").upper() == "PARAGON" and not meta.get("nip_comprador"):
            found = _extract_nip_nabywcy_from_text(raw)
            if found:
                meta["nip_comprador"] = found

        return meta

    def _empty(self):
        return {
            "tipo_documento": "OTRO",
            "fecha_documento": "",
            "periodo": "",
            "nip_comprador": "",
            "nip_vendedor": "",
            "cliente": "",
            "proveedor": "",
            "raw_text": ""
        }
