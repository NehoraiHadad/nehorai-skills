---
name: meta-whatsapp-golive
description: >-
  Set up and debug the Meta WhatsApp Cloud API webhook so inbound messages
  reach the bot and get replies. Use this whenever working in the Meta app /
  developers.facebook.com console for WhatsApp, wiring or fixing the webhook
  (callback URL, verify token, App Mode/Live, messages field, WABA
  subscribed_apps), OR diagnosing "the WhatsApp bot got my message but never
  replied" / "no inbound webhook is arriving" / "messages aren't reaching the
  engine". Reach for it even when the user only says "the bot isn't answering
  on WhatsApp" or "check the webhook" — the failure is almost always one of a
  small, known set of config gaps this skill enumerates.
---

# Meta WhatsApp Cloud API — go-live & webhook debugging

The single most important thing to internalize: **inbound WhatsApp delivery
depends on TWO independent config layers, and both must be correct.** Almost
every "the bot doesn't reply" incident is one layer looking fine while the
other is silently wrong. People check the layer they know about (the callback
URL) and miss the other (the per-WABA subscription), then burn an hour.

## The two-layer mental model

1. **App-level webhook config** (Meta app → WhatsApp → Configuration): the
   Callback URL, verify token, and subscribed *fields* (e.g. `messages`). This
   says "here is where webhooks go and which events I want."
2. **Per-WABA subscription** (`GET/POST /{WABA_ID}/subscribed_apps` via Graph
   API): which apps THIS WhatsApp Business Account routes its events to. A WABA
   with a perfect app-level callback still delivers **nothing** if your app is
   not in its `subscribed_apps`. New/test WABAs often list only Meta's internal
   `WA DevX Webhook Events 1P App` (id 2202427980234937) — that powers the
   console's "Test the API" webhook viewer, not your endpoint.

These are configured in different places and neither UI warns you the other is
missing. Always verify both.

## Prerequisites that silently block everything

- **App Mode must be Live**, not Development. Development mode delivers ONLY
  dashboard test webhooks — no real production inbound, even from admins/devs.
  Top of the app console shows the toggle.
- **The callback URL must point at the domain that actually SERVES the app**,
  not a stale alias. Hosting platforms (Vercel) reassign the primary production
  domain; the old alias then answers every request with a **307 redirect** to
  the new one. **Meta does not follow redirects on webhook delivery — a 307 is
  a failed delivery.** So a callback like `old-alias.vercel.app/...` produces
  zero POSTs even though a browser opening that URL "works" (it redirects).

## Setup checklist (ordered)

Run top to bottom; each step depends on the ones above.

1. **App is Live** (App Mode toggle → Live).
2. **Public privacy policy + category** set in App Settings → Basic (required
   to publish to Live).
3. **Determine the real prod domain.** Don't trust notes — verify:
   `curl -s -D - -o /dev/null https://<domain>/<webhook-path>` and confirm it
   is NOT a `307`/`location:` redirect. The domain that returns your app's own
   response (e.g. `403` to a token-less GET) is the live one.
4. **Callback URL** = `https://<live-domain>/<webhook-path>`.
5. **Verify token**: the field's masked dots are a *placeholder*, not the
   stored value — you must (re-)enter the token to enable "Verify and save".
   Beware browser autofill dropping a saved token (often an `EAA…` access
   token) into this field; clear it and enter the real verify token. It must
   equal the app's `WHATSAPP_VERIFY_TOKEN` env var on the live domain.
   - Prove the value before saving:
     `curl "https://<live-domain>/<webhook-path>?hub.mode=subscribe&hub.verify_token=<TOKEN>&hub.challenge=ping"`
     must echo `ping` with `200`. (A saved callback that survives a page reload
     also proves verification succeeded — Meta won't persist an unverified URL.)
6. **Subscribe the `messages` field** in Webhook fields.
7. **Subscribe the app to the WABA**: `POST /{WABA_ID}/subscribed_apps`. Use a
   token with `whatsapp_business_management`. Then GET it back and confirm your
   app id is present. This is the step most likely to be missing.
8. **Channel routing**: your app's channel mapping must map the incoming
   `phone_number_id` to the right tenant/account, and be active.

## Handler status-code contract

A well-behaved webhook handler makes each code map to one cause — mirror this
in yours so the codes are diagnostic:

- **GET** `200` + echoed `hub.challenge` iff `hub.verify_token` matches
  `WHATSAPP_VERIFY_TOKEN`; otherwise `403` (this is why a token-less GET returns
  `403` on the live domain).
- **POST** `401` — bad/missing `WHATSAPP_APP_SECRET`; HMAC over the raw body
  fails and nothing is processed.
- **POST** `200`, no DB row — signature passed but `phone_number_id` didn't map
  to a tenant (log it, e.g. `Unknown phone_number_id: <id>`).
- **POST** `200` + persisted rows — success.

A valid signature is required to reach persistence, so **any persisted inbound
proves `WHATSAPP_APP_SECRET` is correct.**

## Debugging "no bot reply" — ordered playbook

Work cheapest→deepest. **The database is real-time truth; hosting-platform logs
often lag several minutes**, so never conclude "nothing happened" from logs
alone — check the DB first.

1. **DB: was the inbound persisted?** Look for a fresh `whatsapp` conversation
   + inbound message (real `wamid.*` external id).
   - **Row present** → delivery + signature + routing all work. Jump to step 5.
   - **No row** → the message never got processed. Continue.
2. **Did a POST even arrive?** Host logs grouped by status code over the last
   ~15 min (accept lag). Deduce, don't just read: **if the callback URL saved,
   a verify GET succeeded**, so if that 200 isn't in the logs either, the logs
   are simply lagging — fall back to the DB and to Meta-side checks. Map each
   status to its cause via the contract above:
   - **No POST at all** → Meta isn't delivering. Go to step 3.
   - **POST 401** → `WHATSAPP_APP_SECRET` on the live domain is wrong/missing.
     Fix the env var, redeploy.
   - **POST 200 but no DB row** → `phone_number_id` didn't map to a tenant
     (channel mapping mismatch) — grep the "unknown phone_number_id" warn.
3. **Meta isn't delivering — check, in this order:**
   a. App is **Live** (not Development).
   b. Callback URL host is the **live domain**, not a 307-redirecting alias
      (`curl -D -` and look for `location:`).
   c. **WABA `subscribed_apps` includes your app** (the usual culprit). If not,
      subscribe it, then re-test.
   d. `messages` field Subscribed.
4. **Re-test** by sending a real inbound (from an approved test recipient to
   the number), then re-check the DB after a short debounce + pipeline delay.
5. **Inbound persisted but no reply** → the engine/delivery side. Check your
   answer/telemetry log (action, grounding) and the outbound message's delivery
   status. Free-form business replies need an open 24h service window (opened by
   the customer's inbound). A vague inbound legitimately yields a `clarify`, not
   an answer — that's correct, not a bug.

## Tooling

A small companion toolkit makes this fast. Adapt these to your stack (they
assume a Supabase/Postgres backend and a Graph API token stored in a secrets
vault); see `references/example-instance.md` for the shape:

- **recent-activity** — dump the latest conversations / messages / answer logs.
  **Use this as the real-time source of truth** instead of lagging host logs.
- **waba-subscription** `--waba <id> [--subscribe]` — GET (and optionally POST)
  the WABA's `subscribed_apps`. Read the WhatsApp token from your vault and
  never print it.
- **state-check** — list businesses / channel accounts / operators to confirm
  the `phone_number_id` → tenant mapping.

For the env-setup pattern, placeholder IDs, and exact commands, read
`references/example-instance.md`.

## Hard-won gotchas

- **Two layers** (app callback ≠ WABA subscription) — verify both, every time.
- **Redirecting alias** — a 307 kills webhook delivery invisibly; Meta doesn't
  follow redirects. Always target the domain that serves directly.
- **Logs lag; DB doesn't** — diagnose from the DB, corroborate with logs.
- **Verify-token field** — masked = placeholder; autofill pollutes it.
- **A callback that persists across reload** proves verification passed, even
  when the confirming GET isn't visible in lagging logs.
- **Secrets stay out of chat/files** — reference `WHATSAPP_VERIFY_TOKEN` /
  `WHATSAPP_APP_SECRET` by name; pipe tokens from a vault/CLI, never display
  them. Persistent webhook/subscription changes need explicit sign-off first.
