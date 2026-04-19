import re
import json
import os

class IntentService:
    def __init__(self):
        self.country_keywords = self._load_country_keywords()
        self.visa_type_keywords = {
            "student": ["student", "study", "education", "university", "college", "course"],
            "tourist": ["tourist", "visit", "travel", "tourism", "vacation", "holiday"],
            "work": ["work", "employment", "job", "business", "skilled", "professional"],
            "business": ["business", "conference", "meeting", "corporate"],
            "transit": ["transit", "layover", "connecting", "stopover"],
            "family": ["family", "spouse", "partner", "dependent", "relative"],
            "immigrant": ["immigrant", "permanent", "residence", "settle", "migrate"]
        }
    
    def _load_country_keywords(self):
        """Load country keywords from JSON files"""
        keywords = {}
        data_dir = os.path.join('app', 'data', 'countries')
        
        if os.path.exists(data_dir):
            for filename in os.listdir(data_dir):
                if filename.endswith('.json'):
                    country_code = filename.replace('.json', '')
                    file_path = os.path.join(data_dir, filename)
                    try:
                        with open(file_path, 'r') as f:
                            data = json.load(f)
                            keywords[country_code] = data.get("keywords", [country_code])
                    except:
                        keywords[country_code] = [country_code]
        
        # Fallback keywords if no data files
        if not keywords:
            keywords = {
                "us": ["us", "usa", "united states", "america", "american"],
                "uk": ["uk", "united kingdom", "britain", "british", "england"],
                "canada": ["canada", "canadian"],
                "ireland": ["ireland", "irish"],
                "australia": ["australia", "australian"],
                "germany": ["germany", "german", "deutschland"],
                "france": ["france", "french"],
                "uae": ["uae", "dubai", "emirates", "abu dhabi"]
            }
        
        return keywords
    
    def detect_intent(self, query):
        """Detect country, visa type, and special requirements from query"""
        query_lower = query.lower()
        
        # Detect country
        country = self._detect_country(query_lower)
        
        # Detect visa type
        visa_type = self._detect_visa_type(query_lower)
        
        # Check for Pakistani-specific query
        is_pakistani = self._is_pakistani_query(query_lower)
        
        # Extract additional context
        is_urgent = any(word in query_lower for word in ["urgent", "emergency", "fast", "quick", "priority"])
        needs_fee_info = any(word in query_lower for word in ["fee", "cost", "price", "charge", "expense"])
        
        return {
            "country": country,
            "visa_type": visa_type,
            "is_pakistani": is_pakistani,
            "is_urgent": is_urgent,
            "needs_fee_info": needs_fee_info,
            "original_query": query
        }
    
    def _detect_country(self, query):
        """Detect country from query"""
        detected = []
        
        for country_code, keywords in self.country_keywords.items():
            if any(keyword in query for keyword in keywords):
                detected.append(country_code)
        
        return detected[0] if detected else "unknown"
    
    def _detect_visa_type(self, query):
        """Detect visa type from query"""
        for visa_type, keywords in self.visa_type_keywords.items():
            if any(keyword in query for keyword in keywords):
                return visa_type
        
        return "unknown"
    
    def _is_pakistani_query(self, query):
        """Check if query is specifically for Pakistani nationals"""
        pakistani_keywords = ["pakistani", "pakistan", "from pakistan", "pakistani citizen"]
        return any(keyword in query for keyword in pakistani_keywords)
    
    def get_available_countries(self):
        """Return list of available countries"""
        return list(self.country_keywords.keys())