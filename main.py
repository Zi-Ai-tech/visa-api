import os
import json
import re
import hashlib
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from visa_api_provider import get_visa_provider

app = Flask(__name__)
CORS(app)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100/day", "30/hour"],
    storage_uri="memory://"
)

# =========================
# CACHE SYSTEM
# =========================
CACHE = {}
CACHE_TIMEOUT = 1800  # 30 min


def cache_key(query):
    return hashlib.md5(query.encode()).hexdigest()


def get_cache(key):
    if key in CACHE:
        data, ts = CACHE[key]
        if datetime.now() - ts < timedelta(seconds=CACHE_TIMEOUT):
            return data
    return None


def set_cache(key, value):
    CACHE[key] = (value, datetime.now())


# =========================
# VALIDATION
# =========================
def validate(query):
    if not query or len(query) > 500:
        return False
    if re.search(r'<script|DROP|SELECT', query, re.I):
        return False
    return True


# =========================
# DETECTION
# =========================
def detect_country(query):
    query = query.lower()
    mapping = {
        "us": ["usa", "america"],
        "uk": ["uk", "britain"],
        "germany": ["germany"],
        "canada": ["canada"],
        "australia": ["australia"],
        "uae": ["uae", "dubai"]
    }
    for k, v in mapping.items():
        if any(x in query for x in v):
            return k
    return None


def detect_visa_type(query):
    query = query.lower()
    if "student" in query:
        return "student"
    if "work" in query:
        return "work"
    if "tourist" in query or "visit" in query:
        return "tourist"
    return "unknown"


# =========================
# TRUST LAYER
# =========================
def build_trust(api_result):
    return {
        "last_updated": api_result.get("last_updated"),
        "confidence": api_result.get("confidence"),
        "source": api_result.get("source"),
        "note": "Always verify with official embassy."
    }


# =========================
# FORMAT RESPONSE
# =========================
def format_response(query, country, visa_type, api_result):

    return {
        "query": query,
        "country": api_result["destination"]["name"],
        "visa_type": visa_type,

        "summary": {
            "visa_requirement": api_result.get("requirement"),
            "description": api_result.get("description"),
        },

        "details": {
            "passport_validity": api_result.get("passport_validity"),
            "requirements": api_result.get("primary_rule", {}),
        },

        "trust": build_trust(api_result)
    }


# =========================
# MAIN API
# =========================
@app.route("/api/ask", methods=["POST"])
@limiter.limit("10/minute")
def ask():
    try:
        data = request.get_json()
        query = data.get("query", "").strip()

        if not validate(query):
            return jsonify({"error": "Invalid query"}), 400

        key = cache_key(query)
        cached = get_cache(key)
        if cached:
            cached["cached"] = True
            return jsonify(cached)

        country = detect_country(query)
        visa_type = detect_visa_type(query)

        if not country:
            return jsonify({"error": "Country not detected"}), 400

        if visa_type == "unknown":
            return jsonify({"error": "Specify visa type"}), 400

        provider = get_visa_provider()
        api_result = provider.get_visa_requirement(destination=country, nationality="PK")

        response = format_response(query, country, visa_type, api_result)

        set_cache(key, response)

        return jsonify(response)

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": "Internal error"}), 500


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat()
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)