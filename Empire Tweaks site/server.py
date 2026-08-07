from flask import Flask, request, jsonify
from flask_cors import CORS
import stripe
import secrets
import string

app = Flask(__name__)
CORS(app)

stripe.api_key = "sk_test_51TJvw2LPNXqByMY3Yi7d28qGnOU4MldIrIxGMWYZHK6A5Mpu9eeKQKfIBZbzLBXJfjSCJ0TZy29TsbcLPuL8RDaz00UDQ4fPQa"

activated_licenses = {}
used_payment_intents = set()

def generate_license_key():
    chars = string.ascii_uppercase + string.digits
    parts = ["".join(secrets.choice(chars) for _ in range(4)) for _ in range(3)]
    return "ET-" + "-".join(parts)


@app.route("/create-payment-intent", methods=["POST"])
def create_payment_intent():
    try:
        data = request.json
        intent = stripe.PaymentIntent.create(
            amount=700,
            currency="usd",
            metadata={"email": data.get("email", "")}
        )
        return jsonify({"clientSecret": intent.client_secret})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/confirm-payment", methods=["POST"])
def confirm_payment():
    try:
        data = request.json
        payment_intent_id = data.get("paymentIntentId", "").strip()
        email = data.get("email", "").strip()

        if not payment_intent_id:
            return jsonify({"success": False, "message": "Missing payment ID."}), 400

        # בדוק שלא השתמשנו בתשלום הזה כבר
        if payment_intent_id in used_payment_intents:
            return jsonify({"success": False, "message": "Payment already used."}), 402

        # בדוק מול Stripe
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)

        if intent.status != "succeeded":
            return jsonify({"success": False, "message": f"Payment not completed ({intent.status})."}), 402

        if intent.amount != 700 or intent.currency != "usd":
            return jsonify({"success": False, "message": "Invalid payment amount."}), 402

        # בדוק refund
        charges = intent.get("charges", {}).get("data", [])
        if charges:
            charge = charges[0]
            if charge.get("refunded") or charge.get("disputed"):
                return jsonify({"success": False, "message": "Payment was refunded."}), 402

        # הכל תקין — צור license
        used_payment_intents.add(payment_intent_id)
        license_key = generate_license_key()
        activated_licenses[license_key] = {
            "email": email,
            "payment_id": payment_intent_id,
            "active": True
        }

        print(f"[+] NEW LICENSE: {license_key} | {email}")
        return jsonify({"success": True, "licenseKey": license_key})

    except stripe.error.StripeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/verify-license", methods=["POST"])
def verify_license():
    try:
        data = request.json
        key = data.get("key", "").strip()

        if key not in activated_licenses:
            return jsonify({"success": False, "message": "Invalid license key."}), 404

        lic = activated_licenses[key]
        if not lic.get("active"):
            return jsonify({"success": False, "message": "License inactive."}), 403

        # בדוק שהתשלום לא בוטל
        try:
            intent = stripe.PaymentIntent.retrieve(lic["payment_id"])
            if intent.status != "succeeded":
                activated_licenses[key]["active"] = False
                return jsonify({"success": False, "message": "Payment reversed."}), 403
        except Exception:
            pass

        return jsonify({"success": True, "email": lic["email"]})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    print("Empire Tweaks Server — http://localhost:5000")
    app.run(port=5000, debug=True)