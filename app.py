

# from flask import Flask, jsonify, send_from_directory
# import requests
# import os

# app = Flask(__name__)

# # Load key from env (safer) or hardcode for testing
# API_KEY = os.getenv("IPGEO_KEY", "23f93f8fd38e4ba3ba47396b69dc3398")

# # --- API: Moon data ---------------------------------------------------------
# @app.route("/moon")
# def moon():
#     lat, lon = 16.8409, 96.1735  # Example: Yangon
#     url = f"https://api.ipgeolocation.io/astronomy?apiKey={API_KEY}&lat={lat}&long={lon}"
#     try:
#         res = requests.get(url, timeout=10)  # safer with timeout
#         res.raise_for_status()
#         data = res.json()
#         return jsonify({
#             "phase": data.get("moon_phase", "Unknown"),
#             "illumination": data.get("moon_illumination", "0")
#         })
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
    
# # --- API: Weather data ------------------------------------------------------
# @app.route("/weather")
# def weather():
#     lat = flask.request.args.get("lat")
#     lon = flask.request.args.get("lon")
#     api_key = os.getenv("OPENWEATHER_KEY")
#     if not (lat and lon and api_key):
#         return jsonify({"error": "Missing lat/lon or API key"}), 400

#     url = (
#         f"https://api.openweathermap.org/data/2.5/weather"
#         f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
#     )
#     try:
#         res = requests.get(url, timeout=10)
#         res.raise_for_status()
#         data = res.json()
#         # Forward only safe fields
#         return jsonify({
#             "name": data.get("name"),
#             "main": data.get("main"),
#             "weather": data.get("weather")
#         })
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500


# # --- Pages: Index + Chatbot -------------------------------------------------
# @app.route("/")
# def home():
#     # Serve your new landing page (index)
#     return send_from_directory("template", "home.html")

# @app.route("/chatbot")
# @app.route("/chatbot.html")
# def chatbot():
#     # Serve the chatbot UI
#     return send_from_directory("template", "chatbot.html")

# # --- Static passthrough for other files in /template ------------------------
# @app.route("/<path:filename>")
# def serve_static(filename):
#     return send_from_directory("template", filename)

# if __name__ == "__main__":
#     # Set host='0.0.0.0' if running in a container
#     app.run(debug=True)



from flask import Flask, jsonify, send_from_directory, request
import requests
import os
from pathlib import Path
import pymysql
from datetime import datetime, timezone
from math import sin, pi
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename  # you use this in /pest-detect
from flask import session, redirect, url_for  # you already import request above



DB = {
    "host": "127.0.0.1",
    "port": 3309,                    # XAMPP MySQL
    "user": "root",
    "password": "",        # (often empty by default)
    "database": "bloom_garden",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": True
}
def db(): return pymysql.connect(**DB)


# --------------------------------------------------------------------
# App setup
# --------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "template"   
STATIC_DIR   = BASE_DIR / "static"    

app = Flask(__name__, static_folder=None)  
app.secret_key = os.getenv("SECRET_KEY", "dev-change-me")

# Load key from env (safer) or fallback for testing
IPGEO_KEY = os.getenv("IPGEO_KEY", "23f93f8fd38e4ba3ba47396b69dc3398")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")  # no fallback here on purpose

# Lunar notice page
@app.route("/notice")
@app.route("/notice.html")
def notice():
    return send_from_directory(TEMPLATE_DIR, "notice.html")

# --------------------------------------------------------------------
# API: Moon data
# --------------------------------------------------------------------
@app.route("/moon")
def moon():
    """
    Returns: {"phase": <string>, "illumination": <int percent 0..100>}
    - Tries ipgeolocation quickly (2s timeout).
    - Falls back to a precise local calculation so the UI never breaks.
    """
    # --- helper: local, dependency-free moon calc ---
    def local_moon():
        # Reference epoch & synodic month length
        ref = datetime(2001, 1, 1, tzinfo=timezone.utc)
        synodic_days = 29.530588853  # mean synodic month
        days = (datetime.now(timezone.utc) - ref).total_seconds() / 86400.0
        phase = (days % synodic_days) / synodic_days  # 0..1 (0=new, 0.5=full)
        # illum fraction ≈ sin^2(pi * phase)
        illum_pct = int(round((sin(pi * phase) ** 2) * 100))

        # Name buckets (kept flexible so your JS normalizePhase() still matches)
        eps = 0.03  # ~0.9 day tolerance around the quarter phases
        if phase < eps or phase > 1 - eps:
            name = "New Moon"
        elif abs(phase - 0.25) < eps:
            name = "First Quarter"
        elif abs(phase - 0.50) < eps:
            name = "Full Moon"
        elif abs(phase - 0.75) < eps:
            name = "Last Quarter"
        elif phase < 0.25:
            name = "Waxing Crescent Moon"
        elif phase < 0.50:
            name = "Waxing Gibbous Moon"
        elif phase < 0.75:
            name = "Waning Gibbous Moon"
        else:
            name = "Waning Crescent Moon"

        return {"phase": name, "illumination": illum_pct}

    # --- fast attempt: ipgeolocation (if available), then normalize ---
    try:
        lat, lon = 16.8409, 96.1735  # Yangon (location isn’t critical for phase)
        url = f"https://api.ipgeolocation.io/astronomy?apiKey={IPGEO_KEY}&lat={lat}&long={lon}"
        res = requests.get(url, timeout=2)
        res.raise_for_status()
        data = res.json()

        # Phase string straight through
        phase = data.get("moon_phase") or data.get("phase") or "Unknown"

        # Illumination may come as "57" or "57.3" or as 0..1 fraction on some APIs
        illum_raw = (
            data.get("moon_illumination") or
            data.get("illumination") or
            data.get("moon_illumination_fraction")
        )
        illum_pct = None
        if illum_raw is not None:
            try:
                f = float(illum_raw)
                illum_pct = int(round(f if f > 1 else f * 100))
            except Exception:
                pass

        if illum_pct is None or phase == "Unknown":
            # use local values to fill any gaps
            fallback = local_moon()
            phase = phase if phase != "Unknown" else fallback["phase"]
            illum_pct = illum_pct if illum_pct is not None else fallback["illumination"]

        return jsonify({"phase": phase, "illumination": int(illum_pct)})

    except Exception:
        # Total fallback: dependency-free, guaranteed to work
        return jsonify(local_moon())


# --------------------------------------------------------------------
# Pest Detection
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

@app.route("/pest-detect", methods=["POST"])
def pest_detect():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    # save temporarily (optional: you could skip if you process in-memory)
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    # TODO: Replace this with real ML model inference
    # Here we return a mock response
    fake_results = {
        "detected": True,
        "pests": ["aphids", "spider mites"],
        "recommendations": [
            "Spray neem oil weekly",
            "Introduce ladybugs to control aphids"
        ]
    }
    return jsonify(fake_results)

# --------------------------------------------------------------------
# API: Weather data
# --------------------------------------------------------------------
@app.route("/weather")
def weather_api():
    """OpenWeather proxy (supply ?lat=..&lon=..)"""
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if not (lat and lon and OPENWEATHER_KEY):
        return jsonify({"error": "Missing lat/lon or OPENWEATHER_KEY"}), 400

    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={OPENWEATHER_KEY}&units=metric"
    )
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        # Return only necessary/safe fields
        return jsonify({
            "name": data.get("name"),
            "main": data.get("main"),
            "weather": data.get("weather"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------------------------
# Pages (HTML)
# --------------------------------------------------------------------
@app.route("/")
def home():
    # landing page
    return send_from_directory(TEMPLATE_DIR, "landing.html")

# move the unprotected route out of the way to avoid collision
@app.route("/chatbot-plain", endpoint="chatbot_plain")
def chatbot_plain():
    return send_from_directory(TEMPLATE_DIR, "chatbot.html")


# Plant FAQ (explicit route)
@app.route("/plantfaq")
@app.route("/plantfaq.html")
def plantfaq():
    return send_from_directory(TEMPLATE_DIR, "plantfaq.html")

# Moon page (explicit route) — NOTE: /moon is already used by the API
@app.route("/moon.html")
@app.route("/moonview")
def moon_page():
    return send_from_directory(TEMPLATE_DIR, "moon.html")


# --------------------------------------------------------------------
# Static passthrough (CSS, JS, images, JSON data)
#   - Your JS references /static/data/indoor_plants.json
# --------------------------------------------------------------------
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

# Optional: serve any other file under /template directly by name
@app.route("/<path:filename>")
def template_passthrough(filename):
    return send_from_directory(TEMPLATE_DIR, filename)

# --------------------------------------------------------------------
# ChatBot
# --------------------------------------------------------------------
@app.post("/api/chat/session")
def create_session():
    user_id = 1  # replace with real user later
    with db() as con, con.cursor() as cur:
        cur.execute("INSERT INTO chat_sessions (user_id) VALUES (%s)", (user_id,))
        sid = cur.lastrowid
    return jsonify({"session_id": sid})

@app.get("/api/chat/history")
def history():
    sid = int(request.args.get("session_id"))
    with db() as con, con.cursor() as cur:
        cur.execute("""SELECT role, content, model, tokens_in, tokens_out, latency_ms, sources
                       FROM chat_messages
                       WHERE session_id=%s ORDER BY id ASC""", (sid,))
        rows = cur.fetchall()
    return jsonify({"messages": rows})

@app.post("/api/chat")
def chat():
    data = request.get_json(force=True) or {}
    sid = int(data.get("session_id", 0))
    text = (data.get("message") or "").strip()
    if not sid or not text:
        return jsonify({"reply":"missing session_id or message"}), 400

    # TODO: save to DB if you want
    return jsonify({"reply": f"you said: {text}"})

# in app.py
from functools import wraps
from flask import session, redirect, url_for, request

def login_required(view):
    @wraps(view)
    def _wrap(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page', next=request.path))
        return view(*args, **kwargs)
    return _wrap

@app.route("/chatbot")
@login_required
def chatbot():
     return send_from_directory(TEMPLATE_DIR, "chatbot.html")

# after successful login/signup

@app.get("/login")
def login_page():
    return send_from_directory(TEMPLATE_DIR, "login.html")

@app.get("/signup")
def signup_page():
    return send_from_directory(TEMPLATE_DIR, "signup.html")

@app.post("/signup")
def signup_post():
    email    = (request.form.get("email") or "").strip()
    username = (request.form.get("username") or "").strip()
    pw       = request.form.get("password") or ""
    pw2      = request.form.get("password2") or ""
    next_url = request.form.get("next") or "/chatbot"

    if not email or not username or not pw:
        return "Missing fields", 400
    if pw != pw2 or len(pw) < 8:
        return "Password mismatch / too short", 400

    pwd_hash = generate_password_hash(pw, method="pbkdf2:sha256", salt_length=16)

    with db() as con, con.cursor() as cur:
        # enforce unique user/email
        cur.execute("SELECT 1 FROM users WHERE Username=%s OR Email=%s", (username, email))
        if cur.fetchone():
            return "Username or email already exists", 409

        cur.execute(
            "INSERT INTO users (Username, Email, Password_hashed) VALUES (%s,%s,%s)",
            (username, email, pwd_hash)
        )
        new_id = cur.lastrowid

        # ensure wallet row exists (optional)
        try:
            cur.execute(
                "INSERT IGNORE INTO user_wallet (user_id, beans, moons, beans_lifetime) VALUES (%s,0,0,0)",
                (new_id,)
            )
        except Exception:
            pass

    session["user_id"] = new_id
    return redirect(next_url)


@app.post("/login")
def do_login():
    u_or_e   = (request.form.get("username_or_email") or "").strip()
    pw       = request.form.get("password") or ""
    next_url = request.form.get("next") or "/chatbot"

    if not u_or_e or not pw:
        return "Missing fields", 400

    with db() as con, con.cursor() as cur:
        cur.execute(
            "SELECT ID, Password_hashed FROM users WHERE Username=%s OR Email=%s LIMIT 1",
            (u_or_e, u_or_e)
        )
        row = cur.fetchone()

    if not row:
        return "Account not found", 404

    uid   = row["ID"]
    hash_ = row["Password_hashed"]

    if not check_password_hash(hash_, pw):
        return "Invalid credentials", 401

    session["user_id"] = uid
    return redirect(next_url)


# --------------------------------------------------------------------
# Dev entry
# --------------------------------------------------------------------
if __name__ == "__main__":
    # Use host='0.0.0.0' if running in a container
    app.run(debug=True)
