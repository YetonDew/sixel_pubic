# SIXEL - Smart Intelligent eXtraction & Email Logistics

This is a personal project I started to help my mother-in-law, who runs an accounting business and often deals with email chaos when organizing documents into the correct folders. I decided to build SIXEL to automate that workflow: collect files from emails, classify them, and place them in the right location automatically, so the process is faster, cleaner, and less error-prone.

SIXEL is a document management and accounting automation system that processes Gmail attachments and PDF files, classifies them with AI/OCR, and routes documents into a DSM-like folder structure.

## Main Features

- Gmail integration for downloading PDF attachments.
- OCR and AI extraction of accounting metadata.
- Classification into accounting categories (for example: `FVZ`, `FVS`, `BANK`, `PAYROLL`, `ZUS`, `PIT`, `CIT`, `JPK`, `OTRO`).
- Routing based on client, period, and document type.
- SQLite registration of processed files.
- Streamlit dashboard for monitoring.

## Project Structure

```text
sixel/
|- main.py
|- requirements.txt
|- config/
|- data/
|- sixel_ai/
|- sixel_core/
|- sixel_dashboard/
|- sixel_db/
|- sixel_mail/
|- sixel_router/
|- sixel_tools/
|- sixel_utils/
`- tests/
```

## Installation

1. Clone repository:

```bash
git clone https://github.com/your-user/sixel.git
cd sixel
```

2. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure secrets locally (never commit them):

```bash
cp config/credentials.example.json config/credentials.json
cp config/token.example.json config/token.json
cp config/sixel-ocr-service-account.example.json config/sixel-ocr-your-key.json
```

5. Set environment variables:

```bash
export OPENAI_API_KEY="your_openai_key"
export GOOGLE_APPLICATION_CREDENTIALS="config/sixel-ocr-your-key.json"
```

## Notes

- This public version contains sample configuration only.
- Real client data, inbox files, and local SQLite runtime files are intentionally excluded.
- See `.gitignore` to understand which private files are blocked from commits.

