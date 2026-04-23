import os
import re
import hashlib
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

from visa_api_provider import get_visa_provider
from rag_data_provider import get_visa_info
from app.services.qdrant_service import QdrantService
from app.services.llm_service import LLMService
from app.services.user_service import UserService
from app.services.comparison_service import ComparisonService

load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")
CORS(app, supports_credentials=True, origins=os.getenv("ALLOWED_ORIGINS", "*").split(","))

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.getenv("REDIS_URL", "memory://")
)

# Services
qdrant_service = QdrantService()
llm_service = LLMService()
user_service = UserService()
comparison_service = ComparisonService()

CACHE = {}
CACHE_TIMEOUT = 1800

SUPPORTED_COUNTRIES = {"uk", "germany", "canada", "australia", "usa"}
SUPPORTED_NATIONALITIES = {"PK", "IN", "NG", "BD", "EG", "PH", "GH", "NP"}

SAMPLE_DOCUMENTS = [
    {
        "title": "UK Student Visa Requirements",
        "content": "UK Student Visa requires CAS from university, proof of funds, English language proficiency (IELTS), tuberculosis test results",
        "country": "uk", "visa_type": "student", "ielts_required": True,
        "fees": "£363", "processing_time": "3 weeks", "validity": "Course duration + 4 months"
    },
    {
        "title": "Germany Work Visa Information",
        "content": "Germany Work Visa requires job offer, qualifications recognition, health insurance",
        "country": "germany", "visa_type": "work", "ielts_required": False,
        "fees": "€75", "processing_time": "6-8 weeks", "validity": "Up to 4 years"
    },
    {
        "title": "Canada Tourist Visa Guide",
        "content": "Canada Tourist Visa requires passport, proof of ties to home country, financial statements",
        "country": "canada", "visa_type": "tourist", "ielts_required": False,
        "fees": "CAD 100", "processing_time": "40 days", "validity": "Up to 6 months"
    },
    {
        "title": "Australia Student Visa Details",
        "content": "Australia Student Visa requires Confirmation of Enrollment, genuine temporary entrant requirement, IELTS 6.0+, OSHC health insurance",
        "country": "australia", "visa_type": "student", "ielts_required": True,
        "fees": "AUD 650", "processing_time": "4-8 weeks", "validity": "Course duration"
    },
    {
        "title": "USA Work Visa (H1B)",
        "content": "USA H1B Work Visa requires employer sponsorship, specialty occupation, labor condition application",
        "country": "usa", "visa_type": "work", "ielts_required": False,
        "fees": "$190 + $500 fraud prevention", "processing_time": "2-6 months", "validity": "3 years renewable"
    }
]


def initialize_vector_store():
    """Seed Qdrant only if collection is empty (safe on restart)."""
    try:
        existing = qdrant_service.count_documents()
        if existing == 0:
            for doc in SAMPLE_DOCUMENTS:
                qdrant_service.index_document(doc)
            logger.info("Vector store seeded with %d documents.", len(SAMPLE_DOCUMENTS))
        else:
            logger.info("Vector store already contains %d documents. Skipping seed.", existing)
    except Exception as e:
        logger.error("Failed to initialize vector store: %s", e)


initialize_vector_store()


# =========================
# HELPERS
# =========================

def normalize_query(query: str) -> str:
    """Lowercase, strip whitespace, remove HTML tags."""
    query = re.sub(r"<[^>]+>", "", query)  # strip HTML
    return " ".join(query.lower().split())


def cache_key(query: str, user_id: str = None) -> str:
    normalized = normalize_query(query)
    key = f"{normalized}_{user_id}" if user_id else normalized
    return hashlib.md5(key.encode()).hexdigest()


def get_cache(key: str):
    if key in CACHE:
        data, ts = CACHE[key]
        if datetime.now() - ts < timedelta(seconds=CACHE_TIMEOUT):
            return data
        del CACHE[key]
    return None


def set_cache(key: str, value):
    CACHE[key] = (value, datetime.now())


def validate_query(query: str) -> tuple[bool, str]:
    if not query:
        return False, "Query cannot be empty."
    if len(query) > 500:
        return False, "Query is too long (max 500 characters)."
    if re.search(r"[<>\"'%;()&+]", query):
        return False, "Query contains invalid characters."
    return True, ""


def detect_country(query: str) -> str | None:
    q = query.lower()
    mapping = {
        "uk": ["uk", "britain", "united kingdom", "england"],
        "germany": ["germany", "deutschland", "german"],
        "canada": ["canada", "canadian"],
        "australia": ["australia", "australian"],
        "usa": ["usa", "america", "united states", "us visa"]
    }
    for country, keywords in mapping.items():
        if any(kw in q for kw in keywords):
            return country
    return None


def detect_visa_type(query: str) -> str:
    q = query.lower()
    if "student" in q or "study" in q or "university" in q:
        return "student"
    if "work" in q or "job" in q or "employment" in q or "h1b" in q:
        return "work"
    if "tourist" in q or "visit" in q or "holiday" in q or "vacation" in q:
        return "tourist"
    if "business" in q:
        return "business"
    if "family" in q or "spouse" in q or "dependent" in q:
        return "family"
    return "tourist"


def detect_nationality(query: str) -> str:
    """Extract nationality from query or default to PK."""
    q = query.lower()
    nationality_map = {
        "IN": ["indian", "india"],
        "NG": ["nigerian", "nigeria"],
        "BD": ["bangladeshi", "bangladesh"],
        "PH": ["filipino", "philippines"],
        "GH": ["ghanaian", "ghana"],
        "NP": ["nepali", "nepal"],
    }
    for code, keywords in nationality_map.items():
        if any(kw in q for kw in keywords):
            return code
    return "PK"  # default


def safe_error(message: str, details: str = None, status: int = 500):
    """Return error response without leaking internals in production."""
    resp = {"error": message}
    if os.getenv("FLASK_ENV") == "development" and details:
        resp["details"] = details
    return jsonify(resp), status


# =========================
# DATA FUSION
# =========================

def fuse_data(api_data: dict, local_data: dict, query: str, semantic_results: list = None) -> dict:
    is_ielts = "ielts" in query.lower() or "english proficiency" in query.lower()

    response = {
        "country": api_data.get("destination", {}).get("name", "Unknown"),
        "visa_type": detect_visa_type(query),
        "confidence": api_data.get("confidence", "medium"),
        "realtime": {
            "visa_requirement": api_data.get("requirement", "Check embassy"),
            "passport_validity": api_data.get("passport_validity", "6 months")
        },
        "fees": "",
        "processing_time_note": "",
        "validity_note": "",
        "requirements": [],
        "sources": [],
        "disclaimer": "This information is for guidance only. Always verify with the official embassy or immigration authority."
    }

    if local_data:
        response["fees"] = local_data.get("fees", "")
        response["processing_time_note"] = local_data.get("processing_time", "")
        response["validity_note"] = local_data.get("validity", "")
        response["requirements"] = local_data.get("requirements", [])

    if semantic_results:
        seen_reqs = set(response["requirements"])
        for result in semantic_results:
            for req in result.get("requirements", []):
                if req not in seen_reqs:
                    response["requirements"].append(req)
                    seen_reqs.add(req)
            if not response["fees"] and result.get("fees"):
                response["fees"] = result["fees"]
            if not response["processing_time_note"] and result.get("processing_time"):
                response["processing_time_note"] = result["processing_time"]
            response["sources"].append({
                "name": "Semantic Search",
                "relevance": result.get("title", "Related information")
            })

    response["validity_note"] = response["validity_note"] or api_data.get("description", "Varies")
    response["fees"] = response["fees"] or "Contact embassy"
    response["processing_time_note"] = response["processing_time_note"] or "Varies"

    if api_data.get("embassy_url"):
        response["sources"].append({"name": "Official Source", "url": api_data["embassy_url"]})

    if is_ielts:
        response["question_type"] = "ielts"
        if local_data and local_data.get("ielts_required") is not None:
            required = local_data["ielts_required"]
            response["direct_answer"] = (
                "Yes, IELTS is required." if required
                else "No, IELTS is not mandatory but may be recommended."
            )
        else:
            ielts_found = any("ielts" in str(r).lower() for r in (semantic_results or []))
            response["direct_answer"] = (
                "IELTS is typically required for this visa category." if ielts_found
                else "IELTS is usually required — confirm with the official immigration authority."
            )
        response["specific_details"] = [
            "English proficiency is required for most student visas",
            "IELTS is widely accepted but alternatives may exist (TOEFL, PTE)",
            "Some universities accept Medium of Instruction (MOI) letters",
            "Always confirm requirements with the official immigration authority"
        ]

    return response


# =========================
# ROUTES
# =========================

@app.route("/api/ask", methods=["POST"])
@limiter.limit("30 per hour")
def ask():
    try:
        data = request.get_json(silent=True)
        if not data:
            return safe_error("Invalid JSON body.", status=400)

        query = data.get("query", "").strip()
        session_id = data.get("session_id", request.headers.get("X-Session-ID", "anonymous"))

        valid, reason = validate_query(query)
        if not valid:
            return safe_error(reason, status=400)

        user_id = user_service.get_user_id(session_id)

        key = cache_key(query, user_id)
        cached = get_cache(key)
        if cached:
            cached["from_cache"] = True
            return jsonify(cached)

        country = detect_country(query)
        visa_type = detect_visa_type(query)
        nationality = detect_nationality(query)

        if not country:
            return safe_error(
                "Country not detected. Please mention a country (e.g. UK, USA, Canada, Australia, Germany).",
                status=400
            )

        provider = get_visa_provider()
        nationality = detect_nationality(query)
        api_data = provider.get_visa_requirement(destination=country, nationality=nationality)
        local_data = get_visa_info(country, visa_type)
        semantic_results = qdrant_service.semantic_search(query, country, visa_type, limit=3)
        user_history = user_service.get_user_history(user_id)
        user_profile = user_service.get_user_profile(user_id)

        response = fuse_data(api_data, local_data, query, semantic_results)
        summary = llm_service.summarize_visa_info(response, query)
        response["summary"] = summary
        personalized = llm_service.personalize_response(response, user_history, user_profile)

        user_service.add_to_history(user_id, query, personalized)
        set_cache(key, personalized)

        return jsonify(personalized)

    except Exception as e:
        logger.exception("Error in /api/ask")
        return safe_error("Unable to process your request. Please try again.", str(e))


@app.route("/api/compare", methods=["POST"])
@limiter.limit("15 per hour")
def compare_countries():
    try:
        data = request.get_json(silent=True)
        if not data:
            return safe_error("Invalid JSON body.", status=400)

        countries = [c.lower().strip() for c in data.get("countries", [])]
        visa_type = data.get("visa_type", "tourist")
        query = data.get("query", "")
        session_id = data.get("session_id", request.headers.get("X-Session-ID", "anonymous"))

        if len(countries) < 2:
            return safe_error("Provide at least 2 countries to compare.", status=400)

        invalid = [c for c in countries if c not in SUPPORTED_COUNTRIES]
        if invalid:
            return safe_error(
                f"Unsupported countries: {', '.join(invalid)}. Supported: {', '.join(SUPPORTED_COUNTRIES)}.",
                status=400
            )

        user_id = user_service.get_user_id(session_id)
        countries_data = []

        for country in countries:
            provider = get_visa_provider()
            nationality = data.get("nationality", detect_nationality(query))
            api_data = provider.get_visa_requirement(destination=country, nationality=nationality)
            local_data = get_visa_info(country, visa_type)
            semantic_results = qdrant_service.semantic_search(
                f"{visa_type} visa requirements", country, visa_type, limit=2
            )
            countries_data.append(fuse_data(api_data, local_data, f"{visa_type} visa {country}", semantic_results))

        comparison = comparison_service.compare_countries(countries_data)
        llm_comparison = llm_service.compare_countries(
            countries_data, query or f"Compare {visa_type} visas for {', '.join(countries)}"
        )

        user_profile = user_service.get_user_profile(user_id)
        preferences = {
            "cost_importance": user_profile.get("cost_importance", 0.3),
            "speed_importance": user_profile.get("speed_importance", 0.3),
            "requirements_importance": user_profile.get("requirements_importance", 0.4)
        }
        rankings = comparison_service.get_country_rankings(countries_data, preferences)

        result = {
            "comparison": comparison,
            "llm_analysis": llm_comparison,
            "personalized_rankings": rankings,
            "countries_compared": countries,
            "disclaimer": "Information is for guidance only. Verify with official embassy sources."
        }

        user_service.add_to_history(user_id, f"Compare {visa_type} visas for {', '.join(countries)}", result)
        return jsonify(result)

    except Exception as e:
        logger.exception("Error in /api/compare")
        return safe_error("Comparison failed. Please try again.", str(e))


@app.route("/api/history", methods=["GET"])
@limiter.limit("60 per hour")
def get_history():
    try:
        session_id = request.headers.get("X-Session-ID", "anonymous")
        user_id = user_service.get_user_id(session_id)
        limit = min(int(request.args.get("limit", 10)), 50)  # cap at 50
        history = user_service.get_user_history(user_id, limit)
        return jsonify({"history": history})
    except Exception as e:
        logger.exception("Error in /api/history")
        return safe_error("Failed to retrieve history.", str(e))


@app.route("/api/profile", methods=["GET", "POST"])
@limiter.limit("30 per hour")
def user_profile():
    try:
        session_id = request.headers.get("X-Session-ID", "anonymous")
        user_id = user_service.get_user_id(session_id)

        if request.method == "GET":
            profile = user_service.get_user_profile(user_id)
            return jsonify(profile)

        preferences = request.get_json(silent=True)
        if not preferences:
            return safe_error("Invalid preferences data.", status=400)
        user_service.update_preferences(user_id, preferences)
        return jsonify({"message": "Preferences updated successfully."})

    except Exception as e:
        logger.exception("Error in /api/profile")
        return safe_error("Failed to process profile.", str(e))


@app.route("/api/semantic-search", methods=["POST"])
@limiter.limit("20 per hour")
def semantic_search():
    try:
        data = request.get_json(silent=True)
        if not data:
            return safe_error("Invalid JSON body.", status=400)

        query = data.get("query", "").strip()
        valid, reason = validate_query(query)
        if not valid:
            return safe_error(reason, status=400)

        country = data.get("country")
        visa_type = data.get("visa_type")
        limit = min(int(data.get("limit", 5)), 10)

        results = qdrant_service.semantic_search(query, country, visa_type, limit)
        return jsonify({"results": results})

    except Exception as e:
        logger.exception("Error in /api/semantic-search")
        return safe_error("Search failed.", str(e))


@app.route("/api/recommendations", methods=["GET"])
@limiter.limit("30 per hour")
def get_recommendations():
    try:
        session_id = request.headers.get("X-Session-ID", "anonymous")
        user_id = user_service.get_user_id(session_id)

        user_history = user_service.get_user_history(user_id)
        user_profile = user_service.get_user_profile(user_id)
        popular_queries = user_service.get_popular_queries(limit=5)

        recommendations = {
            "based_on_history": [],
            "popular_queries": popular_queries,
            "suggested_countries": user_profile.get("preferred_countries", []),
            "suggested_visa_types": user_profile.get("preferred_visa_types", [])
        }

        if user_history:
            last_country = user_history[0].get("country")
            if last_country:
                recommendations["based_on_history"].append({
                    "type": "similar_country",
                    "suggestion": f"Explore other visa types for {last_country.title()}"
                })

        return jsonify(recommendations)

    except Exception as e:
        logger.exception("Error in /api/recommendations")
        return safe_error("Failed to get recommendations.", str(e))


@app.route("/api/health")
def health():
    """Basic health check — does not expose service topology in production."""
    if os.getenv("FLASK_ENV") == "development":
        return jsonify({
            "status": "ok",
            "services": {
                "qdrant": "connected",
                "llm": llm_service.provider,
                "redis": "connected" if user_service.redis_client.ping() else "disconnected"
            }
        })
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    debug = os.getenv("FLASK_ENV") == "development"
    app.run(debug=debug, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))