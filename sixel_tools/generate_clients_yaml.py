import math
import re
import pandas as pd
import yaml
from pathlib import Path

CSV_PATH = Path("wykaz_klientow.csv")
OUTPUT_PATH = Path("../data/clients.yaml")

def load_clients_from_csv(csv_path: Path):
    df = pd.read_csv(csv_path, sep=";")

    grouped = {}

    for _, row in df.iterrows():
        base_raw = row.get("name of base")
        if not isinstance(base_raw, str):
            continue
        base = base_raw.strip()
        if not base:
            continue

        company = row.get("Name of company")
        company = company.strip() if isinstance(company, str) else ""

        code_field = row.get("Code")
        code_field = code_field.strip() if isinstance(code_field, str) else ""

        nip_val = row.get("NIP")
        nip = ""
        if isinstance(nip_val, str):
            nip = nip_val.strip()
        elif isinstance(nip_val, (int, float)) and not (
            isinstance(nip_val, float) and math.isnan(nip_val)
        ):
            nip = str(int(nip_val)).strip()

        email_val = row.get("E-mail")
        emails = []
        if isinstance(email_val, str):
            # separa por ; o ,
            for part in re.split(r"[;,]", email_val):
                p = part.strip()
                if p:
                    emails.append(p)

        # si no hay nada útil, saltamos
        if not company and not nip and not emails:
            continue

        g = grouped.setdefault(
            base,
            {
                "company_names": set(),
                "codes": set(),
                "nips": set(),
                "emails": set(),
            },
        )

        if company:
            g["company_names"].add(company)
        if code_field:
            g["codes"].add(code_field)
        if nip:
            g["nips"].add(nip)
        for e in emails:
            g["emails"].add(e)

    clients = []
    for base, info in sorted(grouped.items(), key=lambda kv: kv[0].upper()):
        codes = sorted(info["codes"])
        companies = sorted(info["company_names"])
        nips = sorted(info["nips"])
        emails = sorted(info["emails"])

        display_name = companies[0] if companies else base
        nip = nips[0] if nips else ""

        vendors_keywords = [base]
        for c in codes:
            if c and c not in vendors_keywords:
                vendors_keywords.append(c)
        for comp in companies:
            if comp and comp not in vendors_keywords:
                vendors_keywords.append(comp)

        clients.append(
            {
                "code": base,
                "display_name": display_name,
                "nip": nip,
                "email_patterns": emails,
                "vendors_keywords": vendors_keywords,
                "base_path": f"symulacja_DSM/{base}",
            }
        )

    return {"clients": clients}


def main():
    data = load_clients_from_csv(CSV_PATH)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    print(f"[OK] clients.yaml generado con {len(data['clients'])} clientes → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
