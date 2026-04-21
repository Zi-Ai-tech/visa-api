import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import json
import re
from datetime import datetime
import hashlib
from visa_api_provider import get_visa_provider, VisaAPIProvider

app = Flask(__name__)
CORS(app)

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day", "30 per hour"],
    storage_uri="memory://"
)

# Simple in-memory cache
response_cache = {}
CACHE_TIMEOUT = 3600  # 1 hour

# ============================================
# COUNTRY-SPECIFIC RULES ENGINE
# ============================================

class VisaRulesEngine:
    """Country-specific rules to avoid generic templates"""
    
    @staticmethod
    def get_rules(country_code, visa_type):
        """Get country-specific rules"""
        rules = {
            "us": {
                "requires_visa_type_clarification": True,
                "interview_important": True,
                "administrative_processing_risk": "221(g) possible",
                "validity_note": "Up to 5-10 years at officer's discretion, not guaranteed",
                "entry_duration": "Usually 6 months per visit",
                "refusal_risk": "Moderate to High for Pakistani applicants",
                "documents_approach": "focus_on_ties_not_checklist",
                "processing_time_note": "Wait times vary significantly by consulate (Islamabad/Karachi) and can range from weeks to months"
            },
            "uk": {
                "requires_visa_type_clarification": True,
                "interview_important": False,
                "validity_note": "2, 5, or 10 years depending on visa type",
                "documents_approach": "checklist_based",
                "processing_time_note": "Standard: 3 weeks, Priority: 5 days, Super Priority: 24 hours"
            },
            "canada": {
                "requires_visa_type_clarification": True,
                "interview_important": False,
                "validity_note": "Up to 10 years or passport expiry",
                "documents_approach": "checklist_based",
                "processing_time_note": "Varies by country, check IRCC website for current times"
            },
            "ireland": {
                "requires_visa_type_clarification": True,
                "interview_important": False,
                "validity_note": "Usually 90 days for tourist, 1 year for student",
                "documents_approach": "checklist_based"
            },
            "australia": {
                "requires_visa_type_clarification": True,
                "interview_important": False,
                "validity_note": "3, 6, or 12 months for tourist",
                "documents_approach": "online_assessment"
            },
            "germany": {
                "requires_visa_type_clarification": True,
                "interview_important": True,
                "validity_note": "90 days within 180-day period (Schengen)",
                "documents_approach": "strict_checklist"
            }
        }
        
        # Default rules for countries not explicitly defined
        default_rules = {
            "requires_visa_type_clarification": True,
            "interview_important": False,
            "validity_note": "Varies by visa type and consular discretion",
            "documents_approach": "checklist_based",
            "processing_time_note": "Contact embassy for current processing times"
        }
        
        return rules.get(country_code, default_rules)

# ============================================
# DATA LOADING FUNCTIONS
# ============================================

def load_scraped_data():
    """Load visa data from scraped JSON files"""
    visa_data = {}
    data_dir = "visa_data"
    
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if filename.endswith('.json') and not filename.startswith('_'):
                country_code = filename.replace('.json', '')
                file_path = os.path.join(data_dir, filename)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    visa_data[country_code] = {
                        "country": data.get("country", country_code),
                        "visa_types": data.get("visas", {}),
                        "last_updated": data.get("last_updated", data.get("last_scraped", "Unknown")),
                        "source_type": "scraped",
                        "sources": data.get("sources", [])
                    }
                    
                    print(f"✅ Loaded {country_code}: {data.get('country')}")
                    
                except Exception as e:
                    print(f"❌ Error loading {filename}: {e}")
    
    return visa_data

def load_official_sources():
    """Load official sources with REAL URLs"""
    sources = {}
    data_dir = "visa_data"
    
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if filename.endswith('.json') and not filename.startswith('_'):
                country_code = filename.replace('.json', '')
                file_path = os.path.join(data_dir, filename)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    source_list = data.get("sources", [])
                    if source_list:
                        sources[country_code] = source_list
                except:
                    pass
    
    # Add verified official sources (NEVER fake sources)
    VERIFIED_SOURCES = {
        "us": [
            {
                "name": "U.S. Department of State - Bureau of Consular Affairs",
                "url": "https://travel.state.gov/content/travel/en/us-visas.html",
                "type": "official",
                "domain": ".gov"
            },
            {
                "name": "U.S. Embassy Islamabad",
                "url": "https://pk.usembassy.gov/visas/",
                "type": "official",
                "domain": ".gov"
            }
        ],
        "uk": [
            {
                "name": "UK Visas and Immigration",
                "url": "https://www.gov.uk/browse/visas-immigration",
                "type": "official",
                "domain": ".gov.uk"
            }
        ],
        "canada": [
            {
                "name": "Immigration, Refugees and Citizenship Canada",
                "url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/visit-canada.html",
                "type": "official",
                "domain": ".gc.ca"
            }
        ],
        "ireland": [
            {
                "name": "Irish Immigration Service",
                "url": "https://www.irishimmigration.ie/coming-to-visit-ireland/",
                "type": "official",
                "domain": ".ie"
            }
        ],
        "australia": [
            {
                "name": "Department of Home Affairs",
                "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/visitor-600",
                "type": "official",
                "domain": ".gov.au"
            }
        ],
        "germany": [
            {
                "name": "German Federal Foreign Office",
                "url": "https://www.auswaertiges-amt.de/en/visa-service",
                "type": "official",
                "domain": ".de"
            }
        ]
    }
    
    # Merge scraped sources with verified sources
    for country_code, verified in VERIFIED_SOURCES.items():
        if country_code not in sources:
            sources[country_code] = verified
    
    return sources

# ============================================
#  FALLBACK DATA (Minimal - only for emergencies)
# ============================================

FALLBACK_VISA_DATA = {
    "us": {
        "country": "United States",
        "visa_types": {
            "tourist": {
                "name": "B1/B2 Visitor Visa",
                "requirements": [
                    "Valid passport (6 months beyond intended stay)",
                    "DS-160 confirmation page",
                    "Interview appointment letter",
                    "Proof of financial ability",
                    "Evidence of ties to home country"
                ],
                "processing_time_note": "Wait times vary significantly by consulate (Islamabad/Karachi) and can range from weeks to months",
                "fees": "$185 USD",
                "validity_note": "Up to 5-10 years at officer's discretion, not guaranteed. Entry usually 6 months per visit."
            }
        }
    }
}

# ============================================
# LOAD DATA
# ============================================

print("📂 Loading visa data...")
VISA_DATA = load_scraped_data()

if not VISA_DATA:
    print("⚠️ No scraped data found, using fallback data")
    VISA_DATA = FALLBACK_VISA_DATA
else:
    print(f"✅ Loaded {len(VISA_DATA)} countries from scraped data")

print("🔗 Loading official sources...")
OFFICIAL_SOURCES = load_official_sources()
print(f"✅ Loaded sources for {len(OFFICIAL_SOURCES)} countries")

# ============================================
# PAKISTANI-SPECIFIC DETAILED REQUIREMENTS
# ============================================

PAKISTANI_DETAILED = {
    "us": {
        "tourist": {
            "requirements": [
                "Valid Pakistani passport (6+ months validity beyond intended stay)",
                "Detailed travel history (last 5 years)",
                "Property/asset documents in Pakistan",
                "Family ties evidence (marriage/birth certificates)",
                "Employment letter with approved leave",
                "Bank statements (6 months, consistent income)"
            ],
            "financial_requirements": [
                "Minimum $10,000 in liquid funds (recommended)",
                "6 months of personal/business bank statements",
                "Tax returns for last 2 years (if applicable)"
            ],
            "refusal_risk": "Moderate to High",
            "important_notes": [
                "Visa approval is NOT guaranteed",
                "Applicant must satisfy consular officer of intent to return to Pakistan",
                "Administrative processing (221g) may delay decision by weeks or months",
                "Previous travel history to US/UK/Schengen helps"
            ],
            "interview_tips": [
                "Be honest and consistent in answers",
                "Show strong ties to Pakistan (family, property, job)",
                "Don't purchase tickets before visa approval"
            ]
        },
        "student": {
            "requirements": [
                "I-20 from SEVP-approved institution",
                "SEVIS fee payment receipt",
                "Strong academic background",
                "Clear study plan and post-study intentions"
            ],
            "ielts_required": True,
            "ielts_score": "6.5 overall minimum (varies by institution)",
            "financial_requirements": [
                "Proof of first year tuition + living expenses",
                "Sponsor's bank statements (6 months)",
                "Affidavit of support (if sponsored)"
            ],
            "refusal_risk": "Moderate",
            "important_notes": [
                "Must demonstrate intent to return after studies",
                "Apply 3-4 months before program start",
                "Visa may be denied under Section 214(b) if ties not proven"
            ]
        },
        "work": {
            "requirements": [
                "Approved I-129 petition from US employer",
                "Labor Condition Application (LCA) approval",
                "Educational/professional qualifications",
                "Experience letters"
            ],
            "processing_note": "H-1B cap subject to annual lottery (usually March)",
            "refusal_risk": "Moderate"
        }
    },
    "uk": {
        "student": {
            "requirements": [
                "CAS from licensed UK institution",
                "Tuberculosis test certificate (mandatory)",
                "Police registration upon arrival"
            ],
            "ielts_required": True,
            "ielts_score": "5.5-6.5 depending on course",
            "ielts_note": "MUST be IELTS for UKVI (Academic) - regular IELTS not accepted",
            "financial_requirements": [
                "£1,334 per month (outside London) for up to 9 months",
                "£1,023 per month (inside London)",
                "Funds must be held for 28 consecutive days"
            ]
        }
    },
    "canada": {
        "tourist": {
            "requirements": [
                "Valid Pakistani passport",
                "Proof of funds (min $1,000 CAD per month)",
                "Purpose of travel statement",
                "Ties to Pakistan (property, family, job)"
            ],
            "financial_requirements": [
                "Bank statements (4 months)",
                "Employment letter with salary",
                "Property documents (recommended)"
            ],
            "important_notes": [
                "Biometrics mandatory for all Pakistani applicants",
                "Processing times longer for Pakistani citizens",
                "Previous Canada/US travel history helps"
            ]
        }
    }
}

# ============================================
#  COUNTRY DETECTION KEYWORDS
# ============================================

COUNTRY_KEYWORDS = {
"us": ["us", "usa", "united states", "america", "american", "u.s.", "u.s.a", "united states of america"],
    "canada": ["canada", "canadian", "ca"],
    "mexico": ["mexico", "mexican", "mx"],
    
    # United Kingdom & Ireland
    "uk": ["uk", "united kingdom", "britain", "british", "england", "great britain", "gb", "u.k."],
    "ireland": ["ireland", "irish", "ie", "republic of ireland"],
    
    # Western Europe
    "france": ["france", "french", "fr"],
    "germany": ["germany", "german", "deutschland", "de"],
    "italy": ["italy", "italian", "it"],
    "spain": ["spain", "spanish", "es", "españa"],
    "portugal": ["portugal", "portuguese", "pt"],
    "netherlands": ["netherlands", "dutch", "holland", "nl", "the netherlands"],
    "belgium": ["belgium", "belgian", "be"],
    "switzerland": ["switzerland", "swiss", "ch"],
    "austria": ["austria", "austrian", "at"],
    "sweden": ["sweden", "swedish", "se"],
    "norway": ["norway", "norwegian", "no"],
    "denmark": ["denmark", "danish", "dk"],
    "finland": ["finland", "finnish", "fi"],
    "greece": ["greece", "greek", "gr"],
    
    # Eastern Europe
    "poland": ["poland", "polish", "pl"],
    "czech_republic": ["czech republic", "czech", "czechia", "cz"],
    "hungary": ["hungary", "hungarian", "hu"],
    "romania": ["romania", "romanian", "ro"],
    "bulgaria": ["bulgaria", "bulgarian", "bg"],
    "croatia": ["croatia", "croatian", "hr"],
    "slovakia": ["slovakia", "slovak", "sk"],
    "slovenia": ["slovenia", "slovenian", "si"],
    "estonia": ["estonia", "estonian", "ee"],
    "latvia": ["latvia", "latvian", "lv"],
    "lithuania": ["lithuania", "lithuanian", "lt"],
    "ukraine": ["ukraine", "ukrainian", "ua"],
    "serbia": ["serbia", "serbian", "rs"],
    
    # Asia - East
    "japan": ["japan", "japanese", "jp"],
    "china": ["china", "chinese", "cn", "prc"],
    "south_korea": ["south korea", "korea", "korean", "kr", "rok"],
    "taiwan": ["taiwan", "taiwanese", "tw"],
    "hong_kong": ["hong kong", "hongkong", "hk"],
    "mongolia": ["mongolia", "mongolian", "mn"],
    
    # Asia - Southeast
    "thailand": ["thailand", "thai", "th"],
    "vietnam": ["vietnam", "vietnamese", "vn"],
    "indonesia": ["indonesia", "indonesian", "id", "bali"],
    "malaysia": ["malaysia", "malaysian", "my"],
    "singapore": ["singapore", "singaporean", "sg"],
    "philippines": ["philippines", "filipino", "philippine", "ph", "pilipinas"],
    "cambodia": ["cambodia", "cambodian", "kh"],
    "laos": ["laos", "laotian", "la"],
    "myanmar": ["myanmar", "burma", "burmese", "mm"],
    "brunei": ["brunei", "bruneian", "bn"],
    
    # Asia - South
    "india": ["india", "indian", "in", "bharat"],
    "pakistan": ["pakistan", "pakistani", "pk"],
    "bangladesh": ["bangladesh", "bangladeshi", "bd"],
    "sri_lanka": ["sri lanka", "sri lankan", "lk", "ceylon"],
    "nepal": ["nepal", "nepalese", "np"],
    "bhutan": ["bhutan", "bhutanese", "bt"],
    "maldives": ["maldives", "maldivian", "mv"],
    
    # Middle East
    "uae": ["uae", "dubai", "emirates", "abu dhabi", "united arab emirates", "ae"],
    "saudi_arabia": ["saudi arabia", "saudi", "ksa", "sa"],
    "qatar": ["qatar", "qatari", "qa", "doha"],
    "kuwait": ["kuwait", "kuwaiti", "kw"],
    "bahrain": ["bahrain", "bahraini", "bh"],
    "oman": ["oman", "omani", "om", "muscat"],
    "jordan": ["jordan", "jordanian", "jo"],
    "lebanon": ["lebanon", "lebanese", "lb"],
    "israel": ["israel", "israeli", "il"],
    "palestine": ["palestine", "palestinian", "ps"],
    "iraq": ["iraq", "iraqi", "iq"],
    "iran": ["iran", "iranian", "ir", "persia"],
    "yemen": ["yemen", "yemeni", "ye"],
    "syria": ["syria", "syrian", "sy"],
    
    # Central Asia
    "turkey": ["turkey", "turkish", "tr", "türkiye", "turkiye"],
    "kazakhstan": ["kazakhstan", "kazakh", "kz"],
    "uzbekistan": ["uzbekistan", "uzbek", "uz"],
    "azerbaijan": ["azerbaijan", "azerbaijani", "az"],
    "georgia": ["georgia", "georgian", "ge"],
    "armenia": ["armenia", "armenian", "am"],
    
    # Oceania
    "australia": ["australia", "australian", "au", "oz"],
    "new_zealand": ["new zealand", "nz", "kiwi", "aotearoa"],
    "fiji": ["fiji", "fijian", "fj"],
    
    # Africa - North
    "egypt": ["egypt", "egyptian", "eg"],
    "morocco": ["morocco", "moroccan", "ma"],
    "algeria": ["algeria", "algerian", "dz"],
    "tunisia": ["tunisia", "tunisian", "tn"],
    "libya": ["libya", "libyan", "ly"],
    "sudan": ["sudan", "sudanese", "sd"],
    
    # Africa - East
    "kenya": ["kenya", "kenyan", "ke"],
    "tanzania": ["tanzania", "tanzanian", "tz"],
    "uganda": ["uganda", "ugandan", "ug"],
    "rwanda": ["rwanda", "rwandan", "rw"],
    "ethiopia": ["ethiopia", "ethiopian", "et"],
    "mauritius": ["mauritius", "mauritian", "mu"],
    "seychelles": ["seychelles", "seychellois", "sc"],
    "madagascar": ["madagascar", "malagasy", "mg"],
    
    # Africa - West
    "nigeria": ["nigeria", "nigerian", "ng"],
    "ghana": ["ghana", "ghanaian", "gh"],
    "senegal": ["senegal", "senegalese", "sn"],
    "ivory_coast": ["ivory coast", "ivorian", "cote d'ivoire", "ci"],
    "cameroon": ["cameroon", "cameroonian", "cm"],
    
    # Africa - Southern
    "south_africa": ["south africa", "south african", "sa", "za", "rsa"],
    "zimbabwe": ["zimbabwe", "zimbabwean", "zw"],
    "zambia": ["zambia", "zambian", "zm"],
    "botswana": ["botswana", "batswana", "bw"],
    "namibia": ["namibia", "namibian", "na"],
    
    # South America
    "brazil": ["brazil", "brazilian", "br", "brasil"],
    "argentina": ["argentina", "argentinian", "ar"],
    "chile": ["chile", "chilean", "cl"],
    "peru": ["peru", "peruvian", "pe"],
    "colombia": ["colombia", "colombian", "co"],
    "venezuela": ["venezuela", "venezuelan", "ve"],
    "ecuador": ["ecuador", "ecuadorian", "ec"],
    "bolivia": ["bolivia", "bolivian", "bo"],
    "paraguay": ["paraguay", "paraguayan", "py"],
    "uruguay": ["uruguay", "uruguayan", "uy"],
    "guyana": ["guyana", "guyanese", "gy"],
    "suriname": ["suriname", "surinamese", "sr"],
    
    # Central America & Caribbean
    "panama": ["panama", "panamanian", "pa"],
    "costa_rica": ["costa rica", "costa rican", "cr"],
    "guatemala": ["guatemala", "guatemalan", "gt"],
    "belize": ["belize", "belizean", "bz"],
    "honduras": ["honduras", "honduran", "hn"],
    "el_salvador": ["el salvador", "salvadoran", "sv"],
    "nicaragua": ["nicaragua", "nicaraguan", "ni"],
    "cuba": ["cuba", "cuban", "cu"],
    "jamaica": ["jamaica", "jamaican", "jm"],
    "bahamas": ["bahamas", "bahamian", "bs"],
    "dominican_republic": ["dominican republic", "dominican", "do"],
    "trinidad_and_tobago": ["trinidad", "tobago", "trinidad and tobago", "tt"],
    "barbados": ["barbados", "barbadian", "bb"],
    
    # Others
    "russia": ["russia", "russian", "ru", "russian federation"],
    "belarus": ["belarus", "belarusian", "by"],
    "moldova": ["moldova", "moldovan", "md"],
    "iceland": ["iceland", "icelandic", "is"],
    "malta": ["malta", "maltese", "mt"],
    "cyprus": ["cyprus", "cypriot", "cy"],
    "luxembourg": ["luxembourg", "luxembourgish", "lu"],
    "monaco": ["monaco", "monegasque", "mc"],
    "liechtenstein": ["liechtenstein", "li"],
    "san_marino": ["san marino", "sammarinese", "sm"],
    "vatican": ["vatican", "vatican city", "va", "holy see"],
    "andorra": ["andorra", "ad"],
    "scotland": ["scotland", "scottish"],
    "wales": ["wales", "welsh"],
    "northern_ireland": ["northern ireland"],
    "puerto_rico": ["puerto rico", "pr"],
    "guam": ["guam", "gu"],
    "bermuda": ["bermuda", "bm"],
    "cayman_islands": ["cayman islands", "cayman", "ky"],
    "greenland": ["greenland", "gl"],
    "faroe_islands": ["faroe islands", "faroe", "fo"],
}

# ============================================
# HELPER FUNCTIONS
# ============================================
def clean_requirements(requirements):
    if not requirements: return []
    cleaned = []
    for req in requirements[:5]:
        req = req.replace("Passportvalid", "Valid passport").replace("bycountry", "by country").replace("\u00a0", " ").replace("\u2013", "-")
        if len(req) > 20 and req not in cleaned: cleaned.append(req)
    return cleaned

def validate_input(query):
    if not query or not isinstance(query, str) or len(query) > 500: return False, "Invalid input"
    malicious_patterns = [r'<script', r'javascript:', r'onerror\s*=', r'SELECT\s+.*\s+FROM', r'DROP\s+TABLE', r'--']
    for pattern in malicious_patterns:
        if re.search(pattern, query, re.IGNORECASE): return False, "Invalid query content detected"
    return True, "Valid input"

def detect_country(query):
    query_lower = query.lower()
    detected_countries = []
    for country, keywords in COUNTRY_KEYWORDS.items():
        if any(keyword in query_lower for keyword in keywords):
            detected_countries.append(country)
    return detected_countries[0] if detected_countries else None

def detect_visa_type(query):
    query_lower = query.lower()
    if any(word in query_lower for word in ["student", "study", "education", "university", "college", "course"]): return "student"
    elif any(word in query_lower for word in ["work", "job", "employment", "skilled", "professional", "h1b", "h-1b"]): return "work"
    elif any(word in query_lower for word in ["tourist", "visit", "travel", "tourism", "vacation", "visitor"]): return "tourist"
    elif any(word in query_lower for word in ["business", "conference", "meeting"]): return "business"
    return "unknown"

def generate_requirements_from_api(api_result, visa_type):
    requirement_type = api_result.get('requirement', '').lower()
    passport_validity = api_result.get('passport_validity', '6 months')
    mandatory_reg = api_result.get('mandatory_registration', {})
    requirements = [f"Valid passport (valid for {passport_validity})"]
    if 'visa required' in requirement_type:
        requirements.extend(["Completed visa application form", "Passport-size photographs", "Proof of sufficient funds", "Travel itinerary", "Proof of ties to home country"])
    elif 'online visa' in requirement_type or 'evisa' in requirement_type:
        requirements.extend(["Online application submission", "Scanned passport copy", "Digital photograph", "Payment of visa fee online"])
    elif 'visa on arrival' in requirement_type:
        requirements.extend(["Passport with sufficient blank pages", "Return/onward ticket", "Proof of accommodation", "Sufficient funds for stay"])
    if mandatory_reg and mandatory_reg.get('name'): requirements.append(f"Complete {mandatory_reg.get('name')} registration")
    if visa_type == "student": requirements.append("Letter of acceptance from educational institution")
    elif visa_type == "work": requirements.append("Employment contract or job offer letter")
    return requirements[:8]

def generate_fees_from_api(api_result, country, visa_type):
    fee_ranges = {"us": "$185", "uk": "£115-£150", "ca": "$100 CAD", "au": "$150 AUD", "de": "€80", "fr": "€80", "jp": "¥3,000", "ae": "$100-200", "br": "R$290", "za": "R1,520", "th": "฿1,000-2,000"}
    return fee_ranges.get(country, "Contact embassy for current fees")

def generate_validity_from_api(api_result):
    duration = api_result.get('primary_rule', {}).get('duration', '')
    if duration: return f"Usually {duration}"
    return "Varies by visa type and consular discretion"

def generate_processing_time(api_result, country):
    requirement = api_result.get('requirement', '').lower()
    if 'online visa' in requirement or 'evisa' in requirement: return "3-7 business days (online)"
    elif 'visa on arrival' in requirement: return "Processed at port of entry"
    times = {"us": "2-4 weeks", "uk": "3 weeks", "ca": "2-8 weeks", "au": "20-33 days", "de": "15 days", "fr": "15 days", "jp": "5-7 days", "ae": "3-5 days"}
    return times.get(country, "Contact embassy for current processing times")

def get_sources_for_country(country_code, api_result, display_name=None):
    sources = OFFICIAL_SOURCES.get(country_code, [])
    if not sources:
        sources = [{"name": f"Find {display_name or country_code.upper()} Embassy", "url": f"https://www.embassypages.com/{country_code}", "type": "embassy_directory"}]
    if api_result.get('confidence') == 'high':
        sources.append({"name": "Travel Buddy API (Real-time)", "url": "https://rapidapi.com/TravelBuddyAI/api/visa-requirement", "type": "api"})
    return sources[:3]

# ============================================
# FLASK ROUTES
# ============================================
@app.route("/api/ask", methods=["POST"])
@limiter.limit("10 per minute")
def ask():
    try:
        data = request.get_json()
        if not data: return jsonify({"error": "Invalid request"}), 400
        query = data.get("query", "").strip()
        is_valid, msg = validate_input(query)
        if not is_valid: return jsonify({"error": msg}), 400
        if not query: return jsonify({"error": "Query required"}), 400
        query_lower = query.lower()

        country = detect_country(query_lower)
        if not country:
            return jsonify({"error": "Country not detected", "message": "Please clearly mention a country (e.g., US, UK, Canada, France, Japan, UAE)"}), 400

        visa_type = detect_visa_type(query_lower)
        if visa_type == "unknown":
            return jsonify({"status": "needs_clarification", "country_code": country, "message": "Visa requirements vary by type.", "options": ["tourist", "student", "work", "business"]}), 400

        # ✅ Detect nationality from query (or default to PK for backward compatibility)
        detected_nationality = "PK"  # Default
        for code, keywords in COUNTRY_KEYWORDS.items():
            if code != country and any(kw in query_lower for kw in keywords):
                detected_nationality = code.upper()
                break
        if "pakistani" in query_lower or "pakistan" in query_lower: detected_nationality = "PK"
        if "indian" in query_lower or "india" in query_lower: detected_nationality = "IN"
        if "american" in query_lower or "usa" in query_lower: detected_nationality = "US"

        provider = get_visa_provider()
        api_result = provider.get_visa_requirement(destination=country, nationality=detected_nationality)
        
        visa_info = VISA_DATA.get(country, {"country": country.upper(), "visa_types": {}})
        specific_visa = visa_info.get("visa_types", {}).get(visa_type, {})

        # ✅ CORRECTED COUNTRY NAME LOGIC
        if api_result.get('confidence') == 'high':
            api_dest = api_result.get('destination', {})
            api_name = api_dest.get('name', '')
            passport_name = api_result.get('passport', {}).get('name', '')
            if api_name and api_name.lower() != passport_name.lower():
                country_name = api_name
            else:
                country_name = visa_info.get("country", country.upper())
        else:
            country_name = visa_info.get("country", country.upper())

        response = {
            "country": country_name, "country_code": country, "visa_type": visa_type,
            "confidence": api_result.get('confidence', 'medium'), "source": api_result.get('source', 'fallback')
        }

        if api_result.get('confidence') == 'high':
            response["realtime"] = {"visa_requirement": api_result.get('requirement'), "passport_validity": api_result.get('passport_validity'), "source": api_result.get('source')}
            response["requirements"] = generate_requirements_from_api(api_result, visa_type)
            response["fees"] = generate_fees_from_api(api_result, country, visa_type)
            response["validity_note"] = generate_validity_from_api(api_result)
            response["processing_time_note"] = generate_processing_time(api_result, country)
        else:
            response["requirements"] = specific_visa.get("requirements", [])
            response["fees"] = specific_visa.get("fees", "Contact embassy")
            response["validity_note"] = specific_visa.get("validity_note", "Varies")
            response["processing_time_note"] = specific_visa.get("processing_time_note", "Varies by embassy")

        response["sources"] = get_sources_for_country(country, api_result, country_name)
        return jsonify(response)

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "countries_loaded": len(VISA_DATA), "timestamp": datetime.now().isoformat()})

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting Visa RAG System")
    print("=" * 60)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
