from __future__ import print_function
import base64
import email
import hashlib
import json
import os
import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from sixel_core.config_loader import CONFIG

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

FORWARDED_FROM_RE = re.compile(
    r'(?im)^(from|od|de)\s*:\s*(.+)$'
)


def extract_forwarded_from_from_text(text: str) -> str:
    if not text:
        return ""
    m = FORWARDED_FROM_RE.search(text)
    if not m:
        return ""
    line = m.group(2).strip()

    # Si viene "Name <email@domain>" extraemos email
    em = re.search(r'[\w\.\+\-]+@[\w\.\-]+\.\w+', line)
    return em.group(0).lower() if em else ""


def build_safe_pdf_name(original_filename: str, uniq_seed: str, max_stem_len: int = 60) -> str:
    """
    Genera un nombre de archivo PDF seguro y único.
    
    Args:
        original_filename: nombre del attachment (puede ser largo/feo)
        uniq_seed: algo único y estable del email/attachment (ej: message_id + attachment_id)
        max_stem_len: longitud máxima del stem antes del hash
    
    Returns:
        Nombre de archivo limpio con formato: stem__hash.pdf
    """
    original_filename = (original_filename or "file.pdf").strip()

    # stem/ext
    stem, ext = os.path.splitext(original_filename)
    ext = ext if ext else ".pdf"
    if ext.lower() != ".pdf":
        ext = ".pdf"

    # stem "humano" limpio y corto
    stem = stem.strip()
    stem = stem.replace("/", "_").replace("\\", "_")
    stem = re.sub(r'[<>:"|?*\x00-\x1F]', "_", stem)
    stem = stem.rstrip(" .")
    if not stem:
        stem = "file"

    # quita repetidores tipo " (1) (2) (3) ..."
    stem = re.sub(r'(\s*\(\d+\))+$', "", stem).strip()
    if not stem:
        stem = "file"

    stem = stem[:max_stem_len]

    # hash estable basado en uniq_seed
    h = hashlib.sha1(uniq_seed.encode("utf-8", errors="ignore")).hexdigest()[:10]

    return f"{stem}__{h}{ext}"

class GmailClient:
    def __init__(self):
        self.token_path = Path("config/token.json")
        self.creds_path = Path("config/credentials.json")

    def _get_service(self):
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            try:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    raise Exception("Need new login")
            except Exception:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.creds_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        return build("gmail", "v1", credentials=creds)

    def download_pdfs(self, query: str | None = None):
        raw_root = Path(CONFIG.get("paths.inbox_raw"))
        raw_root.mkdir(exist_ok=True)

        service = self._get_service()

        if query is None:
            # Solo emails no leídos, con adjuntos, últimos x días
            query = "is:unread has:attachment newer_than:3d"

        result = service.users().messages().list(
            userId="me", q=query
        ).execute()

        messages = result.get("messages", [])

        for m in messages:
            msg_id = m["id"]

            # RAW para extraer from/subject
            raw_msg = service.users().messages().get(
                userId="me", id=msg_id, format="raw"
            ).execute()

            msg_bytes = base64.urlsafe_b64decode(raw_msg["raw"])
            msg_obj = email.message_from_bytes(msg_bytes)

            email_from = msg_obj.get("From", "")
            email_subject = msg_obj.get("Subject", "")

            # Extraer forwarded_from del body del mensaje
            forwarded_from = ""
            if msg_obj.is_multipart():
                for part in msg_obj.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body_text = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            forwarded_from = extract_forwarded_from_from_text(body_text)
                            if forwarded_from:
                                break
                        except Exception:
                            pass
            else:
                try:
                    body_text = msg_obj.get_payload(decode=True).decode("utf-8", errors="ignore")
                    forwarded_from = extract_forwarded_from_from_text(body_text)
                except Exception:
                    pass

            # Mensaje completo para leer partes (attachments)
            full_msg = service.users().messages().get(
                userId="me", id=msg_id
            ).execute()

            parts = full_msg.get("payload", {}).get("parts", [])

            for part in parts:
                filename = part.get("filename")
                body = part.get("body", {})

                if filename and filename.lower().endswith(".pdf"):
                    att_id = body.get("attachmentId")
                    if not att_id:
                        continue

                    attachment = service.users().messages().attachments().get(
                        userId="me",
                        messageId=msg_id,
                        id=att_id
                    ).execute()

                    file_data = base64.urlsafe_b64decode(attachment["data"])

                    # Generar nombre seguro y único usando message_id + attachment_id
                    uniq_seed = f"{msg_id}_{att_id}"
                    safe_filename = build_safe_pdf_name(filename, uniq_seed)
                    file_path = raw_root / safe_filename

                    with open(file_path, "wb") as f:
                        f.write(file_data)

                    # Guardar meta del correo junto al nombre final
                    email_ts = int(full_msg.get("internalDate", 0)) // 1000
                    meta_path = raw_root / (file_path.name + ".meta.json")
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "email_from": email_from,
                            "email_subject": email_subject,
                            "forwarded_from": forwarded_from,
                            "email_date": email_ts
                        }, f, indent=2)

                    print(f"[SIXEL] PDF descargado → {file_path}")
