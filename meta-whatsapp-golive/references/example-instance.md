# Example instance — values & commands (fill in your own)

A template for the concrete values and commands this skill needs. Replace the
`<PLACEHOLDERS>` with your deployment's values. **Keep secret VALUES out of this
file** — reference the verify token and access tokens by env-var name / vault,
never paste them.

## Identifiers (non-secret) — fill these in

| Thing | Value |
|---|---|
| Meta App (App ID) | `<APP_ID>` |
| Business Portfolio ID | `<PORTFOLIO_ID>` |
| WABA ID | `<WABA_ID>` |
| Phone Number ID | `<PHONE_NUMBER_ID>` |
| Meta internal 1P webhook app (expected in subscribed_apps) | `2202427980234937` "WA DevX Webhook Events 1P App" |
| Live prod domain | `<live-domain>` (⚠️ watch for a stale alias that 307-redirects to it) |
| Webhook path | `<webhook-path>` (e.g. `/api/webhooks/whatsapp`) |
| Hosting project | `<HOSTING_PROJECT_ID>` (e.g. Vercel project) |
| DB project ref | `<DB_PROJECT_REF>` (e.g. Supabase project) |
| Tenant / business id | `<BUSINESS_ID>` |

Secrets (by name only): `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` (hosting
env); the permanent WhatsApp access token belongs in a secrets vault (e.g.
Supabase Vault, referenced indirectly — never in a DB row or this file).

## Point ops scripts at cloud prod (example, PowerShell + Supabase CLI)

The service-role key is piped from the CLI, never displayed:

```powershell
$keys = npx supabase projects api-keys --project-ref <DB_PROJECT_REF> --output-format json | ConvertFrom-Json
$svc = ($keys.keys | Where-Object { $_.name -eq 'service_role' }).api_key
$env:NEXT_PUBLIC_SUPABASE_URL='https://<DB_PROJECT_REF>.supabase.co'
$env:SUPABASE_SERVICE_ROLE_KEY=$svc
# then: npx tsx scripts/<ops-script>.ts ...
```

## Common commands

```bash
# Is the callback domain live (not a redirect)? Expect 403 (token-less GET) on
# the live domain; a 307 with a location: header means it's a stale alias.
curl -s -D - -o /dev/null https://<live-domain>/<webhook-path>

# Prove the verify token matches the live env before saving in Meta.
# Substitute the real token from your hosting env WHATSAPP_VERIFY_TOKEN (don't commit it):
curl "https://<live-domain>/<webhook-path>?hub.mode=subscribe&hub.verify_token=<WHATSAPP_VERIFY_TOKEN>&hub.challenge=ping"   # -> echoes "ping"

# Real-time truth: did an inbound reach the engine and get a reply?
npx tsx scripts/prod-recent-activity.ts

# Check / fix the WABA -> app subscription (the usual missing link):
npx tsx scripts/prod-waba-subscription.ts --waba <WABA_ID>            # GET
npx tsx scripts/prod-waba-subscription.ts --waba <WABA_ID> --subscribe # POST
```

### Sketch: WABA subscribed_apps check/fix

Resolve the WhatsApp access token from your vault (never print it), then call
the Graph API:

```
GET  https://graph.facebook.com/v25.0/<WABA_ID>/subscribed_apps   Authorization: Bearer <token>
POST https://graph.facebook.com/v25.0/<WABA_ID>/subscribed_apps   Authorization: Bearer <token>   # subscribes the token's app
```

The token's app is the one subscribed on POST — use a token from the app you
want to receive webhooks, with the `whatsapp_business_management` scope.

## Hosting runtime logs (lagging — corroborate, don't rely on)

Scope queries to the current production deployment or use a status-code grouping
for speed; broad unscoped queries time out. Ingestion can lag several minutes —
the DB is authoritative in real time.

## Test flow

A Meta test number only messages ≤5 approved recipients. To generate a real
inbound, send FROM an approved recipient's WhatsApp TO the number, then poll
your recent-activity script after a short debounce + pipeline delay. A grounded
question that matches an indexed source yields an answer; a vague or uncovered
question correctly yields a `clarify` (no hallucination).

## Common prod nuances

- If provisioning defaults a bot to disabled, enable it per tenant or the engine
  short-circuits ("bot paused").
- On Vercel, AI Gateway auth is automatic OIDC at runtime — no API key env var
  needed in prod.
