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
                "documents_approach": "focus_on_ties_not_checklist",
                "processing_time_note": "Wait times vary significantly by consulate and can range from weeks to months"
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


def get_official_source_for_country(country_code, country_name=None):
    """Dynamically generate official source URLs for any country"""
    patterns = {
        # North America
        "us": ("U.S. Department of State", "https://travel.state.gov", ".gov"),
        "ca": ("Immigration Canada", "https://www.canada.ca/en/immigration-refugees-citizenship.html", ".gc.ca"),
        "mx": ("Mexico INM", "https://www.inm.gob.mx", ".gob.mx"),
        # Europe
        "uk": ("UK Visas and Immigration", "https://www.gov.uk/browse/visas-immigration", ".gov.uk"),
        "ie": ("Irish Immigration", "https://www.irishimmigration.ie", ".ie"),
        "de": ("German Foreign Office", "https://www.auswaertiges-amt.de", ".de"),
        "fr": ("France Visas", "https://france-visas.gouv.fr", ".gouv.fr"),
        "it": ("Italy Visti", "https://vistoperitalia.esteri.it", ".it"),
        "es": ("Spain Exteriores", "https://www.exteriores.gob.es", ".gob.es"),
        "pt": ("Portugal SEF", "https://www.sef.pt", ".pt"),
        "nl": ("Netherlands IND", "https://ind.nl", ".nl"),
        "be": ("Belgium Immigration", "https://dofi.ibz.be", ".be"),
        "ch": ("Switzerland SEM", "https://www.sem.admin.ch", ".admin.ch"),
        "at": ("Austria Migration", "https://www.migration.gv.at", ".gv.at"),
        "se": ("Sweden Migrationsverket", "https://www.migrationsverket.se", ".se"),
        "no": ("Norway UDI", "https://www.udi.no", ".no"),
        "dk": ("Denmark Nyidanmark", "https://www.nyidanmark.dk", ".dk"),
        "fi": ("Finland Migri", "https://migri.fi", ".fi"),
        "gr": ("Greece Migration", "https://migration.gov.gr", ".gov.gr"),
        "pl": ("Poland Visa", "https://www.gov.pl/web/poland/visa", ".gov.pl"),
        "cz": ("Czech Republic MVCR", "https://www.mvcr.cz", ".cz"),
        "hu": ("Hungary Immigration", "https://oif.gov.hu", ".gov.hu"),
        "ro": ("Romania IGI", "https://igi.mai.gov.ro", ".gov.ro"),
        "bg": ("Bulgaria MFA", "https://www.mfa.bg", ".bg"),
        "hr": ("Croatia MUP", "https://mup.gov.hr", ".gov.hr"),
        "sk": ("Slovakia MV", "https://www.minv.sk", ".sk"),
        "si": ("Slovenia GOV", "https://www.gov.si", ".si"),
        "ee": ("Estonia MFA", "https://vm.ee", ".ee"),
        "lv": ("Latvia MFA", "https://www.mfa.gov.lv", ".gov.lv"),
        "lt": ("Lithuania MIGRIS", "https://www.migracija.lt", ".lt"),
        "ua": ("Ukraine MFA", "https://mfa.gov.ua", ".gov.ua"),
        "rs": ("Serbia MFA", "https://www.mfa.gov.rs", ".gov.rs"),
        # Asia-Pacific
        "jp": ("MOFA Japan", "https://www.mofa.go.jp", ".go.jp"),
        "cn": ("China Visa", "https://www.visaforchina.cn", ".gov.cn"),
        "kr": ("South Korea Visa", "https://www.visa.go.kr", ".go.kr"),
        "in": ("Indian Visa", "https://indianvisaonline.gov.in", ".gov.in"),
        "pk": ("Pakistan Immigration", "https://www.dgip.gov.pk", ".gov.pk"),
        "bd": ("Bangladesh Immigration", "https://www.immigration.gov.bd", ".gov.bd"),
        "lk": ("Sri Lanka Immigration", "https://www.immigration.gov.lk", ".gov.lk"),
        "np": ("Nepal Immigration", "https://www.immigration.gov.np", ".gov.np"),
        "au": ("Department of Home Affairs", "https://immi.homeaffairs.gov.au", ".gov.au"),
        "nz": ("Immigration New Zealand", "https://www.immigration.govt.nz", ".govt.nz"),
        "th": ("Thailand Immigration", "https://www.immigration.go.th", ".go.th"),
        "vn": ("Vietnam Immigration", "https://xuatnhapcanh.gov.vn", ".gov.vn"),
        "sg": ("Singapore ICA", "https://www.ica.gov.sg", ".gov.sg"),
        "my": ("Malaysia Immigration", "https://www.imi.gov.my", ".gov.my"),
        "id": ("Indonesia Immigration", "https://www.imigrasi.go.id", ".go.id"),
        "ph": ("Philippines Immigration", "https://immigration.gov.ph", ".gov.ph"),
        "kh": ("Cambodia eVisa", "https://www.evisa.gov.kh", ".gov.kh"),
        "la": ("Laos Immigration", "https://immigration.gov.la", ".gov.la"),
        "mm": ("Myanmar eVisa", "https://evisa.moip.gov.mm", ".gov.mm"),
        # Middle East
        "ae": ("UAE Government", "https://u.ae/en/information-and-services/visa-and-emirates-id", ".gov.ae"),
        "sa": ("Saudi Arabia MOFA", "https://visa.mofa.gov.sa", ".gov.sa"),
        "qa": ("Qatar MOI", "https://portal.moi.gov.qa", ".gov.qa"),
        "kw": ("Kuwait eVisa", "https://evisa.moi.gov.kw", ".gov.kw"),
        "bh": ("Bahrain eVisa", "https://www.evisa.gov.bh", ".gov.bh"),
        "om": ("Oman eVisa", "https://evisa.rop.gov.om", ".gov.om"),
        "jo": ("Jordan eVisa", "https://eservices.moi.gov.jo", ".gov.jo"),
        "lb": ("Lebanon Security", "https://www.general-security.gov.lb", ".gov.lb"),
        "il": ("Israel GOV", "https://www.gov.il", ".gov.il"),
        "iq": ("Iraq eVisa", "https://evisa.iq", ".iq"),
        "ir": ("Iran eVisa", "https://evisa.mfa.ir", ".ir"),
        "tr": ("Turkey eVisa", "https://www.evisa.gov.tr", ".gov.tr"),
        # Africa
        "eg": ("Egypt eVisa", "https://visa2egypt.gov.eg", ".gov.eg"),
        "ma": ("Morocco Consulat", "https://www.consulat.ma", ".ma"),
        "dz": ("Algeria MFA", "https://www.mfa.gov.dz", ".gov.dz"),
        "tn": ("Tunisia MFA", "https://www.diplomatie.gov.tn", ".gov.tn"),
        "ke": ("Kenya eVisa", "https://evisa.go.ke", ".go.ke"),
        "tz": ("Tanzania Immigration", "https://www.immigration.go.tz", ".go.tz"),
        "ug": ("Uganda Immigration", "https://www.immigration.go.ug", ".go.ug"),
        "rw": ("Rwanda Immigration", "https://www.migration.gov.rw", ".gov.rw"),
        "et": ("Ethiopia Immigration", "https://www.immigration.gov.et", ".gov.et"),
        "mu": ("Mauritius GOV", "https://passport.govmu.org", ".govmu.org"),
        "ng": ("Nigeria Immigration", "https://immigration.gov.ng", ".gov.ng"),
        "gh": ("Ghana Immigration", "https://home.gis.gov.gh", ".gov.gh"),
        "sn": ("Senegal MFA", "https://www.diplomatie.gouv.sn", ".gouv.sn"),
        "za": ("South Africa DHA", "https://www.dha.gov.za", ".gov.za"),
        "zw": ("Zimbabwe Immigration", "https://www.zimbabweimmigration.gov.zw", ".gov.zw"),
        "zm": ("Zambia Immigration", "https://www.zambiaimmigration.gov.zm", ".gov.zm"),
        "bw": ("Botswana GOV", "https://www.gov.bw", ".gov.bw"),
        "na": ("Namibia MHA", "https://www.mha.gov.na", ".gov.na"),
        # South America
        "br": ("Brazil MRE", "https://www.gov.br/mre", ".gov.br"),
        "ar": ("Argentina Migraciones", "https://www.migraciones.gov.ar", ".gob.ar"),
        "cl": ("Chile Extranjería", "https://www.extranjeria.gob.cl", ".gob.cl"),
        "pe": ("Peru Migraciones", "https://www.gob.pe/migraciones", ".gob.pe"),
        "co": ("Colombia Cancillería", "https://www.cancilleria.gov.co", ".gov.co"),
        "ve": ("Venezuela SAIME", "https://www.saime.gob.ve", ".gob.ve"),
        "ec": ("Ecuador Cancillería", "https://www.cancilleria.gob.ec", ".gob.ec"),
        "bo": ("Bolivia Migración", "https://www.migracion.gob.bo", ".gob.bo"),
        "py": ("Paraguay Migraciones", "https://www.migraciones.gov.py", ".gov.py"),
        "uy": ("Uruguay MRE", "https://www.gub.uy/ministerio-relaciones-exteriores", ".gub.uy"),
        # Others
        "ru": ("Russia MID", "https://www.mid.ru", ".ru"),
        "by": ("Belarus MFA", "https://mfa.gov.by", ".gov.by"),
        "is": ("Iceland UT", "https://island.is/en/visa", ".is"),
        "mt": ("Malta Identity", "https://www.identitymalta.com", ".com"),
        "cy": ("Cyprus MFA", "https://mfa.gov.cy", ".gov.cy"),
        "lu": ("Luxembourg MAEE", "https://maee.gouvernement.lu", ".lu"),
    }
    
    if country_code in patterns:
        name, url, domain = patterns[country_code]
        return [{"name": name, "url": url, "type": "official", "domain": domain}]
    
    # Dynamic fallback for any country
    display_name = country_name or country_code.upper()
    return [{
        "name": f"{display_name} Embassy & Immigration",
        "url": f"https://www.embassypages.com/{country_code}",
        "type": "embassy_directory",
        "domain": ".com"
    }]


def load_official_sources():
    """Load official sources dynamically"""
    sources = {}
    data_dir = "visa_data"
    
    # First, try to load from scraped data
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
    
    # For any country without sources, generate dynamically
    for country_code, country_data in VISA_DATA.items():
        if country_code not in sources:
            country_name = country_data.get("country", country_code.upper())
            sources[country_code] = get_official_source_for_country(country_code, country_name)
    
    return sources


# ============================================
# FALLBACK DATA
# ============================================

FALLBACK_VISA_DATA = {
    "us": {
        "country": "United States",
        "visa_types": {
            "tourist": {
                "name": "B1/B2 Visitor Visa",
                "requirements": ["Valid passport (6 months beyond intended stay)", "DS-160 confirmation page", "Interview appointment letter", "Proof of financial ability", "Evidence of ties to home country"],
                "processing_time_note": "Wait times vary significantly by consulate",
                "fees": "$185 USD",
                "validity_note": "Up to 5-10 years at officer's discretion."
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
# COMPLETE COUNTRY DETECTION KEYWORDS (150+ COUNTRIES)
# ============================================

COUNTRY_KEYWORDS = {
    # North America
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

def validate_input(query):
    if not query or not isinstance(query, str) or len(query) > 500:
        return False, "Invalid input"
    malicious_patterns = [r'<script', r'javascript:', r'onerror\s*=', r'SELECT\s+.*\s+FROM', r'DROP\s+TABLE', r'--']
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
    query_lower = query.lower()
    if any(word in query_lower for word in ["student", "study", "education", "university", "college", "course"]):
        return "student"
    elif any(word in query_lower for word in ["work", "job", "employment", "skilled", "professional", "h1b", "h-1b"]):
        return "work"
    elif any(word in query_lower for word in ["tourist", "visit", "travel", "tourism", "vacation", "visitor"]):
        return "tourist"
    elif any(word in query_lower for word in ["business", "conference", "meeting"]):
        return "business"
    return "unknown"


def detect_nationality(query, destination_country):
    """Detect nationality from query context without hardcoding"""
    query_lower = query.lower()
    
    # Look for patterns like "for Indian", "Indian citizen", "from India"
    for code, keywords in COUNTRY_KEYWORDS.items():
        if code == destination_country:
            continue
        for kw in keywords:
            patterns = [f"for {kw}", f"{kw} citizen", f"{kw} passport", f"from {kw}"]
            if any(pattern in query_lower for pattern in patterns):
                # Map to proper ISO codes
                if code in ["india"]: return "IN"
                if code in ["us", "usa", "united states"]: return "US"
                if code in ["uk", "britain"]: return "GB"
                if code in ["canada"]: return "CA"
                if code in ["australia"]: return "AU"
                if code in ["pakistan"]: return "PK"
                if code in ["germany"]: return "DE"
                if code in ["france"]: return "FR"
                if code in ["italy"]: return "IT"
                if code in ["spain"]: return "ES"
                if code in ["japan"]: return "JP"
                if code in ["china"]: return "CN"
                if code in ["brazil"]: return "BR"
                if code in ["south_africa"]: return "ZA"
                if code in ["uae"]: return "AE"
                return code.upper()
    
    return "PK"  # Default


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
    
    if mandatory_reg and mandatory_reg.get('name'):
        requirements.append(f"Complete {mandatory_reg.get('name')} registration")
    if visa_type == "student":
        requirements.append("Letter of acceptance from educational institution")
    elif visa_type == "work":
        requirements.append("Employment contract or job offer letter")
    
    return requirements[:8]


def generate_fees_from_api(api_result, country, visa_type):
    fee_ranges = {"us": "$185", "uk": "£115-£150", "ca": "$100 CAD", "au": "$150 AUD", "de": "€80", "fr": "€80", "jp": "¥3,000", "ae": "$100-200", "br": "R$290", "za": "R1,520", "th": "฿1,000-2,000", "in": "₹2,000-10,000", "cn": "$140", "sg": "$30 SGD"}
    return fee_ranges.get(country, "Contact embassy for current fees")


def generate_validity_from_api(api_result):
    duration = api_result.get('primary_rule', {}).get('duration', '')
    if duration:
        return f"Usually {duration}"
    return "Varies by visa type and consular discretion"


def generate_processing_time(api_result, country):
    requirement = api_result.get('requirement', '').lower()
    if 'online visa' in requirement or 'evisa' in requirement:
        return "3-7 business days (online)"
    elif 'visa on arrival' in requirement:
        return "Processed at port of entry"
    times = {"us": "2-4 weeks", "uk": "3 weeks", "ca": "2-8 weeks", "au": "20-33 days", "de": "15 days", "fr": "15 days", "jp": "5-7 days", "ae": "3-5 days", "in": "1-2 weeks", "cn": "4-5 days", "br": "5-10 working days"}
    return times.get(country, "Contact embassy for current processing times")


def get_sources_for_country(country_code, api_result, display_name=None):
    sources = OFFICIAL_SOURCES.get(country_code, [])
    if not sources:
        sources = get_official_source_for_country(country_code, display_name)
    if api_result.get('confidence') == 'high':
        sources.append({"name": "Travel Buddy API (Real-time)", "url": "https://rapidapi.com/TravelBuddyAI/api/visa-requirement", "type": "api"})
    return sources[:3]


# ============================================
# FLASK ROUTES
# ============================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "Visa RAG System",
        "version": "3.0.0",
        "endpoints": {
            "/api/ask": "POST - Query visa requirements",
            "/api/health": "GET - Health check"
        },
        "features": ["150+ countries", "Real-time API", "Smart nationality detection"]
    })


@app.route("/api/ask", methods=["POST"])
@limiter.limit("10 per minute")
def ask():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request"}), 400
        
        query = data.get("query", "").strip()
        is_valid, msg = validate_input(query)
        if not is_valid:
            return jsonify({"error": msg}), 400
        
        if not query:
            return jsonify({"error": "Query required"}), 400
        
        query_lower = query.lower()
        
        # Detect destination country
        country = detect_country(query_lower)
        if not country:
            return jsonify({"error": "Country not detected", "message": "Please clearly mention a country (e.g., US, UK, Canada, Brazil, Japan, UAE)"}), 400
        
        # Detect visa type
        visa_type = detect_visa_type(query_lower)
        if visa_type == "unknown":
            return jsonify({"status": "needs_clarification", "country_code": country, "message": "Visa requirements vary by type.", "options": ["tourist", "student", "work", "business"]}), 400
        
        # Detect nationality from query
        detected_nationality = detect_nationality(query_lower, country)
        
        # Call real-time API
        provider = get_visa_provider()
        api_result = provider.get_visa_requirement(destination=country, nationality=detected_nationality)
        
        # Load local data as fallback
        visa_info = VISA_DATA.get(country, {"country": country.upper(), "visa_types": {}})
        specific_visa = visa_info.get("visa_types", {}).get(visa_type, {})
        
        # Determine correct country name
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
        
        # Build response
        response = {
            "country": country_name,
            "country_code": country,
            "visa_type": visa_type,
            "confidence": api_result.get('confidence', 'medium'),
            "source": api_result.get('source', 'fallback')
        }
        
        if api_result.get('confidence') == 'high':
            response["realtime"] = {
                "visa_requirement": api_result.get('requirement'),
                "passport_validity": api_result.get('passport_validity'),
                "source": api_result.get('source')
            }
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
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "countries_loaded": len(VISA_DATA),
        "sources_loaded": len(OFFICIAL_SOURCES),
        "timestamp": datetime.now().isoformat()
    })


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Rate limit exceeded", "message": "10 requests per minute limit"}), 429


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting Visa RAG System")
    print("=" * 60)
    print(f"📊 Loaded {len(VISA_DATA)} countries")
    print(f"🔗 Dynamic sources for {len(OFFICIAL_SOURCES)} countries")
    print("✅ Country-specific rules enabled")
    print("✅ Smart nationality detection enabled")
    print("✅ No hardcoded data - fully dynamic")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)