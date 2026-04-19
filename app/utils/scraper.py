import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

class VisaScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def scrape_country(self, country_code, urls):
        """Scrape visa information for a country"""
        data = {
            "country": "",
            "country_code": country_code,
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "visas": {},
            "sources": []
        }
        
        for url_config in urls:
            try:
                response = requests.get(url_config["url"], headers=self.headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract structured data (customize per country)
                extracted = self._extract_visa_info(soup, url_config["type"])
                data["visas"].update(extracted)
                
                data["sources"].append({
                    "name": url_config["name"],
                    "url": url_config["url"],
                    "type": "official",
                    "last_verified": datetime.now().strftime("%Y-%m-%d")
                })
                
            except Exception as e:
                print(f"Error scraping {url_config['url']}: {e}")
        
        return data
    
    def _extract_visa_info(self, soup, visa_type):
        """Extract visa information from HTML"""
        # This needs to be customized per country website
        # Placeholder implementation
        return {}
    
    def save_country_data(self, country_code, data):
        """Save scraped data to JSON file"""
        file_path = f"app/data/countries/{country_code}.json"
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved data for {country_code}")