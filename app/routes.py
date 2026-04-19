from flask import Blueprint, request, jsonify, render_template
from app.services.intent_service import IntentService
from app.services.rag_service import RAGService
from app.services.validation_service import ValidationService
from app.services.response_service import ResponseService
from app.services.confidence_service import ConfidenceService
from app import limiter
import json
import os
from datetime import datetime
import hashlib

api = Blueprint("api", __name__)

# Initialize services
intent_service = IntentService()
rag_service = RAGService()
validation_service = ValidationService()
response_service = ResponseService()
confidence_service = ConfidenceService()

# Simple cache
response_cache = {}
CACHE_TIMEOUT = 3600

def load_country_data(country_code):
    """Load country data from JSON file"""
    try:
        file_path = os.path.join('app', 'data', 'countries', f'{country_code}.json')
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error loading {country_code}.json: {e}")
        return None

def get_cache_key(query, country, visa_type, is_pakistani):
    """Generate cache key"""
    key_string = f"{query}_{country}_{visa_type}_{is_pakistani}"
    return hashlib.md5(key_string.encode()).hexdigest()

@api.route("/")
def home():
    return render_template("index.html")

@api.route("/api/ask", methods=["POST"])
@limiter.limit("10 per minute")
def ask():
    """Main API endpoint for visa queries"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        query = data.get("query", "").strip()
        
        # Validate input
        is_valid, validation_message = validation_service.validate_input(query)
        if not is_valid:
            return jsonify({"error": validation_message}), 400
        
        if not query:
            return jsonify({"error": "Query required"}), 400
        
        # Detect intent
        intent = intent_service.detect_intent(query)
        
        if intent["country"] == "unknown":
            return jsonify({
                "error": "Country not detected",
                "message": "Please specify a country in your query",
                "available_countries": intent_service.get_available_countries()
            }), 400
        
        # Check cache
        cache_key = get_cache_key(
            query, 
            intent["country"], 
            intent["visa_type"], 
            intent["is_pakistani"]
        )
        
        if cache_key in response_cache:
            cached = response_cache[cache_key]
            if (datetime.now() - cached['timestamp']).seconds < CACHE_TIMEOUT:
                return jsonify(cached['data'])
        
        # Load country data
        country_data = load_country_data(intent["country"])
        
        if not country_data:
            return jsonify({
                "error": "Data not available",
                "message": f"Visa information for {intent['country']} is not available"
            }), 404
        
        # Build context based on intent
        context = rag_service.build_context(country_data, intent["visa_type"])
        
        # Generate response
        response = response_service.generate_response(
            query=query,
            intent=intent,
            context=context,
            country_data=country_data
        )
        
        # Calculate confidence
        confidence = confidence_service.calculate_confidence(
            country_data=country_data,
            context=context,
            intent=intent
        )
        response["confidence"] = confidence
        
        # Validate response
        response = validation_service.validate_response(response, country_data)
        
        # Add timestamp
        response["timestamp"] = datetime.now().isoformat()
        
        # Cache response
        response_cache[cache_key] = {
            'data': response,
            'timestamp': datetime.now()
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in /api/ask: {e}")
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500

@api.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "message": "Visa RAG system is running",
        "cache_size": len(response_cache),
        "timestamp": datetime.now().isoformat()
    })

@api.route("/api/countries", methods=["GET"])
def list_countries():
    """List all available countries"""
    countries = []
    data_dir = os.path.join('app', 'data', 'countries')
    
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if filename.endswith('.json'):
                country_code = filename.replace('.json', '')
                country_data = load_country_data(country_code)
                if country_data:
                    countries.append({
                        "code": country_code,
                        "name": country_data.get("country", country_code),
                        "last_updated": country_data.get("last_updated", "Unknown"),
                        "visa_types": list(country_data.get("visas", {}).keys())
                    })
    
    return jsonify({
        "countries": countries,
        "total": len(countries),
        "timestamp": datetime.now().isoformat()
    })

@api.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please try again later.",
        "limit": "10 requests per minute"
    }), 429