from flask import Flask, request, jsonify
import csv, os, time

ALLOWED_ORIGIN = "https://invite.yourwedding.com"

app = Flask(__name__)

@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Vary"] = "Origin"
    return resp

@app.route("/rsvp", methods=["POST"])
def rsvp():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("Name") or "").strip()
    attending = bool(data.get("Attending"))
    notes = (data.get("Notes") or "").strip()[:500]

    if not name:
        return jsonify({"error": "Name required"}), 400

    newfile = not os.path.exists("rsvps.csv")
    with open("rsvps.csv", "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if newfile:
            w.writerow(["utc", "name", "attending", "notes"])
        w.writerow([int(time.time()), name, attending, notes])

    return jsonify({"message": "Thanks for your RSVP!"})
