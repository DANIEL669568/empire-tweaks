import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import secrets
import string
import base64

app = Flask(__name__)
CORS(app, origins=["*"], supports_credentials=True)

# ══ PAYPAL CONFIG ══════════════════════════════════════════════
PAYPAL_CLIENT_ID = "BAAZi4IqjVn0fgavoJLIKsFpqpiX9hEphBKpQ-6b6QE3TCy_cY7Ts9FCXI52e-KyMca6WN1a-ZtCT7FvSA"
PAYPAL_SECRET    = "ECZKmIwSsTNAXxVEh2EIMizy6Ifk8EZsOoU5HSegPpB0xB6Dudv_jfjzcfGmOiMgqi7w7FeCrR30M0OI"
PAYPAL_BASE      = "https://api-m.paypal.com"  # Live

# ══ FIREBASE ADMIN ══════════════════════════════════════════════
import firebase_admin
from firebase_admin import credentials, firestore

try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    FIREBASE_OK = True
    print("[+] Firebase connected")
except Exception as e:
    print(f"[!] Firebase not connected: {e}")
    FIREBASE_OK = False
    db = None

activated_licenses = {}

def generate_license_key():
    chars = string.ascii_uppercase + string.digits
    parts = ["".join(secrets.choice(chars) for _ in range(4)) for _ in range(3)]
    return "ET-" + "-".join(parts)

def get_paypal_token():
    credentials_str = f"{PAYPAL_CLIENT_ID}:{PAYPAL_SECRET}"
    encoded = base64.b64encode(credentials_str.encode()).decode()
    res = requests.post(
        f"{PAYPAL_BASE}/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data="grant_type=client_credentials"
    )
    return res.json().get("access_token")


@app.route("/create-paypal-order", methods=["POST"])
def create_paypal_order():
    try:
        data = request.json
        email = data.get("email", "")
        token = get_paypal_token()

        res = requests.post(
            f"{PAYPAL_BASE}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {
                        "currency_code": "USD",
                        "value": "7.00"
                    },
                    "description": "Empire Tweaks Pro — Lifetime License",
                    "custom_id": email
                }]
            }
        )
        order = res.json()
        return jsonify({"orderID": order["id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/capture-paypal-order", methods=["POST"])
def capture_paypal_order():
    try:
        data = request.json
        order_id = data.get("orderID", "").strip()
        email = data.get("email", "").strip().lower()

        if not order_id:
            return jsonify({"success": False, "message": "Missing order ID."}), 400

        # בדוק שלא השתמשנו בorder הזה כבר
        if FIREBASE_OK:
            already = db.collection("used_payments").document(order_id).get()
            if already.exists:
                return jsonify({"success": False, "message": "Payment already used."}), 402

        token = get_paypal_token()

        # Capture התשלום
        res = requests.post(
            f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        result = res.json()

        if result.get("status") != "COMPLETED":
            return jsonify({"success": False, "message": f"Payment not completed: {result.get('status')}"}), 402

        # צור license key
        license_key = generate_license_key()

        if FIREBASE_OK:
            db.collection("used_payments").document(order_id).set({"used": True})
            db.collection("licenses").document(license_key).set({
                "email": email,
                "order_id": order_id,
                "active": True
            })
            db.collection("users").document(email).set({
                "pro": True,
                "license_key": license_key,
                "order_id": order_id
            })
        else:
            activated_licenses[license_key] = {
                "email": email,
                "order_id": order_id,
                "active": True
            }

        print(f"[+] NEW LICENSE: {license_key} | {email}")
        return jsonify({"success": True, "licenseKey": license_key})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/check-pro", methods=["POST"])
def check_pro():
    try:
        data = request.json
        email = data.get("email", "").strip().lower()
        if not email:
            return jsonify({"pro": False}), 400
        if FIREBASE_OK:
            doc = db.collection("users").document(email).get()
            if doc.exists and doc.to_dict().get("pro"):
                return jsonify({"pro": True})
        return jsonify({"pro": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/verify-license", methods=["POST"])
def verify_license():
    try:
        data = request.json
        key = data.get("key", "").strip()
        if FIREBASE_OK:
            doc = db.collection("licenses").document(key).get()
            if not doc.exists:
                return jsonify({"success": False, "message": "Invalid license key."}), 404
            lic = doc.to_dict()
        else:
            if key not in activated_licenses:
                return jsonify({"success": False, "message": "Invalid license key."}), 404
            lic = activated_licenses[key]
        if not lic.get("active"):
            return jsonify({"success": False, "message": "License inactive."}), 403
        return jsonify({"success": True, "email": lic["email"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    print("Empire Tweaks Server — http://localhost:5000")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))