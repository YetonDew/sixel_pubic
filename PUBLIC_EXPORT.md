# Public Repository Checklist

This folder is a sanitized public copy generated from a private working project.

## What was removed

- Credentials and OAuth tokens (`config/credentials.json`, `config/token.json`, service-account keys).
- Private inbox files (`_inbox_raw/`).
- Private storage simulation and client documents (`symulacja_DSM/`).
- Private client list and personal emails (`data/clients.yaml` from private source replaced with a sample).
- Local SQLite data file (`sixel_db/database.sqlite3`).
- Local machine artifacts (`.env`, virtualenvs, caches).

## Before publishing

1. Inspect tracked files:

```bash
git status --short
```

2. Run a quick secret scan:

```bash
rg -n "token|refresh_token|client_secret|private_key|BEGIN PRIVATE KEY|api[_-]?key" --glob '!*.example.json' .
```

3. Initialize git and first commit:

```bash
git init
git add .
git commit -m "Initial public-safe version"
```

4. Create GitHub repo and push (using GitHub CLI):

```bash
gh repo create sixel-public --public --source=. --remote=origin --push
```

If you do not use `gh`, create the empty repo on GitHub UI, then:

```bash
git remote add origin https://github.com/<your-user>/<your-repo>.git
git branch -M main
git push -u origin main
```

## Important security note

The original private tokens/keys were present in the source project. They should be revoked and reissued in Google/OpenAI consoles before any further use.
