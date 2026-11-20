from flask import Flask, request, jsonify, send_from_directory
from database import (
    init_db, get_db,
    create_user, get_user_by_username,
    save_masters, get_masters, has_masters, update_masters,
    add_record, get_records, get_record_by_id,
    update_record, delete_record,
    get_dashboard_data,
    set_budget, get_budgets, delete_budget, check_budget_alerts, get_budget_progress
)
import jwt
import datetime
import bcrypt
import os
from bsi.readers.errors import PasswordProtectedError
import analytics, categorizer, importer, llm_insights, risk, income, counterparty, persona, persona_ai, forecast, forecast_ai

llm_insights.load_env()
app = Flask(__name__, static_folder="templates", static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-in-production-abc123")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # statement uploads

init_db()

# ─── Auth helpers ────────────────────────────────────────────────────────────

def make_token(user_id, username):
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    }
    return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

def verify_token(req):
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    try:
        return jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def auth_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = verify_token(request)
        if not payload:
            return jsonify({"error": "Unauthorized"}), 401
        request.user = payload
        return f(*args, **kwargs)
    return decorated

# ─── Static pages ────────────────────────────────────────────────────────────

@app.route("/")
def serve_index():
    resp = send_from_directory("templates", "index.html")
    resp.headers["Cache-Control"] = "no-store"          # always load the current UI, never a cached older page
    return resp

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory("templates", filename)

# ─── Auth routes ─────────────────────────────────────────────────────────────

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if get_user_by_username(username):
        return jsonify({"error": "Username already taken"}), 409
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = create_user(username, hashed)
    token = make_token(user_id, username)
    return jsonify({"token": token, "username": username, "needs_masters": True}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    user = get_user_by_username(username)
    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Invalid username or password"}), 401
    token = make_token(user["id"], username)
    masters_done = has_masters(user["id"])
    return jsonify({"token": token, "username": username, "needs_masters": not masters_done}), 200

# ─── Masters routes ───────────────────────────────────────────────────────────

@app.route("/api/masters", methods=["POST"])
@auth_required
def create_masters():
    data = request.get_json()
    user_id = request.user["user_id"]
    if has_masters(user_id):
        return jsonify({"error": "Masters already configured. Use PUT to update."}), 409
    required = ["categories", "subcategories", "receivers", "payers", "opening_balance"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400
    try:
        opening_balance = float(data["opening_balance"])
    except (ValueError, TypeError):
        return jsonify({"error": "Opening balance must be a number"}), 400
    save_masters(
        user_id=user_id,
        categories=[c.strip() for c in data["categories"] if c.strip()],
        subcategories=[s.strip() for s in data["subcategories"] if s.strip()],
        receivers=[r.strip() for r in data["receivers"] if r.strip()],
        payers=[p.strip() for p in data["payers"] if p.strip()],
        opening_balance=opening_balance
    )
    return jsonify({"message": "Masters saved"}), 201

@app.route("/api/masters", methods=["PUT"])
@auth_required
def edit_masters():
    data = request.get_json()
    user_id = request.user["user_id"]
    if not has_masters(user_id):
        return jsonify({"error": "Masters not configured yet. Use POST to create."}), 404
    required = ["categories", "subcategories", "receivers", "payers", "opening_balance"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400
    try:
        opening_balance = float(data["opening_balance"])
    except (ValueError, TypeError):
        return jsonify({"error": "Opening balance must be a number"}), 400
    update_masters(
        user_id=user_id,
        categories=[c.strip() for c in data["categories"] if c.strip()],
        subcategories=[s.strip() for s in data["subcategories"] if s.strip()],
        receivers=[r.strip() for r in data["receivers"] if r.strip()],
        payers=[p.strip() for p in data["payers"] if p.strip()],
        opening_balance=opening_balance
    )
    return jsonify({"message": "Masters updated successfully"}), 200

@app.route("/api/masters", methods=["GET"])
@auth_required
def fetch_masters():
    user_id = request.user["user_id"]
    masters = get_masters(user_id)
    if not masters:
        return jsonify({"error": "Masters not configured"}), 404
    return jsonify(masters), 200

# ─── Dashboard route ──────────────────────────────────────────────────────────

@app.route("/api/dashboard", methods=["GET"])
@auth_required
def dashboard():
    user_id = request.user["user_id"]
    data = get_dashboard_data(user_id)
    # Activity diagram: always check budget alerts on dashboard load
    data["budget_alerts"] = check_budget_alerts(user_id)
    return jsonify(data), 200

# ─── Records routes ───────────────────────────────────────────────────────────

@app.route("/api/records", methods=["POST"])
@auth_required
def create_record():
    data = request.get_json()
    user_id = request.user["user_id"]
    required = ["type", "amount", "category"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400
    if data["type"] not in ("expense", "earning"):
        return jsonify({"error": "Type must be 'expense' or 'earning'"}), 400
    try:
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Amount must be a positive number"}), 400
    record_id = add_record(
        user_id=user_id,
        record_type=data["type"],
        amount=amount,
        category=data.get("category", ""),
        subcategory=data.get("subcategory", ""),
        receiver_payer=data.get("receiver_payer", ""),
        notes=data.get("notes", ""),
        date=data.get("date") or datetime.date.today().isoformat()
    )
    # Sequence diagram: after Create Record → Check Limit (Budget) → Compare → alerts
    alerts = check_budget_alerts(user_id) if data["type"] == "expense" else []
    return jsonify({"id": record_id, "message": "Record added", "budget_alerts": alerts}), 201

@app.route("/api/records", methods=["GET"])
@auth_required
def list_records():
    user_id = request.user["user_id"]
    filters = {
        "min_amount": request.args.get("min_amount"),
        "max_amount": request.args.get("max_amount"),
        "receiver_payer": request.args.get("receiver_payer"),
        "record_type": request.args.get("type"),
        "category": request.args.get("category"),
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
    }
    records = get_records(user_id, filters)
    streams = income.classify_credits(records)
    for r in records:
        r["risk_flags"] = [f["type"] for f in risk.flags_for_record(r)]
        r["income_stream"] = streams[id(r)]["stream"] if id(r) in streams else None
    return jsonify(records), 200

@app.route("/api/records/<int:record_id>", methods=["GET"])
@auth_required
def get_single_record(record_id):
    user_id = request.user["user_id"]
    record = get_record_by_id(record_id, user_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404
    return jsonify(record), 200

@app.route("/api/records/<int:record_id>", methods=["PUT"])
@auth_required
def edit_record(record_id):
    data = request.get_json()
    user_id = request.user["user_id"]
    record = get_record_by_id(record_id, user_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404
    try:
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Amount must be a positive number"}), 400
    update_record(
        record_id=record_id,
        user_id=user_id,
        record_type=data.get("type", record["type"]),
        amount=amount,
        category=data.get("category", record["category"]),
        subcategory=data.get("subcategory", record["subcategory"]),
        receiver_payer=data.get("receiver_payer", record["receiver_payer"]),
        notes=data.get("notes", record["notes"]),
        date=data.get("date", record["date"])
    )
    return jsonify({"message": "Record updated"}), 200

@app.route("/api/records/<int:record_id>", methods=["DELETE"])
@auth_required
def remove_record(record_id):
    user_id = request.user["user_id"]
    record = get_record_by_id(record_id, user_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404
    delete_record(record_id, user_id)
    return jsonify({"message": "Record deleted"}), 200

# ─── Budget routes ────────────────────────────────────────────────────────────

@app.route("/api/budgets", methods=["GET"])
@auth_required
def list_budgets():
    user_id = request.user["user_id"]
    budgets = get_budget_progress(user_id)
    alerts = check_budget_alerts(user_id)
    return jsonify({"budgets": budgets, "alerts": alerts}), 200

@app.route("/api/budgets", methods=["POST"])
@auth_required
def create_budget():
    data = request.get_json()
    user_id = request.user["user_id"]
    period = data.get("period", "")
    if period not in ("weekly", "monthly"):
        return jsonify({"error": "Period must be 'weekly' or 'monthly'"}), 400
    try:
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Amount must be a positive number"}), 400
    set_budget(user_id, period, amount, data.get("category", ""))
    return jsonify({"message": "Budget set"}), 201

@app.route("/api/budgets/<int:budget_id>", methods=["DELETE"])
@auth_required
def remove_budget(budget_id):
    user_id = request.user["user_id"]
    delete_budget(budget_id, user_id)
    return jsonify({"message": "Budget deleted"}), 200

@app.route("/api/budgets/alerts", methods=["GET"])
@auth_required
def budget_alerts():
    user_id = request.user["user_id"]
    alerts = check_budget_alerts(user_id)
    return jsonify(alerts), 200

# ─── Intelligence routes (statement import, analytics, insights, ML) ─────────

@app.route("/api/import", methods=["POST"])
@auth_required
def import_statement_route():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file uploaded"}), 400
    try:
        result = importer.import_statement(request.user["user_id"], f)
    except PasswordProtectedError as e:
        return jsonify({"error": str(e), "password_protected": True}), 422
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Could not read this statement: {e}"}), 422
    return jsonify(result), 201

@app.route("/api/analytics", methods=["GET"])
@auth_required
def analytics_route():
    return jsonify(analytics.get_analytics(request.user["user_id"],
                                           request.args.get("date_from"),
                                           request.args.get("date_to"))), 200

@app.route("/api/llm/status", methods=["GET"])
@auth_required
def llm_status():
    return jsonify({"configured": llm_insights.is_configured(), "model": llm_insights.model_name(),
                    "provider": llm_insights.provider(), "hint": llm_insights.NOT_CONFIGURED}), 200

@app.route("/api/llm/insights", methods=["POST"])
@auth_required
def llm_insights_route():
    import database as db
    force = bool((request.get_json(silent=True) or {}).get("force"))
    try:
        result = llm_insights.generate(request.user["user_id"], db.get_records(request.user["user_id"], {}), force)
    except llm_insights.LLMNotConfigured as e:
        return jsonify({"error": str(e)}), 503
    except llm_insights.LLMError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(result), 200

@app.route("/api/forecast", methods=["GET"])
@auth_required
def forecast_route():
    import database as db
    return jsonify(forecast.compute_forecast(db.get_records(request.user["user_id"], {}))), 200

@app.route("/api/forecast/explain", methods=["POST"])
@auth_required
def forecast_explain_route():
    import database as db
    force = bool((request.get_json(silent=True) or {}).get("force"))
    fc = forecast.compute_forecast(db.get_records(request.user["user_id"], {}))
    try:
        return jsonify(forecast_ai.explain(request.user["user_id"], fc, force)), 200
    except llm_insights.LLMNotConfigured as e:
        return jsonify({"error": str(e)}), 503
    except llm_insights.LLMError as e:
        return jsonify({"error": str(e)}), 502

@app.route("/api/risk", methods=["GET"])
@auth_required
def risk_route():
    import database as db
    return jsonify(risk.summarize(db.get_records(request.user["user_id"], {}))), 200

@app.route("/api/income-streams", methods=["GET"])
@auth_required
def income_streams_route():
    import database as db
    return jsonify(income.summarize(db.get_records(request.user["user_id"], {}))), 200

@app.route("/api/counterparties", methods=["GET"])
@auth_required
def counterparties_route():
    import database as db
    return jsonify(counterparty.summarize(db.get_records(request.user["user_id"], {}))), 200

@app.route("/api/persona", methods=["GET"])
@auth_required
def persona_route():
    import database as db
    p = persona.compute_persona(db.get_records(request.user["user_id"], {}))
    return jsonify(persona_ai.attach(request.user["user_id"], p)), 200   # Gemini only if no rule matched

@app.route("/api/llm/chat", methods=["POST"])
@auth_required
def llm_chat_route():
    import database as db
    msgs = (request.get_json(silent=True) or {}).get("messages")
    try:
        result = llm_insights.chat(request.user["user_id"], db.get_records(request.user["user_id"], {}), msgs)
    except llm_insights.LLMNotConfigured as e:
        return jsonify({"error": str(e)}), 503
    except llm_insights.LLMError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(result), 200

@app.route("/api/ml/status", methods=["GET"])
@auth_required
def ml_status():
    import database as db
    ml = categorizer.train_for_user(db.get_labeled_records(request.user["user_id"]))
    return jsonify(ml.info), 200

@app.route("/api/ml/recategorize", methods=["POST"])
@auth_required
def ml_recategorize():
    return jsonify(importer.recategorize_user(request.user["user_id"])), 200

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5001)), debug=os.environ.get("FLASK_DEBUG") == "1")
