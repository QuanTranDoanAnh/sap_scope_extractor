# Deployment Guide — Streamlit Community Cloud

This guide takes the **deployment build** of the SAP Scope Item Extractor
and gets it running at a shareable URL for your 6-10 person team. Total
setup time: about 15 minutes the first time. Free, no credit card.

## What you'll end up with

- A URL like `https://sap-scope-extractor-fpt.streamlit.app/`
- A team-wide shared password (change anytime via dashboard)
- Auto-deploys on every git push to your repo
- 1 GB RAM, generous enough for hundreds of scope items
- Sleeps after ~15 min idle, wakes in ~30 sec when someone visits

## Prerequisites

- A GitHub account (personal is fine)
- A Google account (any Gmail) — needed only to log into Streamlit Cloud,
  not for end users of your app

## Step 1 — Get the code into a GitHub repo

The repo can be **public**. The code is generic and contains no secrets,
data, or customer information. The shared password lives only in
Streamlit Cloud's secrets store, never in the repo.

```bash
# From inside the unzipped sap_scope_extractor_v3_deploy/ folder:
git init
git add .
git commit -m "Initial commit"

# Create a new repo on github.com (e.g. 'sap-scope-extractor'),
# then push:
git branch -M main
git remote add origin https://github.com/<your-username>/sap-scope-extractor.git
git push -u origin main
```

Verify on GitHub that `.streamlit/secrets.toml` is **not** in the
uploaded files (it's git-ignored). You should see `secrets.toml.example`
but not `secrets.toml`.

## Step 2 — Sign in to Streamlit Community Cloud

Go to https://share.streamlit.io and sign in with your Google account.
First-time users may need to authorize Streamlit to read your GitHub
repos — click "Authorize" when prompted.

## Step 3 — Deploy the app

1. Click **"Create app"** (top-right) → "Deploy a public app from GitHub"
2. Fill in:
   - **Repository**: `<your-username>/sap-scope-extractor`
   - **Branch**: `main`
   - **Main file path**: `app.py`
   - **App URL**: pick a memorable subdomain, e.g. `sap-scope-fpt`
3. **Before clicking Deploy**, click **"Advanced settings"** → **"Secrets"**
   and paste:
   ```toml
   APP_PASSWORD = "pick-a-strong-team-password-here"
   ```
4. Click **Deploy**.

Streamlit will pull the repo, install dependencies from
`requirements.txt`, and start the app. First deploy takes 2-3 minutes.
Subsequent re-deploys (after git push) take ~30 seconds.

## Step 4 — Share with your team

Send teammates:
- The app URL
- The shared password (use Slack DM, FPT Teams, or whatever your team
  uses for credentials — not email)
- A one-line usage hint:
  > *"ZIP up your `TestScripts` folder, drop it in, click Extract,
  > download the Markdown."*

## Operational notes

### Updating the app

Edit code locally → `git push` → Streamlit auto-redeploys within ~30 sec.
No manual steps needed.

### Changing the password

Streamlit Cloud dashboard → your app → **Settings** → **Secrets** →
update `APP_PASSWORD` → save. Takes effect on next user sign-in (no
restart needed).

### Looking at logs

Dashboard → your app → **Manage app** → log pane on the right shows
recent activity and any errors. Useful when debugging extraction
failures on specific files.

### Wake-from-sleep

After 15 minutes of inactivity the app sleeps. The first user to visit
sees a "Yes, get this app back up!" button — they click it, wait
~30 seconds, and the app boots. Subsequent users in the next 15 min
see no delay.

For a tool used a few times per week this is fine. If it becomes
annoying, options:
- Streamlit Cloud Teams plan (paid, no sleep)
- Move to Render/Railway ($5-7/month, no sleep)
- A simple cron job that pings the app every 10 min (technically
  against Streamlit Cloud's spirit but commonly done)

### Resource limits to be aware of

- 1 GB RAM, 1 CPU. Your 633-scope-item run extracted in well under
  a minute on a workstation; on the cloud expect 2-3 minutes due to
  the smaller CPU.
- 200 MB upload limit (configured in `.streamlit/config.toml`). A full
  TestScripts folder zipped is typically 30-80 MB, so plenty of headroom.
- 2 concurrent users is well within the free tier's capacity.

## When to migrate off Streamlit Cloud

Stay on it as long as:
- Internal team only
- No customer-confidential data uploaded (data uploaded by users is
  per-session and ephemeral, but a misconfigured app could leak in
  edge cases)

Migrate to Render/Railway/Fly.io ($5-10/mo) or FPT internal hosting
when:
- The team grows past ~25 active users
- You start using it in customer-facing engagements
- The 30-second cold start becomes operationally annoying
- You want proper SSO instead of a shared password

## Troubleshooting

**"Module not found" error on first deploy** — check `requirements.txt`
is at the repo root. Python version on Streamlit Cloud defaults to 3.11
which works fine for this app.

**"App is over its resource limits"** — almost always means a single
user uploaded a massive ZIP (>500 MB) or the extraction is somehow
allocating too much memory. The app processes files one at a time, so
this is rare. If it happens, ask the user to ZIP only the
TestScripts folder, not the entire SAP package.

**Password gate appears every time even after signing in** — Streamlit
session state is per-browser-tab. Each new tab requires re-signing in.
This is by design and not really fixable without a more sophisticated
auth setup.

**Multiple people get logged in/out unexpectedly** — shouldn't happen;
each user has their own session. If it does, check that you haven't
accidentally enabled some shared-state debugging code.

## File checklist

Your repo root should contain exactly these files:

```
.
├── .gitignore                  ← keeps secrets.toml out of git
├── .streamlit/
│   ├── config.toml             ← server settings
│   └── secrets.toml.example    ← template only; real one is in cloud dashboard
├── app.py                      ← Streamlit UI (with password gate)
├── docx_parser.py              ← extraction logic
├── markdown_writer.py          ← output rendering
├── requirements.txt            ← streamlit, python-docx, pandas
└── README.md                   ← user-facing documentation
```

If `.streamlit/secrets.toml` (without the `.example`) exists in your
local folder, that's fine — `.gitignore` keeps it from being pushed.
You only need it locally if you want to test the password gate before
deploying.
