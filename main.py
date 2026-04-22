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

CACHE = {}
CACHE_TIMEOUT = 1800


# =========================
# CACHE
# =========================
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
        "us": ["usa", "america", "united states"],
        "uk": ["uk", "britain", "united kingdom", "england"],
        "germany": ["germany"],
        "canada": ["canada"],
        "australia": ["australia"],
        "uae": ["uae", "dubai", "emirates"],
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
# LOAD LOCAL JSON
# =========================
def load_country_data(country):
    try:
        path = f"visa_data/{country}.json"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return None


# =========================
# FORMAT RESPONSE (FIXED)
# =========================
def format_response(api_result, query, country, visa_type):
    is_ielts = "ielts" in query.lower()

    # API fields
    visa_requirement = api_result.get("requirement", "Check embassy")
    passport_validity = api_result.get("passport_validity", "6 months recommended")
    description = api_result.get("description", "Varies")

    # Load local data
    local_data = load_country_data(country)

    response = {
        "country": api_result.get("destination", {}).get("name", country.title()),
        "visa_type": visa_type,
        "confidence": api_result.get("confidence", "medium"),

        "realtime": {
            "visa_requirement": visa_requirement,
            "passport_validity": passport_validity
        },

        "fees": "Contact embassy",
        "processing_time_note": "Varies",
        "validity_note": description,

        "requirements": [],
        "sources": []
    }

    # =========================
    # LOCAL DATA MERGE
    # =========================
    if local_data and visa_type in local_data.get("visas", {}):
        visa_info = local_data["visas"][visa_type]

        response["requirements"] = visa_info.get("requirements", [])
        response["fees"] = visa_info.get("fees", response["fees"])
        response["processing_time_note"] = visa_info.get("processing_time", "Varies")
        response["validity_note"] = visa_info.get("validity", description)

        response["sources"] = local_data.get("sources", [])

    # =========================
    # IELTS HANDLING
    # =========================
    if is_ielts:
        response["question_type"] = "ielts"

        if local_data and visa_type in local_data.get("visas", {}):
            ielts_required = local_data["visas"][visa_type].get("ielts_required")

            if ielts_required is True:
                answer = "Yes, IELTS is generally required."
            elif ielts_required is False:
                answer = "No, IELTS is not strictly required."
            else:
                answer = "Depends on university requirements."
        else:
            answer = "Depends on university and visa requirements."

        response["direct_answer"] = answer

        response["specific_details"] = [
            "English proficiency is required for most student visas",
            "IELTS is widely accepted but alternatives may exist",
            "Some universities accept MOI or other tests",
            "Always confirm with official immigration authority"
        ]

    return response


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

        # ✅ FIXED CALL
        response = format_response(api_result, query, country, visa_type)

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
    app.run(host="0.0.0.0", port=5000, debug=True)