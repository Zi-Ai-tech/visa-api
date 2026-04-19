from .base_scraper import BaseScraper
from datetime import datetime
from typing import Dict

class MiddleEastScraper:
    """Scraper for Middle Eastern countries"""
    
    def __init__(self):
        self.countries = {
            "uae": {"name": "UAE", "visa_url": "https://u.ae/en/information-and-services/visa-and-emirates-id"},
            "saudi_arabia": {"name": "Saudi Arabia", "visa_url": "https://visa.mofa.gov.sa"},
            "qatar": {"name": "Qatar", "visa_url": "https://portal.moi.gov.qa"},
            "kuwait": {"name": "Kuwait", "visa_url": "https://evisa.moi.gov.kw"},
            "bahrain": {"name": "Bahrain", "visa_url": "https://www.evisa.gov.bh"},
            "oman": {"name": "Oman", "visa_url": "https://evisa.rop.gov.om"},
            "egypt": {"name": "Egypt", "visa_url": "https://visa2egypt.gov.eg"},
            "turkey": {"name": "Turkey", "visa_url": "https://www.evisa.gov.tr"}
        }
    
    def scrape_all(self) -> Dict[str, Dict]:
        """Scrape all Middle Eastern countries"""
        results = {}
        
        for code, info in self.countries.items():
            print(f"🕌 Scraping {info['name']}...")
            
            scraper = BaseScraper(code, info['name'])
            
            data = {
                "country": info['name'],
                "last_updated": datetime.now().strftime('%Y-%m-%d'),
                "visas": {
                    "tourist": self._get_tourist_data(code),
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
    
    def _get_tourist_data(self, code: str) -> Dict:
        """Get tourist visa data for Middle Eastern country"""
        data = {
            "requirements": [
                "Valid passport (6 months validity)",
                "Passport photos",
                "Hotel booking",
                "Return flight ticket"
            ],
            "processing_time": "3-5 working days",
            "fees": "$100-200",
            "validity": "30-90 days",
            "ielts_required": False
        }
        
        if code == "uae":
            data["fees"] = "$100-200"
            data["validity"] = "30-90 days"
        elif code == "saudi_arabia":
            data["fees"] = "$130"
            data["requirements"].append("Travel insurance")
        elif code == "turkey":
            data["fees"] = "$60"
            data["processing_time"] = "24-48 hours (e-Visa)"
        
        return data