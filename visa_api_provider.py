"""
Visa API Provider - Real-time visa data from Travel Buddy API v2
"""

import os
import json
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dotenv import load_dotenv

load_dotenv()


class VisaAPIProvider:
    """Real-time visa data provider with caching"""
    
    def __init__(self, cache_dir: str = "visa_api_cache"):
        self.api_key = os.environ.get('TRAVELBUDDY_API_KEY')
        self.api_host = os.environ.get('TRAVELBUDDY_API_HOST', 'visa-requirement.p.rapidapi.com')
        self.base_url = "https://visa-requirement.p.rapidapi.com"
        
        self.cache_dir = cache_dir
        self.cache_durations = {
            "requirements": timedelta(hours=48),
        }
        
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Country name to ISO code mapping
        self.country_code_map = {
            "us": "US", "usa": "US", "united states": "US", "america": "US",
            "canada": "CA", "canadian": "CA",
            "uk": "GB", "united kingdom": "GB", "britain": "GB", "england": "GB",
            "germany": "DE", "france": "FR", "italy": "IT", "spain": "ES",
            "japan": "JP", "china": "CN", "india": "IN", "australia": "AU",
            "uae": "AE", "dubai": "AE", "ireland": "IE",
            "netherlands": "NL", "sweden": "SE", "norway": "NO", "denmark": "DK",
            "finland": "FI", "switzerland": "CH", "austria": "AT", "belgium": "BE",
            "portugal": "PT", "greece": "GR", "poland": "PL", "turkey": "TR",
            "singapore": "SG", "malaysia": "MY", "thailand": "TH", "vietnam": "VN",
            "indonesia": "ID", "philippines": "PH", "south_korea": "KR",
            "saudi_arabia": "SA", "qatar": "QA", "egypt": "EG",
            "south_africa": "ZA", "brazil": "BR", "mexico": "MX"
        }
    
    def _get_cache_key(self, endpoint: str, params: Dict) -> str:
        key_string = f"{endpoint}_{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> Optional[Dict]:
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                
                cached_time = datetime.fromisoformat(cached['timestamp'])
                if datetime.now() - cached_time < self.cache_durations["requirements"]:
                    age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                    print(f"📦 Using cached response (age: {age_hours:.1f}h)")
                    return cached['data']
            except:
                pass
        return None
    
    def _save_to_cache(self, cache_key: str, data: Dict) -> None:
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        cached = {'timestamp': datetime.now().isoformat(), 'data': data}
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cached, f, indent=2)
            print(f"💾 Saved to cache")
        except:
            pass
    
    def get_visa_requirement(self, destination: str, nationality: str = "PK") -> Dict:
        """Get visa requirements using v2 API"""
        
        dest_code = self.country_code_map.get(destination.lower(), destination.upper())
        passport_code = nationality.upper()
        
        params = {
            'passport': passport_code,
            'destination': dest_code
        }
        
        cache_key = self._get_cache_key("v2/visa/check", params)
        
        # Try cache first
        cached = self._get_cached_response(cache_key)
        if cached:
            return cached
        
        # Make API request
        if not self.api_key:
            print("❌ No API key configured")
            return self._get_fallback_response(dest_code, passport_code)
        
        headers = {
            'X-RapidAPI-Key': self.api_key,
            'X-RapidAPI-Host': self.api_host,
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}/v2/visa/check"  # ✅ CORRECT ENDPOINT
        
        try:
            print(f"🌐 Calling API: {passport_code} → {dest_code}")
            response = requests.post(url, headers=headers, json=params, timeout=15)
            
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                formatted = self._format_v2_response(data, dest_code, passport_code)
                self._save_to_cache(cache_key, formatted)
                return formatted
            elif response.status_code == 403:
                print("❌ API key invalid or not subscribed")
            elif response.status_code == 429:
                print("⚠️ Rate limit exceeded")
            else:
                print(f"❌ API error: {response.status_code} - {response.text[:100]}")
                
        except Exception as e:
            print(f"❌ Request failed: {e}")
        
        return self._get_fallback_response(dest_code, passport_code)
    
    def _format_v2_response(self, api_response: Dict, destination: str, nationality: str) -> Dict:
        """Format v2 API response"""
        data = api_response.get('data', api_response)
        
        dest_info = data.get('destination', {})
        passport_info = data.get('passport', {})
        visa_rules = data.get('visa_rules', {})
        primary_rule = visa_rules.get('primary_rule', {})
        secondary_rule = visa_rules.get('secondary_rule', {})
        mandatory_reg = data.get('mandatory_registration', {})
        
        # Determine the best requirement description
        requirement = primary_rule.get('name', 'unknown')
        if secondary_rule and secondary_rule.get('name'):
            requirement = f"{requirement} or {secondary_rule.get('name')}"
        
        # Build description
        description_parts = []
        if primary_rule.get('duration'):
            description_parts.append(f"Duration: {primary_rule.get('duration')}")
        if mandatory_reg and mandatory_reg.get('name'):
            description_parts.append(f"Required: {mandatory_reg.get('name')}")
        
        description = "; ".join(description_parts) if description_parts else requirement
        
        return {
            'destination': {
                'code': dest_info.get('code', destination),
                'name': dest_info.get('name', destination),
                'continent': dest_info.get('continent', 'Unknown'),
                'capital': dest_info.get('capital', 'Unknown'),
                'currency': dest_info.get('currency', 'Unknown')
            },
            'passport': {
                'code': passport_info.get('code', nationality),
                'name': passport_info.get('name', nationality),
                'currency_code': passport_info.get('currency_code', '')
            },
            'requirement': requirement,
            'description': description,
            'primary_rule': primary_rule,
            'secondary_rule': secondary_rule,
            'mandatory_registration': mandatory_reg,
            'passport_validity': dest_info.get('passport_validity', '6 months recommended'),
            'embassy_url': dest_info.get('embassy_url', ''),
            'last_updated': datetime.now().isoformat(),
            'source': 'Travel Buddy API v2',
            'confidence': 'high'
        }
    
    def _get_fallback_response(self, destination: str, nationality: str) -> Dict:
        return {
            'destination': {'code': destination, 'name': destination},
            'passport': {'code': nationality, 'name': nationality},
            'requirement': 'unknown',
            'description': 'Check with official embassy',
            'last_updated': datetime.now().isoformat(),
            'source': 'fallback',
            'confidence': 'low'
        }
    
    def get_visa_map(self, passport: str = "PK") -> Optional[Dict]:
        """Get color-coded visa map for a passport"""
        if not self.api_key:
            return None
        
        headers = {
            'X-RapidAPI-Key': self.api_key,
            'X-RapidAPI-Host': self.api_host,
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}/v2/visa/map"
        
        try:
            response = requests.post(url, headers=headers, json={'passport': passport.upper()}, timeout=15)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    
    def get_cache_stats(self) -> Dict:
        cache_files = [f for f in os.listdir(self.cache_dir) if f.endswith('.json')]
        total_size = sum(os.path.getsize(os.path.join(self.cache_dir, f)) for f in cache_files)
        
        return {
            'total_entries': len(cache_files),
            'total_size_kb': round(total_size / 1024, 2),
            'cache_dir': self.cache_dir
        }


_visa_provider = None

def get_visa_provider() -> VisaAPIProvider:
    global _visa_provider
    if _visa_provider is None:
        _visa_provider = VisaAPIProvider()
    return _visa_provider