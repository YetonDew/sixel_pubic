import yaml


def normalize_nip(value: str | None) -> str:
    """
    Devuelve SOLO dígitos.
    Soporta formatos como: 'PL5731082788', '573-108-27-88', 'NIP: 573 108 27 88'.
    """
    if not value:
        return ""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    # NIP en PL normalmente tiene 10 dígitos
    if len(digits) > 10:
        # si OCR añade basura o captura VAT UE, nos quedamos con los últimos 10
        digits = digits[-10:]
    return digits


class ClientsDB:
    def __init__(self, path: str = "data/clients.yaml"):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.clients = data.get("clients", [])

    def match_by_email(self, email_from: str, email_to: str = "", email_subject: str = ""):
        """
        Cliente principal determinado por metadatos del correo.
        Coincidencia parcial de patrones registrados.
        """
        haystack = " ".join([
            (email_from or ""),
            (email_to or ""),
            (email_subject or ""),
        ]).lower()

        if not haystack.strip():
            return None

        for client in self.clients:
            for pattern in client.get("email_patterns", []):
                p = (pattern or "").lower().strip()
                if p and p in haystack:
                    return client

        return None

    def match_by_nip(self, nip: str):
        """
        Match por NIP normalizado (10 dígitos).
        """
        nip_clean = normalize_nip(nip)
        if not nip_clean:
            return None

        for client in self.clients:
            client_nip = normalize_nip(client.get("nip", ""))
            if client_nip and client_nip == nip_clean:
                return client

        return None

    def match(self, meta: dict, filename: str = ""):
        """
        Matching:
        1) Email (from/to/subject)
        2) NIP (comprador/vendedor/nip genérico)
        3) Keywords en texto (raw_text/proveedor/cliente)
        4) (fallback) buscar el NIP del cliente dentro del raw_text (por si el extractor no lo capturó)
        """

        # 1) EMAIL (prioridad: forwarded_from -> email_from)
        email_from = meta.get("email_from", "") or meta.get("from", "")
        forwarded_from = meta.get("forwarded_from", "")

        client = self.match_by_email(forwarded_from) or self.match_by_email(email_from)
        if client:
            return client

        # 2) NIP (IMPORTANTE: aquí está el fix real)
        # Tu extractor suele guardar nip_comprador / nip_vendedor, no "nip".
        candidates = [
            meta.get("nip_comprador"),
            meta.get("nip_vendedor"),
            meta.get("nip"),  # por si tu extractor lo usa en otros docs
        ]
        for nip_candidate in candidates:
            client = self.match_by_nip(nip_candidate)
            if client:
                return client

        # 2.5) URLOP/ZWOLNIENIA: matching especial (sin NIP, por email + keywords)
        raw_text = (meta.get("raw_text") or "").lower()
        is_urlop = any(k in raw_text for k in [
            "wniosek urlopowy",
            "urlop wypoczynkowy",
            "urlop bezpłatny",
            "zwolnienie",
            "zwolnienie lekarskie",
            "chorobowy",
        ])

        if is_urlop:
            # Email tiene prioridad incluso en URLOP
            email_from = meta.get("email_from", "") or meta.get("from", "")
            forwarded_from = meta.get("forwarded_from", "")
            client = self.match_by_email(forwarded_from) or self.match_by_email(email_from)
            if client:
                return client

            # Fallback a keywords por empresa/proveedor (muy útil en URLOP)
            proveedor = (meta.get("proveedor") or "").lower()
            cliente_txt = (meta.get("cliente") or "").lower()
            
            for client in self.clients:
                for kw in client.get("vendors_keywords", []):
                    kw_l = (kw or "").lower().strip()
                    if kw_l and (kw_l in raw_text or kw_l in proveedor or kw_l in cliente_txt):
                        return client

        # 3) KEYWORDS en texto
        proveedor = (meta.get("proveedor") or "").lower()
        cliente_txt = (meta.get("cliente") or "").lower()

        for client in self.clients:
            for kw in client.get("vendors_keywords", []):
                kw_l = (kw or "").lower().strip()
                if kw_l and (kw_l in raw_text or kw_l in proveedor or kw_l in cliente_txt):
                    return client

        # 4) FALLBACK: buscar el NIP de cada cliente dentro del raw_text (incluye casos 'PL...' o con separadores)
        # Esto ayuda cuando el extractor no llena nip_comprador/nip_vendedor pero el NIP sí está en el texto.
        raw_digits = "".join(ch for ch in raw_text if ch.isdigit())
        if raw_digits:
            for client in self.clients:
                client_nip = normalize_nip(client.get("nip", ""))
                if client_nip and client_nip in raw_digits:
                    return client

        return None
