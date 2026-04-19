from .base_scraper import BaseScraper
from datetime import datetime
from typing import Dict

class AustraliaScraper(BaseScraper):
    def __init__(self):
        super().__init__("australia", "Australia")
    
    def scrape(self) -> Dict:
        print(f"🇦🇺 Scraping {self.country_name} visa information...")
        
        data = {
            "country": self.country_name,
            "last_updated": datetime.now().strftime('%Y-%m-%d'),
            "visas": {
                "tourist": self._get_tourist_data(),
                "student": self._get_student_data(),
                "work": self._get_work_data()
            },
            "sources": [
                {
                    "name": "Department of Home Affairs",
                    "url": "https://immi.homeaffairs.gov.au",
                    "type": "official",
                    "domain_type": ".gov.au"
                }
            ]
        }
        
        return data
    
    def _get_tourist_data(self) -> Dict:
        return {
            "requirements": [
                "Valid passport",
                "Completed application form",
                "Proof of funds ($5,000+ AUD)",
                "Travel itinerary",
                "Health insurance",
                "Character certificate"
            ],
            "processing_time": "20-33 days",
            "fees": "$150 AUD",
            "validity": "3, 6, or 12 months",
            "ielts_required": False
        }
    
    def _get_student_data(self) -> Dict:
        return {
            "requirements": [
                "Confirmation of Enrolment (CoE)",
                "Genuine Temporary Entrant statement",
                "Proof of funds ($21,041 AUD/year)",
                "Health insurance (OSHC)",
                "English proficiency",
                "Health examination"
            ],
            "processing_time": "4-8 weeks",
            "fees": "$650 AUD",
            "validity": "Course duration",
            "ielts_required": True,
            "minimum_ielts_score": "5.5 - 6.5"
        }
    
    def _get_work_data(self) -> Dict:
        return {
            "requirements": [
                "Sponsorship by Australian employer",
                "Skills assessment",
                "Relevant work experience",
                "English proficiency",
                "Health and character checks"
            ],
            "processing_time": "3-12 months",
            "fees": "$4,115 AUD",
            "validity": "Up to 4 years",
            "ielts_required": True,
            "minimum_ielts_score": "6.0 in each band"
        }