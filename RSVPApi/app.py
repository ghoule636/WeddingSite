from flask import Flask, request, jsonify, Response, g
import sqlite3, os, time, csv, io, logging
from logging.handlers import RotatingFileHandler

# === CONFIG ===
ALLOWED_ORIGINS = {
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://gvwedding.org,https://rsvp.gvwedding.org"
    ).split(",")
    if o.strip()
}

app = Flask(__name__)

# --- Logging ---
log_dir = os.path.dirname(LOG_PATH)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)
log_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_048_576, backupCount=5)
log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
log_handler.setLevel(logging.INFO)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(log_handler)
app.logger.propagate = False
app.logger.info("RSVP API initialized; logging to %s", LOG_PATH)

# --- DB helpers ---
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute(
        """
          CREATE TABLE IF NOT EXISTS rsvps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_utc INTEGER NOT NULL,
            name TEXT NOT NULL,
            attending INTEGER NOT NULL, -- 0/1
            guest_count INTEGER,
            notes TEXT,
            language TEXT
          )
        """
    )
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(rsvps)").fetchall()
    }
    if "guest_count" not in existing_columns:
        db.execute("ALTER TABLE rsvps ADD COLUMN guest_count INTEGER")
    if "language" not in existing_columns:
        db.execute("ALTER TABLE rsvps ADD COLUMN language TEXT")
    db.commit()

  # --- CORS ---
  @app.after_request
  def add_cors(resp):
      origin = request.headers.get("Origin", "")
      if origin in ALLOWED_ORIGINS:
          resp.headers["Access-Control-Allow-Origin"] = origin
      resp.headers["Vary"] = "Origin"
      resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
      resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
      return resp

@app.route("/rsvp", methods=["POST", "OPTIONS"])
def rsvp():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    remote_addr = request.headers.get("CF-Connecting-IP") or request.remote_addr or "-"

    name = (data.get("name") or data.get("Name") or "").strip()
    if not name:
        app.logger.warning("RSVP rejected | ip=%s | reason=missing name", remote_addr)
        return jsonify({"error": "Name required"}), 400

    attending_raw = data.get("isAttending")
    if attending_raw is None and "Attending" in data:
        attending_raw = data.get("Attending")
    attending = 1 if bool(attending_raw) else 0

    guest_count = data.get("guestCount", data.get("GuestCount"))
    if guest_count is not None:
        try:
            guest_count = int(guest_count)
        except (TypeError, ValueError):
            app.logger.warning("RSVP rejected | ip=%s | name=%s | reason=invalid guest count: %r", remote_addr, name, guest_count)
            return jsonify({"error": "Guest count must be a number"}), 400
        if guest_count < 0 or guest_count > 12:
            app.logger.warning(
                "RSVP rejected | ip=%s | name=%s | reason=guest count out of range: %s",
                remote_addr,
                name,
                guest_count,
            )
            return jsonify({"error": "Guest count must be between 0 and 12"}), 400
    elif attending:
        app.logger.warning(
            "RSVP rejected | ip=%s | name=%s | reason=missing guest count for attendee",
            remote_addr,
            name,
        )
        return jsonify({"error": "Guest count required for attendees"}), 400

    notes = (
        data.get("allergyNotes")
        or data.get("AllergyNotes")
        or data.get("notes")
        or data.get("Notes")
        or ""
    ).strip()[:500]

    language = (data.get("language") or data.get("Language") or "").strip()[:12]

    init_db()

    try:
        db = get_db()
        db.execute(
            """
                INSERT INTO rsvps (created_utc, name, attending, guest_count, notes, language)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            (int(time.time()), name, attending, guest_count, notes, language),
        )
        db.commit()
    except Exception:
        app.logger.exception("RSVP failed to store | ip=%s | name=%s", remote_addr, name)
        return jsonify({"error": "Unable to save RSVP right now"}), 500

    app.logger.info(
        "RSVP stored | ip=%s | name=%s | attending=%s | guest_count=%s | language=%s",
        remote_addr,
        name,
        bool(attending),
        guest_count if guest_count is not None else "n/a",
        language or "n/a",
    )
    return jsonify({"message": "Thanks for your RSVP!"})

@app.route("/health")
def health():
    return jsonify({"ok": True, "time": int(time.time())})

# Simple CSV export protected by a header
@app.route("/admin/export.csv")
def export_csv():
    token = request.headers.get("X-Admin-Token", "")
    if token != ADMIN_TOKEN:
        remote_addr = request.headers.get("CF-Connecting-IP") or request.remote_addr or "-"
        app.logger.warning("Unauthorized export attempt | ip=%s", remote_addr)
        return jsonify({"error": "unauthorized"}), 401

    init_db()
    db = get_db()
    rows = db.execute(
        "SELECT created_utc, name, attending, guest_count, notes, language FROM rsvps ORDER BY id ASC"
    ).fetchall()
    remote_addr = request.headers.get("CF-Connecting-IP") or request.remote_addr or "-"
    app.logger.info("Admin export requested | ip=%s | rows=%s", remote_addr, len(rows))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["utc", "name", "attending", "guest_count", "notes", "language"])
    for r in rows:
        writer.writerow(
            [r["created_utc"], r["name"], r["attending"], r["guest_count"], r["notes"], r["language"]]
        )
    csv_bytes = output.getvalue()

    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=rsvps.csv"},
    )

if __name__ == "__main__":
    with app.app_context():
        init_db()
