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
    """Clean up scraped requirement text"""
    if not requirements:
        return []
    
    cleaned = []
    for req in requirements[:5]:  # Limit to 5 most important
        # Fix common typos and formatting
        req = req.replace("Passportvalid", "Valid passport")
        req = req.replace("bycountry", "by country")
        req = req.replace("\u00a0", " ")
        req = req.replace("\u2013", "-")
        req = req.replace("thePhotograph", "the Photograph")
        req = req.replace("thephoto", "the photo")
        req = req.replace("Form DS-160\u2013Learn", "Form DS-160 - Learn")
        req = req.replace("DS-160confirmation", "DS-160 confirmation")
        req = req.replace("about completing theDS-160", "about completing the DS-160")
        
        # Only keep substantive requirements
        if len(req) > 20 and req not in cleaned:
            cleaned.append(req)
    
    return cleaned

def validate_input(query):
    """Validate and sanitize input query"""
    if not query or not isinstance(query, str):
        return False, "Invalid input type"
    
    if len(query) > 500:
        return False, "Query too long (max 500 characters)"
    
    malicious_patterns = [
        r'<script', r'javascript:', r'onerror\s*=', r'onclick\s*=',
        r'SELECT\s+.*\s+FROM', r'DROP\s+TABLE', r'DELETE\s+FROM',
        r'--', r'/\*', r'\.\./', r'\.\.\\', r'exec\s*\(', r'eval\s*\('
    ]
    
    for pattern in malicious_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return False, "Invalid query content detected"
    
    return True, "Valid input"

def detect_country(query):
    """Detect which country is being asked about"""
    query_lower = query.lower()
    
    detected_countries = []
    for country, keywords in COUNTRY_KEYWORDS.items():
        if any(keyword in query_lower for keyword in keywords):
            detected_countries.append(country)
    
    return detected_countries[0] if detected_countries else None

def detect_visa_type(query):
    """Detect visa type from query - returns 'unknown' if not specified"""
    query_lower = query.lower()
    
    if any(word in query_lower for word in ["student", "study", "education", "university", "college", "course"]):
        return "student"
    elif any(word in query_lower for word in ["work", "job", "employment", "skilled", "professional", "h1b", "h-1b"]):
        return "work"
    elif any(word in query_lower for word in ["tourist", "visit", "travel", "tourism", "vacation", "visitor"]):
        return "tourist"
    elif any(word in query_lower for word in ["business", "conference", "meeting"]):
        return "business"
    
    return "unknown"  # IMPORTANT: Return unknown instead of assuming

def get_cache_key(query, country, visa_type, is_pakistani):
    """Generate cache key for query"""
    key_string = f"{query}_{country}_{visa_type}_{is_pakistani}"
    return hashlib.md5(key_string.encode()).hexdigest()

def get_pakistani_details(country_code, visa_type):
    """Get detailed Pakistani-specific requirements"""
    country_data = PAKISTANI_DETAILED.get(country_code, {})
    return country_data.get(visa_type, {})

def generate_answer(query, country_code, visa_info, visa_type, is_pakistani, confidence_info):
    """Generate a comprehensive, non-generic answer with country-specific rules"""
    
    country_name = visa_info.get('country', country_code.upper())
    rules = VisaRulesEngine.get_rules(country_code, visa_type)
    
    visa_types = visa_info.get('visa_types', {})
    
    # Handle unknown visa type
    if visa_type == "unknown":
        return generate_clarification_response(country_name, country_code, visa_types, is_pakistani)
    
    specific_visa = visa_types.get(visa_type, {})
    
    answer_parts = []
    
    # Header with visa type clarification
    visa_display_names = {
        "tourist": "B1/B2 Visitor Visa" if country_code == "us" else "Tourist/Visitor Visa",
        "student": "F-1 Student Visa" if country_code == "us" else "Student Visa",
        "work": "Work Visa",
        "business": "Business Visa"
    }
    
    display_name = visa_display_names.get(visa_type, f"{visa_type.title()} Visa")
    
    answer_parts.append(f"## {country_name} {display_name} Requirements")
    
    # IMPORTANT: Clarify if visa type wasn't explicitly asked
    if not any(word in query.lower() for word in ["student", "work", "tourist", "visit"]):
        answer_parts.append(f"\n*⚠️ Note: You didn't specify a visa type. Below are requirements for {display_name}. Other visa types (student, work) have different requirements.*\n")
    
    # Confidence badge
    confidence_badge = "🟢 HIGH" if confidence_info['level'] == 'high' else "🟡 MEDIUM" if confidence_info['level'] == 'medium' else "🔴 LOW"
    answer_parts.append(f"*Confidence: {confidence_badge} ({confidence_info['score']*100:.0f}%) • Last Updated: {visa_info.get('last_updated', 'Recently')}*\n")
    
    # ============================================
    # COUNTRY-SPECIFIC LOGIC - US
    # ============================================
    if country_code == "us":
        answer_parts.extend(generate_us_response(visa_type, specific_visa, is_pakistani, rules))
    
    # ============================================
    # COUNTRY-SPECIFIC LOGIC - UK
    # ============================================
    elif country_code == "uk":
        answer_parts.extend(generate_uk_response(visa_type, specific_visa, is_pakistani, rules))
    
    # ============================================
    # COUNTRY-SPECIFIC LOGIC - SCHENGEN
    # ============================================
    elif country_code in ["germany", "france", "italy", "spain", "netherlands", "sweden", "norway", "denmark", "finland", "austria", "belgium", "portugal", "greece", "switzerland", "poland", "czech_republic", "hungary"]:
        answer_parts.extend(generate_schengen_response(country_name, visa_type, specific_visa, is_pakistani, rules))
    
    # ============================================
    # DEFAULT RESPONSE FOR OTHER COUNTRIES
    # ============================================
    else:
        answer_parts.extend(generate_default_response(country_name, visa_type, specific_visa, is_pakistani, rules))
    
    # ============================================
    #  SOURCES (REAL URLs ONLY - NO FAKE SOURCES)
    # ============================================
    answer_parts.append("### 🔗 Official Sources")
    sources = OFFICIAL_SOURCES.get(country_code, [])
    
    if sources:
        for source in sources[:2]:
            answer_parts.append(f"• [{source['name']}]({source['url']}) - Official Government Source")
    else:
        answer_parts.append("• Contact the nearest embassy for official information")
    
    # ============================================
    # // UNIVERSAL DISCLAIMER
    # ============================================
    answer_parts.append("\n### ⚠️ Important Notice")
    answer_parts.append("• Visa requirements change frequently. Always verify with official sources.")
    answer_parts.append("• Visa approval is **NOT guaranteed** even if you meet all requirements.")
    answer_parts.append("• This information is for guidance only. Consular officers make final decisions.")
    
    return "\n".join(answer_parts)

def generate_clarification_response(country_name, country_code, visa_types, is_pakistani):
    """Generate response when visa type is unknown"""
    answer_parts = []
    
    answer_parts.append(f"## {country_name} Visa Information")
    answer_parts.append(f"\n*⚠️ Please specify which type of visa you're asking about.*\n")
    
    answer_parts.append(f"**Available visa categories:**")
    
    visa_descriptions = {
        "tourist": "Tourist/Visitor visa for tourism or visiting family/friends",
        "student": "Student visa for academic studies",
        "work": "Work visa for employment",
        "business": "Business visa for meetings/conferences"
    }
    
    for v_type, v_data in visa_types.items():
        if v_type in visa_descriptions:
            answer_parts.append(f"• **{v_type.title()}** - {visa_descriptions[v_type]}")
    
    answer_parts.append(f"\n**Example queries:**")
    answer_parts.append(f'• "{country_name} tourist visa requirements"')
    answer_parts.append(f'• "{country_name} student visa for Pakistani"')
    answer_parts.append(f'• "{country_name} work visa process"')
    
    return "\n".join(answer_parts)

def generate_us_response(visa_type, visa_data, is_pakistani, rules):
    """Generate US-specific response (NOT generic template)"""
    parts = []
    
    if visa_type == "tourist":
        parts.append("### 📋 B1/B2 Visitor Visa Requirements")
        parts.append("")
        parts.append("**Core Documents:**")
        parts.append("1. DS-160 confirmation page (completed online)")
        parts.append("2. Valid Pakistani passport (6+ months beyond intended stay)")
        parts.append("3. Interview appointment letter")
        parts.append("4. 2x2 inch photograph (white background)")
        parts.append("5. Visa fee payment receipt ($185)")
        parts.append("")
        parts.append("**Supporting Evidence (Focus on Ties to Pakistan):**")
        parts.append("• Employment letter with approved leave")
        parts.append("• Bank statements (6 months, consistent income)")
        parts.append("• Property/asset documents")
        parts.append("• Family ties evidence (marriage/birth certificates)")
        parts.append("")
        parts.append(f"**⏱️ Processing Time Note:** {rules.get('processing_time_note', 'Varies by consulate')}")
        parts.append("")
        validity_default = "At officer's discretion"
        parts.append(f"**📅 Validity Note:** {rules.get('validity_note', validity_default)}")
        parts.append("")
        
        if is_pakistani:
            parts.append("### 🇵🇰 Pakistani Applicants - Critical Information")
            pakistani_details = get_pakistani_details("us", "tourist")
            
            if pakistani_details:
                parts.append(f"\n**Refusal Risk:** {pakistani_details.get('refusal_risk', 'Moderate')}")
                parts.append("")
                parts.append("**Important Notes:**")
                for note in pakistani_details.get('important_notes', []):
                    parts.append(f"• {note}")
                parts.append("")
                parts.append("**Interview Tips:**")
                for tip in pakistani_details.get('interview_tips', []):
                    parts.append(f"• {tip}")
                parts.append("")
                parts.append("**Financial Recommendations:**")
                for req in pakistani_details.get('financial_requirements', []):
                    parts.append(f"• {req}")
        
        parts.append("")
        parts.append("### 🎤 Interview Information")
        parts.append("• **Location:** U.S. Embassy Islamabad or Consulates in Karachi/Lahore")
        parts.append("• **Wait Times:** Check travel.state.gov for current appointment availability")
        parts.append("• **Administrative Processing:** Some cases require additional review (221g) which may take weeks/months")
        
    elif visa_type == "student":
        parts.append("### 📚 F-1 Student Visa Requirements")
        parts.append("")
        parts.append("**Required Documents:**")
        parts.append("1. Form I-20 from SEVP-approved school")
        parts.append("2. SEVIS fee payment receipt ($350)")
        parts.append("3. DS-160 confirmation")
        parts.append("4. Valid passport")
        parts.append("5. Financial proof (first year expenses)")
        parts.append("")
        
        if is_pakistani:
            pakistani_details = get_pakistani_details("us", "student")
            if pakistani_details:
                parts.append(f"**📚 IELTS Requirement:** {pakistani_details.get('ielts_score', 'Check institution')}")
                parts.append("")
                parts.append("**Financial Requirements:**")
                for req in pakistani_details.get('financial_requirements', []):
                    parts.append(f"• {req}")
    
    return parts

def generate_uk_response(visa_type, visa_data, is_pakistani, rules):
    """Generate UK-specific response"""
    parts = []
    
    if visa_type == "student" and is_pakistani:
        parts.append("### 🇬🇧 UK Student Visa - Pakistani Applicants")
        parts.append("")
        parts.append("**⚠️ CRITICAL IELTS REQUIREMENT**")
        parts.append("• IELTS for UKVI (Academic) is **MANDATORY**")
        parts.append("• Regular IELTS (Academic) is **NOT ACCEPTED**")
        parts.append("• Minimum score: 5.5-6.5 depending on course level")
        parts.append("")
        parts.append("**Tuberculosis Test:**")
        parts.append("• Mandatory for all Pakistani applicants")
        parts.append("• Must be from IOM-approved clinic")
        parts.append("")
        parts.append("**Financial Requirements:**")
        parts.append("• £1,334/month (outside London) for up to 9 months")
        parts.append("• Funds must be held for 28 consecutive days")
        parts.append("• Bank statements must be within 31 days of application")
    
    return parts

def generate_schengen_response(country_name, visa_type, visa_data, is_pakistani, rules):
    """Generate Schengen-specific response"""
    parts = []
    
    parts.append(f"### 🇪🇺 {country_name} Schengen Visa")
    parts.append("")
    parts.append("**Standard Schengen Requirements:**")
    parts.append("• Valid passport (3 months beyond intended departure)")
    parts.append("• Travel insurance (€30,000 minimum coverage)")
    parts.append("• Proof of accommodation")
    parts.append("• Proof of sufficient funds")
    parts.append("• Flight reservation (NOT purchased ticket)")
    parts.append("")
    
    if is_pakistani:
        parts.append("**Pakistani Applicants - Additional Requirements:**")
        parts.append("• Detailed travel itinerary")
        parts.append("• Strong ties to Pakistan (property, family, employment)")
        parts.append("• 6 months bank statements")
        parts.append("• NOC from employer (if employed)")
        parts.append("")
        parts.append("**Processing Note:**")
        parts.append("• Apply at least 4-6 weeks before travel")
        parts.append("• First-time applicants may face additional scrutiny")
    
    return parts

def generate_default_response(country_name, visa_type, visa_data, is_pakistani, rules):
    """Generate default response for other countries"""
    parts = []
    
    parts.append(f"### {visa_type.title()} Visa Requirements")
    parts.append("")
    
    requirements = visa_data.get('requirements', [])
    if requirements:
        for i, req in enumerate(requirements[:6], 1):
            parts.append(f"{i}. {req}")
    
    if is_pakistani:
        parts.append("")
        parts.append("### 🇵🇰 Pakistani Applicants")
        parts.append("• Additional documentation may be required")
        parts.append("• Contact the embassy for specific requirements")
        parts.append("• Apply well in advance of travel date")
    
    return parts

def calculate_confidence(country_code, visa_info, visa_type_specified):
    """Calculate confidence score"""
    confidence_score = 0.7
    confidence_level = "medium"
    
    # Higher confidence if visa type is specified
    if visa_type_specified:
        confidence_score += 0.1
    
    # Higher confidence for scraped data
    if visa_info.get('source_type') == 'scraped':
        confidence_score += 0.15
    
    # Higher confidence for countries with verified sources
    if country_code in OFFICIAL_SOURCES and OFFICIAL_SOURCES[country_code]:
        confidence_score += 0.05
    
    confidence_score = min(0.95, confidence_score)
    
    if confidence_score >= 0.85:
        confidence_level = "high"
    elif confidence_score >= 0.6:
        confidence_level = "medium"
    else:
        confidence_level = "low"
    
    return {
        "score": confidence_score,
        "level": confidence_level
    }
def generate_requirements_from_api(api_result, visa_type):
    """Generate smart requirements based on API result"""
    requirement_type = api_result.get('requirement', '').lower()
    passport_validity = api_result.get('passport_validity', '6 months')
    primary_rule = api_result.get('primary_rule', {}).get('name', '')
    mandatory_reg = api_result.get('mandatory_registration', {})
    
    requirements = []
    
    # Passport requirement (universal)
    requirements.append(f"Valid passport (valid for {passport_validity})")
    
    # Based on visa requirement type
    if 'visa required' in requirement_type:
        requirements.extend([
            "Completed visa application form",
            "Passport-size photographs",
            "Proof of sufficient funds",
            "Travel itinerary (flight and hotel bookings)",
            "Proof of ties to home country"
        ])
    elif 'online visa' in requirement_type or 'evisa' in requirement_type:
        requirements.extend([
            "Online application submission",
            "Scanned passport copy",
            "Digital photograph",
            "Payment of visa fee online"
        ])
    elif 'visa-free' in requirement_type:
        requirements.append("No visa required for tourist visits")
    elif 'visa on arrival' in requirement_type:
        requirements.extend([
            "Passport with sufficient blank pages",
            "Return/onward ticket",
            "Proof of accommodation",
            "Sufficient funds for stay"
        ])
    
    # Add mandatory registration if required
    if mandatory_reg and mandatory_reg.get('name'):
        requirements.append(f"Complete {mandatory_reg.get('name')} registration before travel")
    
    # Add visa-type specific requirements
    if visa_type == "student":
        requirements.append("Letter of acceptance from educational institution")
    elif visa_type == "work":
        requirements.append("Employment contract or job offer letter")
    
    return requirements[:8]  # Limit to 8 most important


def generate_fees_from_api(api_result, country, visa_type):
    """Generate fee information"""
    # Common fee ranges by country
    fee_ranges = {
        "us": "$185",
        "uk": "£115-£150",
        "ca": "$100 CAD",
        "au": "$150 AUD",
        "nz": "$211 NZD",
        "jp": "¥3,000",
        "cn": "$140",
        "in": "$25-100",
        "ae": "$100-200",
        "de": "€80",
        "fr": "€80",
        "it": "€80",
        "es": "€80",
        "nl": "€80",
        "ch": "€80",
        "ie": "€80",
        "sg": "$30 SGD",
        "my": "RM 20-200",
        "th": "฿1,000-2,000",
        "za": "R1,520",
        "br": "R$290",
        "mx": "$36-51 USD"
    }
    
    return fee_ranges.get(country, "Contact embassy for current fees")


def generate_validity_from_api(api_result):
    """Generate validity information"""
    primary_rule = api_result.get('primary_rule', {})
    duration = primary_rule.get('duration', '')
    
    if duration:
        return f"Usually {duration}"
    
    requirement = api_result.get('requirement', '').lower()
    if 'visa-free' in requirement:
        return "Usually 30-90 days depending on nationality"
    elif 'visa on arrival' in requirement:
        return "Usually 15-90 days"
    
    return "Varies by visa type and consular discretion"


def generate_processing_time(api_result, country):
    """Generate processing time information"""
    requirement = api_result.get('requirement', '').lower()
    
    if 'online visa' in requirement or 'evisa' in requirement:
        return "3-7 business days (online processing)"
    elif 'visa on arrival' in requirement:
        return "Processed at port of entry"
    elif 'visa-free' in requirement:
        return "No advance processing required"
    
    # Common processing times by country
    times = {
        "us": "2-4 weeks for interview scheduling",
        "uk": "3 weeks (priority: 5 days)",
        "ca": "2-8 weeks",
        "au": "20-33 days",
        "nz": "20-25 days",
        "ae": "3-5 working days",
        "de": "15 days (Schengen)",
        "fr": "15 days (Schengen)",
        "jp": "5-7 working days",
        "cn": "4-5 working days",
        "sg": "3 working days",
        "za": "5-10 working days"
    }
    
    return times.get(country, "Contact embassy for current processing times")


def get_sources_for_country(country_code, api_result, display_name=None):
    """Get official sources for a country"""
    sources = OFFICIAL_SOURCES.get(country_code, [])
    
    # If no sources, generate embassy finder link
    if not sources:
        search_name = display_name if display_name else country_code.upper()
        sources = [{
            "name": f"Find {search_name} Embassy",
            "url": f"https://www.embassypages.com/{country_code}",
            "type": "embassy_directory"
        }]
    
    # Add API source if used
    if api_result.get('confidence') == 'high':
        sources.append({
            "name": "Travel Buddy API (Real-time)",
            "url": "https://rapidapi.com/TravelBuddyAI/api/visa-requirement",
            "type": "api"
        })
    
    return sources[:3]

def get_pakistani_note(country, visa_type):
    """Get Pakistani-specific note"""
    notes = {
        "us": "Pakistani applicants face higher scrutiny. Strong ties to home country essential.",
        "uk": "IELTS for UKVI required for students. TB test mandatory.",
        "ca": "Biometrics mandatory. Higher financial proof often required.",
        "ae": "Easy process with valid residence permit or employment letter.",
        "ie": "IELTS 5.5+ typically required. Embassy interview may be required.",
        "au": "GTE assessment stricter for Pakistani applicants.",
        "de": "Blocked account required for students. APS certificate needed."
    }
    
    return notes.get(country, "Contact embassy for Pakistani-specific requirements.")

# ============================================
# FLASK ROUTES
# ============================================

# @app.route("/")
# def home():
#     return render_template("index.html")

@app.route("/api/debug/config", methods=["GET"])
def debug_config():
    """Debug endpoint to check configuration"""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.environ.get('TRAVELBUDDY_API_KEY')
    
    return jsonify({
        "api_key_configured": bool(api_key),
        "api_key_length": len(api_key) if api_key else 0,
        "api_key_preview": api_key[:15] + "..." if api_key else None,
        "api_host": os.environ.get('TRAVELBUDDY_API_HOST', 'not set')
    })

# Add this temporarily to main.py
@app.route("/api/debug/api-test", methods=["GET"])
def test_api_connection():
    """Debug endpoint to test API connection"""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.environ.get('TRAVELBUDDY_API_KEY')
    
    return jsonify({
        "api_key_configured": bool(api_key),
        "api_key_preview": api_key[:10] + "..." if api_key else None,
        "api_host": os.environ.get('TRAVELBUDDY_API_HOST')
    })

@app.route("/api/ask", methods=["POST"])
@limiter.limit("10 per minute")
def ask():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request"}), 400

        query = data.get("query", "").strip()

        # Validate input
        is_valid, msg = validate_input(query)
        if not is_valid:
            return jsonify({"error": msg}), 400

        if not query:
            return jsonify({"error": "Query required"}), 400

        query_lower = query.lower()

        # Detect country
        country = detect_country(query_lower)
        if not country:
            return jsonify({
                "error": "Country not detected",
                "message": "Please clearly mention a country (e.g., US, UK, Canada, France, Japan, UAE)"
            }), 400

        # Detect visa type
        visa_type = detect_visa_type(query_lower)
        visa_type_specified = visa_type != "unknown"
        is_pakistani = "pakistani" in query_lower or "pakistan" in query_lower

        # 🚨 STRICT RULE: DO NOT ANSWER WITHOUT VISA TYPE
        if not visa_type_specified:
            return jsonify({
                "status": "needs_clarification",
                "country_code": country,
                "message": f"Visa requirements vary by type.",
                "options": ["tourist", "student", "work", "business"],
                "example_queries": [
                    f"{country} tourist visa requirements",
                    f"{country} student visa for Pakistani",
                    f"{country} work visa process"
                ]
            })

        # ✅ PRIMARY: Get real-time data from API for ALL countries
        provider = get_visa_provider()
        api_result = provider.get_visa_requirement(
            destination=country,
            nationality="PK" if is_pakistani else "US"
        )
        
        # ✅ SECONDARY: Load local data as fallback/supplement
        visa_info = VISA_DATA.get(country, {})
        if not visa_info:
            visa_info = {"country": country.upper(), "visa_types": {}}
        
        visa_types = visa_info.get("visa_types", {})
        specific_visa = visa_types.get(visa_type, {})

        # ✅ BUILD RESPONSE - FIXED COUNTRY NAME
        # Determine the correct country name
        if api_result.get('confidence') == 'high':
            api_destination = api_result.get('destination', {})
            api_country_name = api_destination.get('name', '')
            
            # Check if the API returned the passport country instead of destination
            passport_info = api_result.get('passport', {})
            passport_name = passport_info.get('name', '')
            
            # Use the destination if it's not the same as passport, otherwise use local
            if api_country_name and api_country_name.lower() != passport_name.lower():
                country_name = api_country_name
            else:
                # Fallback to local or formatted country code
                country_name = visa_info.get("country", country.upper())
        else:
            country_name = visa_info.get("country", country.upper())

        response = {
            "country": country_name,
            "country_code": country,
            "visa_type": visa_type,
            "confidence": api_result.get('confidence', 'medium'),
            "source": api_result.get('source', 'fallback')
        }

        # Add realtime data if available
        if api_result.get('confidence') == 'high':
            response["realtime"] = {
                "visa_requirement": api_result.get('requirement'),
                "passport_validity": api_result.get('passport_validity'),
                "primary_rule": api_result.get('primary_rule', {}).get('name'),
                "source": api_result.get('source')
            }
            
            # Generate smart requirements based on API result
            response["requirements"] = generate_requirements_from_api(api_result, visa_type)
            response["fees"] = generate_fees_from_api(api_result, country, visa_type)
            response["validity_note"] = generate_validity_from_api(api_result)
            response["processing_time_note"] = generate_processing_time(api_result, country)
        else:
            # Fallback to local data
            response["requirements"] = specific_visa.get("requirements", [])
            response["fees"] = specific_visa.get("fees", "Contact embassy")
            response["validity_note"] = specific_visa.get("validity_note", "Varies")
            response["processing_time_note"] = specific_visa.get("processing_time_note", "Varies by embassy")

        # Add Pakistani-specific notes
        if is_pakistani:
            response["pakistani_note"] = get_pakistani_note(country, visa_type)

        # Add official sources - FIXED: Pass the correct country name
        response["sources"] = get_sources_for_country(country, api_result, country_name)

        return jsonify(response)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/countries", methods=["GET"])
def list_countries():
    """List all available countries"""
    countries_list = []
    for code, data in VISA_DATA.items():
        countries_list.append({
            "code": code,
            "name": data.get("country", code),
            "last_updated": data.get("last_updated", "Unknown"),
            "visa_types": list(data.get("visa_types", {}).keys())
        })
    
    countries_list.sort(key=lambda x: x['name'])
    
    return jsonify({
        "countries": countries_list,
        "total": len(countries_list),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "message": "Visa RAG System with Country-Specific Rules",
        "cache_size": len(response_cache),
        "countries_loaded": len(VISA_DATA),
        "sources_verified": len(OFFICIAL_SOURCES),
        "timestamp": datetime.now().isoformat()
    })

# ============================================
# REAL-TIME API ENDPOINTS (NEW)
# ============================================

@app.route("/api/visa/check", methods=["POST"])
@limiter.limit("20 per minute")
def check_visa_requirement():
    """
    Check visa requirements using real-time Travel Buddy API.
    
    Request body:
    {
        "destination": "US" or "united states",
        "nationality": "PK" (optional, defaults to Pakistan)
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request"}), 400
        
        destination = data.get("destination", "").strip()
        nationality = data.get("nationality", "PK").strip()
        
        if not destination:
            return jsonify({"error": "Destination required"}), 400
        
        provider = get_visa_provider()
        result = provider.get_visa_requirement(destination, nationality)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cache/stats", methods=["GET"])
def get_cache_stats():
    """Get API cache statistics"""
    provider = get_visa_provider()
    return jsonify(provider.get_cache_stats())


@app.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    """Clear expired API cache entries"""
    provider = get_visa_provider()
    cleared = provider.clear_expired_cache()
    return jsonify({"cleared": cleared})

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "10 requests per minute limit"
    }), 429

def clean_cache():
    now = datetime.now()
    keys_to_delete = []

    for key, value in response_cache.items():
        if (now - value['timestamp']).seconds > CACHE_TIMEOUT:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        del response_cache[key]

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting Visa RAG System")
    print("=" * 60)
    print(f"📊 Loaded {len(VISA_DATA)} countries")
    print(f"🔗 Verified sources: {len(OFFICIAL_SOURCES)} countries")
    print("✅ Country-specific rules enabled")
    print("✅ No fake sources - official URLs only")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
 
"# Last updated: $(date)" 

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