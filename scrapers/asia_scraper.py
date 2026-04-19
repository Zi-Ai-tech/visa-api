from .base_scraper import BaseScraper
from datetime import datetime
from typing import Dict

class AsiaScraper:
    """Scraper for Asian countries"""
    
    def __init__(self):
        self.countries = {
            "japan": {"name": "Japan", "visa_url": "https://www.mofa.go.jp/j_info/visit/visa/"},
            "china": {"name": "China", "visa_url": "https://www.visaforchina.cn"},
            "india": {"name": "India", "visa_url": "https://indianvisaonline.gov.in"},
            "singapore": {"name": "Singapore", "visa_url": "https://www.ica.gov.sg"},
            "malaysia": {"name": "Malaysia", "visa_url": "https://www.imi.gov.my"},
            "south_korea": {"name": "South Korea", "visa_url": "https://www.visa.go.kr"},
            "thailand": {"name": "Thailand", "visa_url": "https://www.thaievisa.go.th"},
            "vietnam": {"name": "Vietnam", "visa_url": "https://evisa.xuatnhapcanh.gov.vn"},
            "indonesia": {"name": "Indonesia", "visa_url": "https://www.imigrasi.go.id"},
            "philippines": {"name": "Philippines", "visa_url": "https://immigration.gov.ph"}
        }
    
    def scrape_all(self) -> Dict[str, Dict]:
        """Scrape all Asian countries"""
        results = {}
        
        for code, info in self.countries.items():
            print(f"🌏 Scraping {info['name']}...")
            
            scraper = BaseScraper(code, info['name'])
            
            data = {
                "country": info['name'],
                "last_updated": datetime.now().strftime('%Y-%m-%d'),
                "visas": {
                    "tourist": self._get_tourist_data(code, info['name']),
                },
                "sources": [{
                    "name": f"{info['name']} Immigration",
                    "url": info['visa_url'],
                    "type": "official"
                }]
            }
            
            scraper.save_data(data)
            results[code] = data
            
            import time
            time.sleep(1)
        
        return results
    
    def _get_tourist_data(self, code: str, country: str) -> Dict:
        """Get tourist visa data for Asian country"""
        data = {
            "requirements": [
                "Valid passport (6 months validity)",
                "Completed visa application",
                "Passport photos",
                "Flight booking",
                "Hotel reservation",
                "Proof of funds"
            ],
            "processing_time": "3-7 working days",
            "fees": "Varies by nationality",
            "validity": "30-90 days",
            "ielts_required": False
        }
        
        # Country-specific adjustments
        if code == "japan":
            data["fees"] = "¥3,000"
            data["processing_time"] = "5 working days"
        elif code == "china":
            data["fees"] = "$140"
            data["requirements"].append("Invitation letter (if applicable)")
        elif code == "south_korea":
            data["fees"] = "$40-90"
            data["validity"] = "90 days"
        
        return data