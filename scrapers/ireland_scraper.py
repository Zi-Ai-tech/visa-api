from .base_scraper import BaseScraper
from datetime import datetime
from typing import Dict

class IrelandScraper(BaseScraper):
    def __init__(self):
        super().__init__("ireland", "Ireland")
    
    def scrape(self) -> Dict:
        print(f"🇮🇪 Scraping {self.country_name} visa information...")
        
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
                    "name": "Irish Immigration Service",
                    "url": "https://www.irishimmigration.ie",
                    "type": "official",
                    "domain_type": ".ie"
                }
            ]
        }
        
        return data
    
    def _get_tourist_data(self) -> Dict:
        return {
            "requirements": [
                "Valid passport (6 months validity)",
                "Completed application form",
                "Passport photos",
                "Travel itinerary",
                "Proof of accommodation",
                "Proof of funds (€50/day)",
                "Travel insurance"
            ],
            "processing_time": "8 weeks",
            "fees": "€80",
            "validity": "90 days",
            "ielts_required": False
        }
    
    def _get_student_data(self) -> Dict:
        return {
            "requirements": [
                "Acceptance letter from Irish institution",
                "Proof of funds (€7,000)",
                "Private medical insurance",
                "English proficiency",
                "Police clearance"
            ],
            "processing_time": "4-8 weeks",
            "fees": "€100",
            "validity": "Course duration + 2 years",
            "ielts_required": True,
            "minimum_ielts_score": "6.0 overall"
        }
    
    def _get_work_data(self) -> Dict:
        return {
            "requirements": [
                "Employment permit",
                "Job offer from Irish employer",
                "Relevant qualifications",
                "Proof of experience"
            ],
            "processing_time": "8-12 weeks",
            "fees": "€500-1,000",
            "validity": "2 years (renewable)",
            "ielts_required": True
        }