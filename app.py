

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
import json, hashlib
from datetime import date, timedelta
from datetime import datetime, timezone
from math import sin, pi
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename  # you use this in /pest-detect
from flask import session, redirect,abort, url_for  # you already import request above



DB = {
    "host": "127.0.0.1",
    "port": 3309,                    
    "user": "root",
    "password": "",        
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
    if filename.startswith("api/"):
            abort(404)
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

@app.get("/tasks")
@app.get("/tasks.html")
@login_required
def tasks_page():
    return send_from_directory(TEMPLATE_DIR, "tasks.html")

@app.get("/profile")
@login_required
def profile_page():
    # (Create template/profile.html when you’re ready)
    return send_from_directory(TEMPLATE_DIR, "profile.html")
# ===== Beans/Moons Tasks API (minimal, matches tasks.html JS) =====
DATA_DIR =  Path(app.static_folder) / "data"
TASKS_PATH = DATA_DIR / "tasks.json"

def _get_wallet(user_id: int):
    with db() as con, con.cursor(dictionary=True) as cur:
        cur.execute("SELECT beans, moons, beans_lifetime FROM user_wallet WHERE user_id=%s", (user_id,))
        w = cur.fetchone()
        if not w:
            return {"beans": 0, "moons": 0, "beans_lifetime": 0}
        return {k:int(w[k]) for k in w}

def _add_wallet(user_id: int, beans=0, moons=0, lifetime=0):
    with db() as con, con.cursor() as cur:
        cur.execute("""
        INSERT INTO user_wallet (user_id, beans, moons, beans_lifetime)
          VALUES (%s,%s,%s,%s)
          ON DUPLICATE KEY UPDATE
            beans = beans + VALUES(beans),
            moons = moons + VALUES(moons),
            beans_lifetime = beans_lifetime + VALUES(beans_lifetime)
        """, (user_id, max(0,beans), max(0,moons), max(0,lifetime)))

def _today(): return date.today().isoformat()

def _load_tasks_doc():
    doc = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    return {
        "rules": doc.get("rules", {}),
        "tasks": doc.get("tasks", [])
    }

def _pick_today_tasks(user_id: int):
    """Deterministic daily selection using a stable hash; avoids tasks used in the last N days."""
    doc = _load_tasks_doc()
    rules = doc["rules"]; tasks = doc["tasks"]
    slots = int(rules.get("daily_slots", 3))
    no_repeat = int(rules.get("no_repeat_within_days", 3))

    # tasks to avoid (done within window)
    avoid = set()
    with db() as con, con.cursor(dictionary=True) as cur:
        cur.execute("""
          SELECT task_id FROM user_task_log
          WHERE user_id=%s AND task_date >= %s
        """, (user_id, (date.today() - timedelta(days=no_repeat)).isoformat()))
        for r in cur.fetchall(): avoid.add(r["task_id"])

    # stable ordering by hash
    def key_fn(t):
        h = hashlib.sha256(f"{user_id}|{_today()}|{t['id']}".encode()).hexdigest()
        return h

    pool = [t for t in tasks if t.get("id") not in avoid] or tasks
    pool.sort(key=key_fn)
    picked = pool[:slots]

    # mark done for today
    done_ids = set()
    with db() as con, con.cursor() as cur:
        cur.execute("""
          SELECT task_id FROM user_task_log WHERE user_id=%s AND task_date=%s
        """, (user_id, _today()))
        done_ids = {r[0] for r in cur.fetchall()}

    items = [{
        "id": t["id"],
        "title": t.get("title",""),
        "beans": int(t.get("beans", 0)),
        "done": t["id"] in done_ids
    } for t in picked]

    all_done = all(x["done"] for x in items) and len(items) > 0
    return items, all_done, rules

@app.get("/api/wallet")
@login_required
def api_wallet():
    uid = session["user_id"]
    w = _get_wallet(uid)
    # if you want username in header chip:
    with db() as con, con.cursor(dictionary=True) as cur:
        cur.execute("SELECT Username FROM users WHERE ID=%s", (uid,))
        u = cur.fetchone() or {}
    return jsonify({
        "username": u.get("Username"),
        "beans": w["beans"],
        "moons": w["moons"],
        "xp": w["beans_lifetime"]
    })

@app.get("/api/tasks/today")
@login_required
def api_tasks_today():
    uid = session["user_id"]
    tasks, all_done, rules = _pick_today_tasks(uid)
    w = _get_wallet(uid)
    return jsonify({
        "date": _today(),
        "beans": w["beans"],
        "moons": w["moons"],
        "tasks": tasks,
        "all_done": all_done,
        "all_done_bonus_moons": int(rules.get("all_done_bonus_moons", 2)),
        "max_daily_beans": int(rules.get("max_daily_beans", 25))
    })

@app.post("/api/tasks/complete")
@login_required
def api_tasks_complete():
    uid = session["user_id"]
    data = request.get_json(silent=True) or request.form
    task_id = (data.get("task_id") or "").strip()
    if not task_id: return jsonify({"error":"task_id"}), 400

    today_tasks, _, rules = _pick_today_tasks(uid)
    t = next((x for x in today_tasks if x["id"] == task_id), None)
    if not t: return jsonify({"error":"not_today"}), 400

    # idempotent: if already logged for today, no beans
    with db() as con, con.cursor() as cur:
        cur.execute("""
          SELECT 1 FROM user_task_log WHERE user_id=%s AND task_id=%s AND task_date=%s
        """, (uid, task_id, _today()))
        if cur.fetchone():
            w = _get_wallet(uid)
            return jsonify({"awarded_beans": 0, "awarded_moons": 0, "beans": w["beans"], "moons": w["moons"]})

    # enforce daily cap
    cap = int(rules.get("max_daily_beans", 25))
    with db() as con, con.cursor() as cur:
        cur.execute("""
          SELECT COALESCE(SUM(awarded_beans),0) FROM user_task_log WHERE user_id=%s AND task_date=%s
        """, (uid, _today()))
        awarded_today = int(cur.fetchone()[0])

    remaining = max(cap - awarded_today, 0)
    award = min(t["beans"], remaining)

    # log + update wallet
    with db() as con, con.cursor() as cur:
        cur.execute("""
          INSERT INTO user_task_log (user_id, task_id, task_date, awarded_beans)
          VALUES (%s,%s,%s,%s)
        """, (uid, task_id, _today(), award))
    if award > 0:
        _add_wallet(uid, beans=award, lifetime=award)

    w = _get_wallet(uid)
    return jsonify({
        "awarded_beans": award,
        "awarded_moons": 0,
        "beans": w["beans"],
        "moons": w["moons"],
        "daily_cap": cap,
        "daily_awarded": min(awarded_today + award, cap)
    })

@app.post("/api/tasks/claim_all_done_bonus")
@login_required
def api_claim_all_done_bonus():
    uid = session["user_id"]
    _, all_done, rules = _pick_today_tasks(uid)
    if not all_done: return jsonify({"error":"not_all_done"}), 400
    bonus = int(rules.get("all_done_bonus_moons", 2))

    # prevent double-claim using user_daily_bonus
    with db() as con, con.cursor() as cur:
        cur.execute("SELECT 1 FROM user_daily_bonus WHERE user_id=%s AND bonus_date=%s", (uid, _today()))
        if cur.fetchone():
            w = _get_wallet(uid)
            return jsonify({"awarded_moons": 0, "beans": w["beans"], "moons": w["moons"]})

    with db() as con, con.cursor() as cur:
        cur.execute("INSERT INTO user_daily_bonus (user_id, bonus_date, awarded_moons) VALUES (%s,%s,%s)",
                    (uid, _today(), bonus))
    _add_wallet(uid, moons=bonus)
    w = _get_wallet(uid)
    return jsonify({"awarded_moons": bonus, "beans": w["beans"], "moons": w["moons"]})

# --------------------------------------------------------------------
# Dev entry
# --------------------------------------------------------------------
if __name__ == "__main__":
    # Use host='0.0.0.0' if running in a container
    app.run(debug=True)
