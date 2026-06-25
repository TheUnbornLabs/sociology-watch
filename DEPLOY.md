# Deploying Sociology Watch (one-time setup)

This puts your dashboard online at a public link and makes it refresh itself
every day. You only do this once.

## What you need
- A free GitHub account.
- The GitHub CLI (`gh`) — already installed on this machine.

## Step 1 — Log in (the only manual step)
In PowerShell, run:

```powershell
gh auth login
```

Choose **GitHub.com** → **HTTPS** → **Login with a web browser**, then paste the
one-time code it shows you into the browser page it opens. That's it.

## Step 2 — Create the repo and push (automated)
From inside this folder:

```powershell
git init
git add .
git commit -m "Initial Sociology Watch"
gh repo create sociology-watch --public --source=. --remote=origin --push
```

## Step 3 — Turn on GitHub Pages (automated)
```powershell
gh api -X POST repos/:owner/sociology-watch/pages -f "source[branch]=main" -f "source[path]=/"
```

Your site will be live within a minute at:

```
https://<your-github-username>.github.io/sociology-watch/
```

## Step 4 — Kick off the first cloud collection
```powershell
gh workflow run "Daily Sociology Watch collection"
```

After that it runs **automatically every day at 06:30 UTC** and commits fresh
data back, so the link always shows the latest — even when your PC is off.

## Sharing
Just send anyone the `https://<username>.github.io/sociology-watch/` link. It
works on phones; they open or reload it, no install needed.

---

### Notes
- To change the daily time, edit the `cron:` line in
  `.github/workflows/daily.yml` (it's in UTC).
- To run a collection on demand any time: GitHub repo → **Actions** tab →
  **Daily Sociology Watch collection** → **Run workflow**.
