# Credentials

Reference for every credential Aegis uses. **No real values live here**: this file is tracked
by git. Real values go in `.env` (gitignored). Copy `.env.example` to `.env` and fill it in.

## Dashboard accounts

| Account | Username | Password source | Role |
|---|---|---|---|
| First admin | `ADMIN_USERNAME` (default `admin`) | `ADMIN_PASSWORD` in `.env`; if unset, generated and printed once | admin |

- Created by `scripts/bootstrap_admin.py` or `scripts/seed_demo.py`, only when no users exist.
- There is no default password. Use 10+ characters. Change it after first login.
- Roles: `admin` (all), `supervisor` (enroll/edit faces, review alerts), `operator`, `viewer`.
- Lost the admin password? Reset it with the admin reset helper noted in the run docs, or
  delete the user row and re-run `scripts/bootstrap_admin.py`.

## Secrets (`.env`)

| Variable | Purpose | Notes |
|---|---|---|
| `SECRET_KEY` | Signs JWT login tokens | Backend refuses to start with the default. Generate: `openssl rand -hex 32` |
| `INTERNAL_API_KEY` | Pipeline → backend alert dispatch | **Must match** between backend and pipeline. Generate: `openssl rand -hex 24` |
| `ENCRYPTION_KEY`, `ENCRYPTION_SALT` | Encrypts stored sensitive data | Changing them makes old encrypted data unreadable |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Database login | Also used by `DATABASE_URL` |
| `REDIS_URL` | Cache/queue | Include password if Redis requires one |

## Integrations (optional)

| Variable | Purpose |
|---|---|
| `LAW_ENFORCEMENT_WEBHOOK`, `EMERGENCY_WEBHOOK`, `SECURITY_TEAM_WEBHOOK` | Alert webhooks. Criminal alerts are held until an operator confirms |
| `SMS_WEBHOOK`, `CAD_WEBHOOK`, `RADIO_WEBHOOK` | Extra notification channels |
| `RTSP_GATE_1`, `RTSP_PARKING_1`, `RTSP_LOBBY_1` | Camera URLs. Often contain `user:pass@host`, so treat as secrets |

## Rules

1. Never commit `.env`, camera URLs with passwords, or webhook URLs.
2. Rotate `SECRET_KEY` and `INTERNAL_API_KEY` if exposed. Rotating `SECRET_KEY` logs everyone out.
3. Use a different value per environment (dev, staging, production).
4. Share secrets through a password manager, not chat or email.

## Quick setup

```bash
cp .env.example .env
sed -i '' "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env              # macOS
sed -i '' "s/^INTERNAL_API_KEY=.*/INTERNAL_API_KEY=$(openssl rand -hex 24)/" .env
echo "ADMIN_PASSWORD=<choose-a-strong-password>" >> .env
```
