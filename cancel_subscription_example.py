"""
דוגמה להוספה ל-server.py הקיים שלכם ב-Render.
דורש: pip install requests

צריך להגדיר את PAYPAL_CLIENT_ID ו-PAYPAL_SECRET כמשתני סביבה ב-Render
(מתוך PayPal Developer Dashboard -> Apps & Credentials).
לעולם אל תשימו את ה-Secret ישירות בקוד או בצד הלקוח.
"""

import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

PAYPAL_CLIENT_ID = os.environ["PAYPAL_CLIENT_ID"]
PAYPAL_SECRET = os.environ["PAYPAL_SECRET"]
PAYPAL_API_BASE = "https://api-m.paypal.com"  # לסביבת בדיקות: https://api-m.sandbox.paypal.com


def get_paypal_access_token():
    resp = requests.post(
        f"{PAYPAL_API_BASE}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        data={"grant_type": "client_credentials"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@app.route("/cancel-subscription", methods=["POST"])
def cancel_subscription():
    data = request.get_json(force=True)
    subscription_id = data.get("subscriptionID")

    if not subscription_id:
        return jsonify({"success": False, "error": "missing subscriptionID"}), 400

    try:
        token = get_paypal_access_token()
        resp = requests.post(
            f"{PAYPAL_API_BASE}/v1/billing/subscriptions/{subscription_id}/cancel",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"reason": "Customer requested cancellation"},
        )
        # PayPal מחזיר 204 No Content בהצלחה
        if resp.status_code == 204:
            return jsonify({"success": True})
        return jsonify({"success": False, "error": resp.text}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run()
