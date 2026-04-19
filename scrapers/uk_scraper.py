from .base_scraper import BaseScraper
from datetime import datetime
from typing import Dict
import re

class UKScraper(BaseScraper):
    def __init__(self):
        super().__init__("uk", "United Kingdom")
        self.base_url = "https://www.gov.uk"
        self.urls = {
            "tourist": "https://www.gov.uk/standard-visitor-visa",
            "student": "https://www.gov.uk/student-visa",
            "work": "https://www.gov.uk/skilled-worker-visa"
        }
    
    def scrape(self) -> Dict:
        print(f"🇬🇧 Scraping {self.country_name} visa information...")
        
        data = {
            "country": self.country_name,
            "last_updated": datetime.now().strftime('%Y-%m-%d'),
            "visas": {},
            "sources": [
                {
                    "name": "UK Visas and Immigration",
                    "url": "https://www.gov.uk/browse/visas-immigration",
                    "type": "official",
                    "domain_type": ".gov.uk"
                }
            ]
        }
        
        # Scrape each visa type
        for visa_type, url in self.urls.items():
            visa_data = self._scrape_visa_type(url, visa_type)
            if visa_data:
                data["visas"][visa_type] = visa_data
        
        return data
    
    def _scrape_visa_type(self, url: str, visa_type: str) -> Dict:
        """Scrape specific visa type"""
        soup = self._make_request(url)
        if not soup:
            return self._get_fallback_data(visa_type)
        
        data = {
            "requirements": [],
            "documents": [],
            "processing_time": "",
            "fees": "",
            "validity": ""
        }
        
        # Extract requirements
        req_selectors = [
            ".govuk-list--bullet li",
            ".requirements-list li",
            "article li"
        ]
        data["requirements"] = self._extract_list(soup, req_selectors)[:8]
        
        # Extract fees
        fee_text = self._extract_text(soup, [
            ".fee-summary",
            "p:contains('fee')",
            "p:contains('cost')"
        ])
        if fee_text:
            fee_match = re.search(r'£[\d,]+', fee_text)
            if fee_match:
                data["fees"] = fee_match.group()
        
        # Extract processing time
        time_text = self._extract_text(soup, [
            "p:contains('processing')",
            "p:contains('decision')"
        ])
        if time_text:
            data["processing_time"] = time_text[:100]
        
        # Set visa-specific defaults
        if visa_type == "student":
            data["ielts_required"] = True
            data["ielts_note"] = "Minimum IELTS 5.5-6.0 depending on institution"
        else:
            data["ielts_required"] = False
        
        return data
    
    def _get_fallback_data(self, visa_type: str) -> Dict:
        """Fallback data for UK visas"""
        fallback = {
            "tourist": {
                "requirements": [
                    "Valid passport",
                    "Proof of funds",
                    "Travel itinerary",
                    "Accommodation details"
                ],
                "processing_time": "3 weeks",
                "fees": "£115",
                "validity": "6 months",
                "ielts_required": False
            },
            "student": {
                "requirements": [
                    "CAS from licensed sponsor",
                    "Proof of funds (£1,334/month)",
                    "English proficiency",
                    "TB test (if applicable)"
                ],
                "processing_time": "3 weeks",
                "fees": "£490",
                "validity": "Course duration + 2 years",
                "ielts_required": True
            },
            "work": {
                "requirements": [
                    "Job offer from licensed sponsor",
                    "Certificate of sponsorship",
                    "Appropriate salary (£38,700+)",
                    "English proficiency"
                ],
                "processing_time": "3 weeks",
                "fees": "£719 - £1,500",
                "validity": "Up to 5 years",
                "ielts_required": True
            }
        }
        return fallback.get(visa_type, {})