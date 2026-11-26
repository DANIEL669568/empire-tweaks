"""
Empire Tweaks – website + API server (runs on Render).

Serves the website from ./site and the API under /api.
ALL secrets come from environment variables (Render -> Environment):
    PAYPAL_CLIENT_ID          PayPal live client id
    PAYPAL_SECRET             PayPal live secret   (NEVER put it in code / GitHub)
    PAYPAL_PLAN_ID            subscription plan id (P-...)
    FIREBASE_SERVICE_ACCOUNT  the whole serviceAccountKey.json content (one line)
optional:
    PRICE_LABEL               shown on the site, default "$7"
    PRICE_PERIOD              default "month"
    APP_VERSION               latest app version, default "3.0.0"
    APP_DOWNLOAD_URL          direct link to EmpireTweaks.exe
    PAYPAL_BASE               default live: https://api-m.paypal.com
"""
import base64
import json
import os
import secrets
import string
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(ROOT, "site")

app = Flask(__name__, static_folder=None)
CORS(app, resources={r"/api/*": {"origins": "*"}, r"/verify-license": {"origins": "*"}})

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")
PAYPAL_PLAN_ID = os.environ.get("PAYPAL_PLAN_ID", "P-37F11585C4970333YNKJNTIQ")
PAYPAL_BASE = os.environ.get("PAYPAL_BASE", "https://api-m.paypal.com")
PRICE_LABEL = os.environ.get("PRICE_LABEL", "$7")
PRICE_PERIOD = os.environ.get("PRICE_PERIOD", "month")
APP_VERSION = os.environ.get("APP_VERSION", "3.0.0")
APP_DOWNLOAD_URL = os.environ.get(
    "APP_DOWNLOAD_URL", "https://github.com/DANIEL669568/empire-tweaks/releases/latest/download/EmpireTweaks.exe")
RECHECK_SECONDS = 6 * 3600

# ─────────────────────────── Firebase ───────────────────────────
import firebase_admin
from firebase_admin import auth as fb_auth, credentials, firestore

db = None
try:
    sa = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    cred = credentials.Certificate(json.loads(sa)) if sa else credentials.Certificate(os.path.join(ROOT, "serviceAccountKey.json"))
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("[+] Firebase connected")
except Exception as e:  # noqa
    print(f"[!] Firebase NOT connected: {e}")


def err(msg, code=400):
    return jsonify({"success": False, "message": msg}), code


def current_user():
    """Verify the Firebase ID token from 'Authorization: Bearer <token>'. Returns decoded token or None."""
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer ") or db is None:
        return None
    try:
        return fb_auth.verify_id_token(h[7:])
    except Exception:
        return None


# Owner accounts: PRO forever, no payment. Override with env OWNER_EMAILS="a@x.com,b@y.com".
OWNER_EMAILS = {e.strip().lower() for e in os.environ.get("OWNER_EMAILS", "danielnamdar83@gmail.com").split(",") if e.strip()}


def is_owner(email, verified=True):
    return bool(verified) and (email or "").strip().lower() in OWNER_EMAILS


def make_owner(uid, data, email):
    """Give the owner account PRO + a license key, and remember it so the app's key check also sees it."""
    changed = not data.get("owner") or not data.get("license_key")
    data.update(owner=True, pro=True, status="OWNER", paid_until=0)
    data.setdefault("email", email)
    if not data.get("license_key"):
        data["license_key"] = new_license_key()
    if changed and db is not None:
        user_doc(uid).set(data, merge=True)
        db.collection("licenses").document(data["license_key"]).set(
            {"uid": uid, "email": data.get("email") or email, "active": True}, merge=True)
    return data


def new_license_key():
    chars = string.ascii_uppercase + string.digits
    return "ET-" + "-".join("".join(secrets.choice(chars) for _ in range(4)) for _ in range(3))


# ─────────────────────────── PayPal ───────────────────────────
_token = {"value": None, "exp": 0}
_token_lock = threading.Lock()


def paypal_token():
    with _token_lock:
        if _token["value"] and time.time() < _token["exp"] - 60:
            return _token["value"]
        basic = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_SECRET}".encode()).decode()
        r = requests.post(f"{PAYPAL_BASE}/v1/oauth2/token", timeout=20,
                          headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
                          data="grant_type=client_credentials")
        r.raise_for_status()
        d = r.json()
        _token.update(value=d["access_token"], exp=time.time() + int(d.get("expires_in", 3000)))
        return _token["value"]


def paypal_subscription(sub_id: str) -> dict:
    r = requests.get(f"{PAYPAL_BASE}/v1/billing/subscriptions/{sub_id}", timeout=20,
                     headers={"Authorization": f"Bearer {paypal_token()}"})
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()


def _iso_to_ts(s):
    if not s:
        return 0
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def sub_state(sub: dict) -> dict:
    """Translate a PayPal subscription into {status, pro, paid_until}."""
    status = sub.get("status", "UNKNOWN")
    nbt = _iso_to_ts((sub.get("billing_info") or {}).get("next_billing_time"))
    last = _iso_to_ts(((sub.get("billing_info") or {}).get("last_payment") or {}).get("time"))
    paid_until = nbt or (last + 31 * 86400 if last else 0)
    if status in ("ACTIVE", "APPROVED"):
        pro = True
    elif status in ("CANCELLED", "SUSPENDED"):
        pro = paid_until > time.time()          # keeps PRO until the paid month ends
    else:
        pro = False
    return {"status": status, "pro": pro, "paid_until": paid_until}


# ─────────────────────────── Accounts ───────────────────────────
def user_doc(uid):
    return db.collection("users").document(uid)


def refresh_user(uid: str, data: dict, force=False) -> dict:
    """Re-check the PayPal subscription if it's time; returns the updated user data."""
    if data.get("owner"):
        data.update(pro=True, status="OWNER")
        return data
    sub_id = data.get("subscription_id")
    if not sub_id or not PAYPAL_SECRET:
        return data
    if not force and time.time() - data.get("checked_at", 0) < RECHECK_SECONDS:
        # still expire on time even without re-checking
        if data.get("pro") and data.get("status") in ("CANCELLED", "SUSPENDED") and data.get("paid_until", 0) < time.time():
            data["pro"] = False
        return data
    try:
        st = sub_state(paypal_subscription(sub_id))
    except Exception as e:  # PayPal down – keep previous state
        print("[!] PayPal check failed:", e)
        return data
    data.update(pro=st["pro"], status=st["status"], paid_until=st["paid_until"], checked_at=time.time())
    user_doc(uid).set(data, merge=True)
    if data.get("license_key"):
        db.collection("licenses").document(data["license_key"]).set({"active": st["pro"]}, merge=True)
    return data


def public_account(uid, data, email=""):
    return {
        "success": True,
        "email": data.get("email") or email,
        "pro": bool(data.get("pro")),
        "status": data.get("status", "NONE"),
        "license_key": data.get("license_key", ""),
        "paid_until": data.get("paid_until", 0),
        "subscription_id": data.get("subscription_id", ""),
    }


@app.after_request
def cache_headers(resp):
    p = request.path
    if p.startswith(("/vendor/", "/fonts/", "/img/")) or p == "/favicon.ico":
        resp.headers["Cache-Control"] = "public, max-age=86400"
    elif not p.startswith("/api/") and p != "/verify-license":
        resp.headers["Cache-Control"] = "no-cache"   # always check for a new version of the page
    return resp


# ─────────────────────────── Website ───────────────────────────
@app.route("/")
def index():
    return send_from_directory(SITE_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    if path.startswith("api/"):
        return err("Not found", 404)
    full = os.path.join(SITE_DIR, path)
    if os.path.isfile(full):
        return send_from_directory(SITE_DIR, path)
    return send_from_directory(SITE_DIR, "index.html")


# ─────────────────────────── API ───────────────────────────
@app.get("/api/config")
def api_config():
    return jsonify({
        "paypal_client_id": PAYPAL_CLIENT_ID,
        "plan_id": PAYPAL_PLAN_ID,
        "price": PRICE_LABEL,
        "period": PRICE_PERIOD,
        "app_version": APP_VERSION,
        "download_url": APP_DOWNLOAD_URL,
    })


@app.get("/api/app/version")
def api_version():
    return jsonify({"version": APP_VERSION, "download_url": APP_DOWNLOAD_URL})


@app.get("/api/account")
def api_account():
    u = current_user()
    if not u:
        return err("Please sign in again.", 401)
    snap = user_doc(u["uid"]).get()
    data = snap.to_dict() if snap.exists else {"email": u.get("email", "")}
    if is_owner(u.get("email"), u.get("email_verified")):
        data = make_owner(u["uid"], data, u.get("email", ""))
    data = refresh_user(u["uid"], data)
    return jsonify(public_account(u["uid"], data, u.get("email", "")))


@app.post("/api/subscription/activate")
def api_activate():
    """Called by the site right after PayPal approves (or to restore an old subscription)."""
    u = current_user()
    if not u:
        return err("Please sign in again.", 401)
    sub_id = (request.get_json(silent=True) or {}).get("subscriptionID", "").strip()
    if not sub_id.startswith("I-"):
        return err("That doesn't look like a PayPal subscription ID (it starts with I-).")
    # one subscription = one account
    owner = db.collection("subscriptions").document(sub_id).get()
    if owner.exists and owner.to_dict().get("uid") != u["uid"]:
        return err("This subscription is already linked to another account.", 409)
    try:
        sub = paypal_subscription(sub_id)
    except Exception as e:  # noqa
        return err(f"Could not reach PayPal: {e}", 502)
    if not sub:
        return err("Subscription not found at PayPal.", 404)
    if sub.get("plan_id") != PAYPAL_PLAN_ID:
        return err("This subscription is for a different product.", 400)
    st = sub_state(sub)
    ref = user_doc(u["uid"])
    snap = ref.get()
    data = snap.to_dict() if snap.exists else {}
    key = data.get("license_key") or new_license_key()
    data.update(email=u.get("email", ""), subscription_id=sub_id, license_key=key, pro=st["pro"],
                status=st["status"], paid_until=st["paid_until"], checked_at=time.time(),
                activated_at=data.get("activated_at", time.time()))
    ref.set(data, merge=True)
    db.collection("subscriptions").document(sub_id).set({"uid": u["uid"]})
    db.collection("licenses").document(key).set({"uid": u["uid"], "email": data["email"], "active": st["pro"]})
    print(f"[+] PRO {data['email']} {sub_id} -> {key} ({st['status']})")
    return jsonify(public_account(u["uid"], data))


@app.post("/api/subscription/cancel")
def api_cancel():
    u = current_user()
    if not u:
        return err("Please sign in again.", 401)
    ref = user_doc(u["uid"])
    snap = ref.get()
    data = snap.to_dict() if snap.exists else {}
    sub_id = data.get("subscription_id")
    if not sub_id:
        return err("No active subscription on this account.", 404)
    r = requests.post(f"{PAYPAL_BASE}/v1/billing/subscriptions/{sub_id}/cancel", timeout=20,
                      headers={"Authorization": f"Bearer {paypal_token()}", "Content-Type": "application/json"},
                      json={"reason": "Customer cancelled from empire-tweaks website"})
    if r.status_code not in (204, 200, 422):   # 422 = already cancelled
        return err("PayPal refused the cancellation. Try again or cancel in your PayPal account.", 502)
    data = refresh_user(u["uid"], data, force=True)
    return jsonify(public_account(u["uid"], data))


@app.post("/verify-license")
def verify_license():
    """Used by the desktop app. Body: {"key": "ET-XXXX-XXXX-XXXX"}"""
    key = ((request.get_json(silent=True) or {}).get("key") or "").strip().upper()
    if not key or db is None:
        return err("Invalid license key.", 404)
    lic = db.collection("licenses").document(key).get()
    if not lic.exists:
        return err("Invalid license key.", 404)
    uid = lic.to_dict().get("uid")
    if not uid:   # very old one-time licenses
        l = lic.to_dict()
        return jsonify({"success": bool(l.get("active")), "pro": bool(l.get("active")), "email": l.get("email", ""),
                        "paid_until": 0, "message": "" if l.get("active") else "License inactive."})
    snap = user_doc(uid).get()
    data = refresh_user(uid, snap.to_dict() if snap.exists else {})
    # success = the key is valid (account linked). "pro" says whether PRO is unlocked right now.
    return jsonify({"success": True, "pro": bool(data.get("pro")), "email": data.get("email", ""),
                    "paid_until": data.get("paid_until", 0), "status": data.get("status", "NONE"),
                    "message": "" if data.get("pro") else "No active PRO subscription on this account."})


# ───── Connect the desktop app to a website account (device-code flow) ─────
_links = {}            # code -> {secret, created, uid}
_links_lock = threading.Lock()


def _clean_links():
    now = time.time()
    for c in [c for c, v in _links.items() if now - v["created"] > 600]:
        _links.pop(c, None)


@app.post("/api/app/link/start")
def link_start():
    with _links_lock:
        _clean_links()
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
        code = code[:4] + "-" + code[4:]
        sec = secrets.token_urlsafe(24)
        _links[code] = {"secret": sec, "created": time.time(), "uid": None}
    return jsonify({"code": code, "secret": sec, "expires_in": 600})


@app.post("/api/app/link/confirm")
def link_confirm():
    u = current_user()
    if not u:
        return err("Please sign in again.", 401)
    code = ((request.get_json(silent=True) or {}).get("code") or "").strip().upper()
    with _links_lock:
        _clean_links()
        if code not in _links:
            return err("This code expired. Click 'Sign in' in the app again.", 404)
        _links[code]["uid"] = u["uid"]
        _links[code]["email"] = u.get("email", "")
        _links[code]["verified"] = bool(u.get("email_verified"))
    return jsonify({"success": True})


@app.post("/api/app/link/poll")
def link_poll():
    body = request.get_json(silent=True) or {}
    code, sec = (body.get("code") or "").upper(), body.get("secret") or ""
    with _links_lock:
        l = _links.get(code)
        if not l or not secrets.compare_digest(l["secret"], sec):
            return err("expired", 404)
        if not l["uid"]:
            return jsonify({"success": False, "pending": True})
        _links.pop(code, None)
        uid, email, verified = l["uid"], l.get("email", ""), l.get("verified", False)
    return jsonify(app_account(uid, email, verified))


def app_account(uid, email, verified):
    """Account data for the desktop app – makes sure the account has a license key."""
    ref = user_doc(uid)
    snap = ref.get()
    data = snap.to_dict() if snap.exists else {"email": email}
    if is_owner(email, verified):
        data = make_owner(uid, data, email)
    if not data.get("license_key"):
        # every account gets a key so the app can stay linked; it unlocks PRO only while subscribed
        data["license_key"] = new_license_key()
        data.setdefault("email", email)
        ref.set(data, merge=True)
        db.collection("licenses").document(data["license_key"]).set({"uid": uid, "email": data["email"],
                                                                      "active": bool(data.get("pro"))})
    data = refresh_user(uid, data)
    return public_account(uid, data, email)


@app.post("/api/app/login")
def app_login():
    """The desktop app signs in directly (email + password via Firebase) and sends the ID token here."""
    u = current_user()
    if not u:
        return err("Sign-in failed. Check your email and password.", 401)
    return jsonify(app_account(u["uid"], u.get("email", ""), u.get("email_verified")))


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "firebase": db is not None, "paypal": bool(PAYPAL_SECRET)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
