import requests
import json
import os
import hashlib

# ← תכניס את ה-Product Permalink שלך מ-Gumroad
# Gumroad → המוצר → Edit → ה-URL נראה כך: gumroad.com/l/XXXX
GUMROAD_PRODUCT_ID = "EmpireTweaks"

LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".empire_tweaks_license")


def verify_license_online(key: str) -> dict:
    """
    בודק את המפתח מול Gumroad API.
    מחזיר dict עם success, message, email של הקונה.
    """
    try:
        response = requests.post(
            "https://api.gumroad.com/v2/licenses/verify",
            data={
                "product_permalink": GUMROAD_PRODUCT_ID,
                "license_key": key.strip(),
                "increment_uses_count": "false"  # לא מונה שימוש כל פעם
            },
            timeout=8
        )
        data = response.json()

        if data.get("success"):
            purchase = data.get("purchase", {})
            # בדיקה שהרכישה לא בוטלה / הוחזרה
            if purchase.get("refunded") or purchase.get("chargebacked"):
                return {"success": False, "message": "This license has been refunded."}
            return {
                "success": True,
                "message": "License activated!",
                "email": purchase.get("email", ""),
                "buyer_name": purchase.get("full_name", "")
            }
        else:
            return {
                "success": False,
                "message": data.get("message", "Invalid license key.")
            }

    except requests.exceptions.Timeout:
        return {"success": False, "message": "Connection timeout. Check your internet."}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": "No internet connection."}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}


def save_license(key: str):
    """שומר את המפתח מוצפן על הדיסק כדי שלא צריך להכניס כל פעם."""
    hashed = hashlib.sha256(key.strip().encode()).hexdigest()
    data = {"key": key.strip(), "hash": hashed}
    with open(LICENSE_FILE, "w") as f:
        json.dump(data, f)


def load_saved_license() -> str | None:
    """טוען license key שמור מהדיסק."""
    try:
        if not os.path.exists(LICENSE_FILE):
            return None
        with open(LICENSE_FILE, "r") as f:
            data = json.load(f)
        key = data.get("key", "")
        # בדיקה שהקובץ לא שונה ידנית
        expected_hash = hashlib.sha256(key.encode()).hexdigest()
        if data.get("hash") != expected_hash:
            return None
        return key
    except:
        return None


def remove_license():
    """מוחק את ה-license (לצורך logout / refund)."""
    if os.path.exists(LICENSE_FILE):
        os.remove(LICENSE_FILE)


def is_pro_active() -> bool:
    """
    מחזיר True אם יש license תקין שמור.
    קורא לזה בכל מקום באפליקציה שצריך לבדוק Pro.
    """
    key = load_saved_license()
    if not key:
        return False

    # בדיקה online אחת ל-24 שעות (אופציונלי — מונע בזבוז API calls)
    cache_file = LICENSE_FILE + "_cache"
    try:
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                cache = json.load(f)
            import time
            if time.time() - cache.get("timestamp", 0) < 86400:  # 24 שעות
                return cache.get("valid", False)
    except:
        pass

    # בדיקה online
    result = verify_license_online(key)
    # שמור cache
    try:
        import time
        with open(cache_file, "w") as f:
            json.dump({"valid": result["success"], "timestamp": time.time()}, f)
    except:
        pass

    return result["success"]


# ───────────────────────────────────────────
# דוגמה לשימוש ב-GUI (tkinter)
# ───────────────────────────────────────────
if __name__ == "__main__":
    import tkinter as tk
    from tkinter import messagebox

    def activate():
        key = entry.get().strip()
        if not key:
            messagebox.showwarning("Empire Tweaks", "Please enter your license key.")
            return

        btn.config(text="Checking...", state="disabled")
        root.update()

        result = verify_license_online(key)

        if result["success"]:
            save_license(key)
            messagebox.showinfo(
                "Empire Tweaks Pro",
                f"✓ Pro activated!\n\nWelcome, {result.get('buyer_name') or result.get('email', '')}!\nAll features are now unlocked."
            )
            root.destroy()
            # ← כאן תקרא לפונקציה שמפעילה את הפיצ'רים של Pro באפליקציה שלך
        else:
            messagebox.showerror("Activation Failed", result["message"])
            btn.config(text="Activate Pro", state="normal")

    root = tk.Tk()
    root.title("Empire Tweaks — Activate Pro")
    root.geometry("420x220")
    root.configure(bg="#0c0c13")
    root.resizable(False, False)

    tk.Label(root, text="EMPIRE TWEAKS PRO", font=("Arial", 14, "bold"),
             bg="#0c0c13", fg="#42a5f5").pack(pady=(28, 4))

    tk.Label(root, text="Enter your license key from your purchase email:",
             font=("Arial", 9), bg="#0c0c13", fg="#52607a").pack()

    entry = tk.Entry(root, width=42, font=("Courier", 10),
                     bg="#1a1a28", fg="white", insertbackground="white",
                     relief="flat", bd=8)
    entry.pack(pady=14, padx=30)
    entry.bind("<Return>", lambda e: activate())

    btn = tk.Button(root, text="Activate Pro", command=activate,
                    bg="#1565c0", fg="white", font=("Arial", 10, "bold"),
                    relief="flat", padx=20, pady=8, cursor="hand2",
                    activebackground="#1976d2", activeforeground="white")
    btn.pack()

    # בדוק אם כבר מופעל
    if is_pro_active():
        messagebox.showinfo("Empire Tweaks", "Pro is already active on this machine!")
    else:
        root.mainloop()