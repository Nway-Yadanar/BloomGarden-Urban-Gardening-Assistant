from flask import Flask, jsonify, send_from_directory
import requests
import os

app = Flask(__name__)

# Load key from env (safer) or hardcode for testing
API_KEY = os.getenv("IPGEO_KEY", "23f93f8fd38e4ba3ba47396b69dc3398")

@app.route("/moon")
def get_moon():
    lat, lon = 16.8, 96.15  # Yangon
    url = f"https://api.ipgeolocation.io/astronomy?apiKey={API_KEY}&lat={lat}&long={lon}"
    res = requests.get(url).json()
    print(res)
    return jsonify({
        "phase": res["moon_phase"],
        "illumination": res["moon_illumination","0"]
    })
    

# Serve frontend files
@app.route("/")
def home():
    return send_from_directory("frontend", "moon.html")

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory("frontend", filename)

if __name__ == "__main__":
    app.run(debug=True)
