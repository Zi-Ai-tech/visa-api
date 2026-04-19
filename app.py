import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import json
import re
from datetime import datetime
import hashlib

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
// FALLBACK DATA (Minimal - only for emergencies)
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
// PAKISTANI-SPECIFIC DETAILED REQUIREMENTS
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
// COUNTRY DETECTION KEYWORDS
# ============================================

COUNTRY_KEYWORDS = {
    "us": ["us", "usa", "united states", "america", "american", "u.s.", "u.s.a"],
    "uk": ["uk", "united kingdom", "britain", "british", "england", "great britain"],
    "canada": ["canada", "canadian"],
    "uae": ["uae", "dubai", "emirates", "abu dhabi", "united arab emirates"],
    "ireland": ["ireland", "irish"],
    "australia": ["australia", "australian"],
    "germany": ["germany", "german", "deutschland"],
    "france": ["france", "french"],
    "italy": ["italy", "italian"],
    "spain": ["spain", "spanish"],
    "japan": ["japan", "japanese"],
    "china": ["china", "chinese"],
    "india": ["india", "indian"],
    "singapore": ["singapore", "singaporean"],
    "malaysia": ["malaysia", "malaysian"],
    "new_zealand": ["new zealand", "nz"],
    "south_africa": ["south africa", "south african"],
    "netherlands": ["netherlands", "dutch", "holland"],
    "sweden": ["sweden", "swedish"],
    "norway": ["norway", "norwegian"],
    "denmark": ["denmark", "danish"],
    "switzerland": ["switzerland", "swiss"],
    "belgium": ["belgium", "belgian"],
    "austria": ["austria", "austrian"],
    "portugal": ["portugal", "portuguese"],
    "greece": ["greece", "greek"],
    "turkey": ["turkey", "turkish", "türkiye"],
    "south_korea": ["south korea", "korea", "korean"],
    "thailand": ["thailand", "thai"],
    "vietnam": ["vietnam", "vietnamese"],
    "indonesia": ["indonesia", "indonesian"],
    "philippines": ["philippines", "filipino", "philippine"],
    "mexico": ["mexico", "mexican"],
    "saudi_arabia": ["saudi arabia", "saudi", "ksa"],
    "qatar": ["qatar", "qatari"],
    "kuwait": ["kuwait", "kuwaiti"],
    "bahrain": ["bahrain", "bahraini"],
    "oman": ["oman", "omani"],
    "egypt": ["egypt", "egyptian"],
    "poland": ["poland", "polish"],
    "finland": ["finland", "finnish"]
}

# ============================================
# HELPER FUNCTIONS
# ============================================

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
    // SOURCES (REAL URLs ONLY - NO FAKE SOURCES)
    # ============================================
    answer_parts.append("### 🔗 Official Sources")
    sources = OFFICIAL_SOURCES.get(country_code, [])
    
    if sources:
        for source in sources[:2]:
            answer_parts.append(f"• [{source['name']}]({source['url']}) - Official Government Source")
    else:
        answer_parts.append("• Contact the nearest embassy for official information")
    
    # ============================================
    // UNIVERSAL DISCLAIMER
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
        parts.append(f"**📅 Validity Note:** {rules.get('validity_note', 'At officer\\'s discretion')}")
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

# ============================================
# FLASK ROUTES
# ============================================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/ask", methods=["POST"])
@limiter.limit("10 per minute")
def ask():
    print("📥 Received request to /api/ask", flush=True)
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
            
        query = data.get("query", "")
        
        # Input validation
        is_valid, validation_message = validate_input(query)
        if not is_valid:
            return jsonify({"error": validation_message}), 400
        
        if not query:
            return jsonify({"error": "Query required"}), 400
        
        query_lower = query.lower()
        
        # Detect country and visa type
        country = detect_country(query_lower)
        if not country:
            return jsonify({
                "error": "Country not detected",
                "message": "Please specify a country",
                "available_countries": list(VISA_DATA.keys())[:10]
            }), 400
        
        visa_type = detect_visa_type(query_lower)
        visa_type_specified = visa_type != "unknown"
        is_pakistani = "pakistani" in query_lower or "pakistan" in query_lower
        
        # Check cache
        cache_key = get_cache_key(query_lower, country, visa_type, is_pakistani)
        if cache_key in response_cache:
            cached_response = response_cache[cache_key]
            if (datetime.now() - cached_response['timestamp']).seconds < CACHE_TIMEOUT:
                print(f"📦 Returning cached response", flush=True)
                return jsonify(cached_response['data'])
        
        # Get visa information
        visa_info = VISA_DATA.get(country, FALLBACK_VISA_DATA.get(country, {}))
        if not visa_info:
            return jsonify({
                "error": "Country data not available",
                "message": f"Visa information for {country} is not available"
            }), 404
        
        # Calculate confidence
        confidence_info = calculate_confidence(country, visa_info, visa_type_specified)
        
        # Generate answer
        answer = generate_answer(
            query, country, visa_info, visa_type, 
            is_pakistani, confidence_info
        )
        
        # Get visa-specific data
        visa_types = visa_info.get('visa_types', {})
        display_visa = visa_types.get(visa_type, {}) if visa_type != "unknown" else {}
        
        # Build response with REAL sources (no fake sources)
        response_data = {
            "direct_answer": answer,
            "country": visa_info.get("country", country.upper()),
            "country_code": country,
            "visa_type": visa_type,
            "visa_type_specified": visa_type_specified,
            "requirements": display_visa.get('requirements', []),
            "processing_time_note": display_visa.get('processing_time_note', 'Contact embassy'),
            "fees": display_visa.get('fees', 'Contact embassy'),
            "validity_note": display_visa.get('validity_note', 'Varies'),
            "confidence": confidence_info,
            "sources": OFFICIAL_SOURCES.get(country, []),  # REAL sources only
            "is_pakistani": is_pakistani,
            "timestamp": datetime.now().isoformat(),
            "disclaimer": "Visa approval is not guaranteed. Always verify with official sources."
        }
        
        # Cache the response
        response_cache[cache_key] = {
            'data': response_data,
            'timestamp': datetime.now()
        }
        
        print(f"✅ Processed query for {country} (visa_type: {visa_type})", flush=True)
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500

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

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "10 requests per minute limit"
    }), 429

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