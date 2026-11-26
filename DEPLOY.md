# Empire Tweaks – how to put the new site live

The server (`server.py`) now serves **both** the website (`site/`) and the API.
Everything lives at one address: https://empire-tweaks.onrender.com

## 1. Render → Environment (one time)
Render → your service → **Environment** → add:

| Key | Value |
|---|---|
| `PAYPAL_CLIENT_ID` | Live Client ID from developer.paypal.com → Apps & Credentials |
| `PAYPAL_SECRET` | the **NEW** secret (rotate the old one – it was in GitHub) |
| `PAYPAL_PLAN_ID` | `P-37F11585C4970333YNKJNTIQ` (or your plan id) |
| `FIREBASE_SERVICE_ACCOUNT` | the whole content of `serviceAccountKey.json` (Firebase → Project settings → Service accounts → Generate new private key) |
| `PRICE_LABEL` | `$7` – must match the price of the PayPal plan |
| `APP_VERSION` | `3.0.0` – raise it when you release a new exe, the app will show "update available" |
| `APP_DOWNLOAD_URL` | link to `EmpireTweaks.exe` (see step 3) |

Start command: `python server.py` (or `gunicorn server:app`).

## 2. Firebase (one time)
Firebase console → Authentication → Settings → **Authorized domains** → add `empire-tweaks.onrender.com`
(otherwise "Continue with Google" won't work on the site).

## 3. Put the exe online
GitHub → your repo → **Releases** → *Draft a new release* → tag `v3.0.0` → upload `dist\EmpireTweaks.exe` → Publish.
The default `APP_DOWNLOAD_URL` already points to `.../releases/latest/download/EmpireTweaks.exe`.

## 4. Upload the code
From this folder:
```
git add -A
git commit -m "New website + secure account API"
git push
```
Render deploys automatically after the push.

## How the app and the site connect
* Customer buys PRO on the site (PayPal subscription) → the server checks it with PayPal and gives the account a license key.
* In the app: Settings & Account → **Sign in with your Empire Tweaks account** → the browser opens, the customer
  clicks **Connect this PC** → PRO unlocks in the app. (They can also paste the license key.)
* The app re-checks once a day. If the subscription is cancelled, PRO stays until the paid month ends, then locks.
* Old customers from the previous site: when they sign in on the new site from the same browser, their subscription
  is attached automatically. Otherwise: Account → "Already paid but PRO is not active?" → paste the PayPal `I-...` id.
