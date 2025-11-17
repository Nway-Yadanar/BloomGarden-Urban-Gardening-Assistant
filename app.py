from flask import Flask, jsonify, send_from_directory, request,render_template
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
DATA_DIR    = STATIC_DIR / "data" 
TASKS_PATH  = DATA_DIR/ "tasks.json"
STICKERS_DIR = DATA_DIR / "stickers"
STICKERS_PATH = STICKERS_DIR / "stickers.json"

DAILY_MOON_BONUS = 2
app = Flask(__name__, static_folder="static")  
app.secret_key = os.getenv("SECRET_KEY", "dev-change-me")

# Load key from env (safer) or fallback for testing
IPGEO_KEY = os.getenv("IPGEO_KEY", "23f93f8fd38e4ba3ba47396b69dc3398")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")  # no fallback here on purpose

# Define this function to retrieve the user ID from the session or JWT token
def get_user_id():
    # Assuming you store user_id in session during login
    return session.get('user_id')


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

import re
from werkzeug.security import generate_password_hash

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PW_RE    = re.compile(r"^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")
from urllib.parse import urlencode
from flask import redirect

def _signup_err(field, msg, username="", email=""):
    q = urlencode({"err_field": field, "err_msg": msg, "u": username, "e": email})
    return redirect(f"/signup?{q}")


@app.post("/signup")
def signup_post():
    username = (request.form.get("username") or "").strip()
    email    = (request.form.get("email") or "").strip()
    pw       = request.form.get("password") or ""
    pw2      = request.form.get("password2") or ""
    next_url = request.form.get("next") or "/chatbot"

    # validations
    if not (3 <= len(username) <= 50):
        return _signup_err("username", "Username must be 3–50 characters.", username, email)
    if not EMAIL_RE.match(email):
       return _signup_err("email", "Please enter a valid email address.", username, email)

    if not PW_RE.match(pw):
      return _signup_err("password", "Password must be at least 8 chars with 1 uppercase, 1 number, 1 special.", username, email)
    if pw != pw2:
        return _signup_err("password2", "Passwords do not match.", username, email)

    # unique checks (username or email)
    with db() as con, con.cursor() as cur:
      cur.execute("SELECT 1 FROM users WHERE Username=%s OR Email=%s LIMIT 1", (username, email))
      if cur.fetchone():
          return _signup_err("email", "Username or email already exists.", username, email)
      pwd_hash = generate_password_hash(pw, method="pbkdf2:sha256", salt_length=16)
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
            "SELECT id, password_hashed FROM users WHERE username=%s OR email=%s LIMIT 1",
            (u_or_e, u_or_e)
        )
        row = cur.fetchone()

    if not row:
        return "Account not found", 404

    uid   = row["id"]
    hash_ = row["password_hashed"]

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
DATA_DIR = STATIC_DIR / "data"
TASKS_PATH = DATA_DIR / "tasks.json"

def _get_wallet(user_id: int):
     with db() as con, con.cursor() as cur:
        cur.execute("SELECT leaves, plants, beans_lifetime FROM user_wallet WHERE user_id=%s", (user_id,))
        w = cur.fetchone()
        if not w:
            return {"leaves": 0, "plants": 0, "beans_lifetime": 0}
        return {k:int(w[k]) for k in w}

def _add_wallet(user_id: int, leaves=0, plants=0, lifetime=0):
    with db() as con, con.cursor() as cur:
        cur.execute("""
        INSERT INTO user_wallet (user_id, leaves, plants, beans_lifetime)
          VALUES (%s,%s,%s,%s)
          ON DUPLICATE KEY UPDATE
            leaves = leaves + VALUES(leaves),
            plants = plants + VALUES(plants),
            beans_lifetime = beans_lifetime + VALUES(beans_lifetime)
        """, (user_id, max(0,plants), max(0,leaves), max(0,lifetime)))

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
    with db() as con, con.cursor() as cur:
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
        rows = cur.fetchall() or []
        done_ids = {r["task_id"] for r in cur.fetchall()}

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
    with db() as con, con.cursor() as cur:
        cur.execute("SELECT Username FROM users WHERE ID=%s", (uid,))
        u = cur.fetchone() or {}
    return jsonify({
        "username": u.get("Username"),
        "leaves": w["leaves"],
        "plants": w["plants"],
        "xp": w["beans_lifetime"]
    })
from datetime import date
import json, pymysql

from datetime import date
import json
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent
TASKS_PATH = BASE_DIR / "static" / "data" / "tasks.json"

@app.get("/api/tasks/today")
def api_tasks_today():
    try:
        # 1) load tasks.json
        with open(TASKS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        # show a friendly message but never 500
        print("tasks.json load error:", e)
        return jsonify({"tasks": [], "all_done": False, "leaves_per_task": 3})

    # 2) accept multiple schemas: daily | tasks | pool | items
    pool = (raw.get("daily")
            or raw.get("tasks")
            or raw.get("pool")
            or raw.get("items")
            or [])

    # beans per task + how many to show
    rules = raw.get("rules") or {}
    leaves_per_task = int(rules.get("leaves_per_task", 3))
    count = int(rules.get("daily_count", 3))
    pool = pool[:count] if count > 0 else pool

    # 3) mark done for today (best-effort; safe with tuple cursor)
    done_ids = set()
    uid = session.get("user_id")
    if uid:
        try:
            with db() as con, con.cursor() as cur:
                cur.execute(
                    "SELECT task_id FROM user_tasks_done WHERE user_id=%s AND done_date=%s",
                    (uid, date.today())
                )
                done_ids = {str(r[0]) for r in cur.fetchall()}
        except Exception as e:
            print("tasks_today DB warn:", e)

    # 4) normalize shape for the frontend (id, title, done)
    out = []
    for t in pool:
     tid   = str(t.get("id") or t.get("key") or t.get("slug") or t.get("title"))
     title = t.get("title") or t.get("label") or tid
     leaves = t.get("leaves") or leaves_per_task  # ✅ fallback to global rule
     out.append({
        "id": tid,
        "title": title,
        "done": (tid in done_ids),
        "leaves": leaves               # ✅ include beans explicitly
    })


    return jsonify({
    "date": date.today().isoformat(),
    "tasks": out,
    "all_done": all(x["done"] for x in out) if out else False,
    "beans_per_task": leaves_per_task
})
@app.route('/api/tasks/complete', methods=['POST'])
@login_required

def complete_task():
    user_id = get_user_id()  # Get the user ID (perhaps from session or token)
    task_id = request.json['task_id']
    with db() as con, con.cursor() as cur:
    # Update the task as completed in user_task_log table
        cur.execute("UPDATE user_task_log SET status = 'completed' WHERE user_id = %s AND task_id = %s",user_id, task_id)
    
    
    # Update the user's wallet (leaves/beans)
    update_wallet_query = """
    UPDATE user_wallet 
    SET leaves = leaves + 3 
    WHERE user_id = %s
    """
    cur.execute(update_wallet_query, (user_id,))
    
    return jsonify({"message": "Task completed and leaves updated."}), 200


@app.route('/api/tasks/claim_all_done_bonus', methods=['POST'])
@login_required
def claim_all_done_bonus():
    user_id = get_user_id() 
     # Get the user ID (perhaps from session or token)

    # Check if all tasks are completed
    query = "SELECT COUNT(*) FROM user_task_log WHERE user_id = %s AND status != 'completed'"
    incomplete_tasks = fetch_query(query, (user_id,))
    
    if incomplete_tasks[0][0] > 0:
        return jsonify({"error": "Not all tasks are completed."}), 400
    
    # Add plants (or moons) to the user's wallet
    query = "UPDATE user_wallet SET plants = plants + 5 WHERE user_id = %s"
    execute_query(query, (user_id,))
    
    return jsonify({"message": "Bonus claimed, plants updated."}), 200

#profile page
@login_required
def profile_page():
    return render_template("profile.html")
import json
from datetime import date

def _load_sticker(sticker_id: str):
    with open("static/data/stickers.json", "r", encoding="utf-8") as f:
        items = json.load(f)
    # find by id
    for s in items:
        if str(s.get("id")) == str(sticker_id):
            return s
    return None

@app.post("/api/stickers/redeem")
def api_stickers_redeem():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error":"auth"}), 401

    data = request.get_json(force=True) or {}
    sid = (data.get("sticker_id") or "").strip()
    stk = _load_sticker(sid)
    if not stk:
        return jsonify({"ok":False, "error":"unknown_sticker"}), 400

    # cost can be like "25" (beans) or "2m" (moons)
    cost_raw = str(stk.get("cost", "")).lower().strip()
    use_moons = cost_raw.endswith("m")
    cost = int(cost_raw[:-1]) if use_moons else int(cost_raw or "0")

    with db() as con, con.cursor() as cur:
        # already owned?
        cur.execute("SELECT 1 FROM user_stickers WHERE user_id=%s AND sticker_id=%s LIMIT 1", (uid, sid))
        if cur.fetchone():
            # return wallet unchanged
            cur.execute("SELECT leaves, plants FROM user_wallet WHERE user_id=%s", (uid,))
            w = cur.fetchone() or {"leaves":0, "plants":0}
            return jsonify({"ok":True, "already_owned":True, "leaves":int(w.get("leaves",0)), "plants":int(w.get("plants",0))})

        # check wallet
        cur.execute("SELECT leaves, plants FROM user_wallet WHERE user_id=%s LIMIT 1", (uid,))
        w = cur.fetchone() or {"leaves":0, "plants":0}
        leaves = int(w.get("leaves", 0))
        plants = int(w.get("plants", 0))

        if use_moons:
            if plants < cost:
                return jsonify({"ok":False, "error":"insufficient_plants", "leaves":leaves, "plants":plants}), 400
            # deduct moons
            cur.execute("UPDATE user_wallet SET plants = plants - %s WHERE user_id=%s", (cost, uid))
        else:
            if leaves < cost:
                return jsonify({"ok":False, "error":"insufficient_leaves", "leaves":leaves, "plants":plants}), 400
            # deduct beans
            cur.execute("UPDATE user_wallet SET leaves = leaves - %s WHERE user_id=%s", (cost, uid))

        # grant sticker
        cur.execute(
            "INSERT INTO user_stickers (user_id, sticker_id, acquired_at) VALUES (%s,%s,%s)",
            (uid, sid, date.today())
        )

        # new wallet values
        cur.execute("SELECT leaves, plants FROM user_wallet WHERE user_id=%s", (uid,))
        w2 = cur.fetchone() or {"leaves":0, "plants":0}

    return jsonify({"ok":True, "leaves":int(w2.get("leaves",0)), "plants":int(w2.get("plants",0))})



# --------------------------------------------------------------------
# Dev entry
# --------------------------------------------------------------------
if __name__ == "__main__":
    # Use host='0.0.0.0' if running in a container
    app.run(debug=True)


