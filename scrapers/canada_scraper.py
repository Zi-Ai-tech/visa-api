from .base_scraper import BaseScraper
from datetime import datetime
from typing import Dict

class CanadaScraper(BaseScraper):
    def __init__(self):
        super().__init__("canada", "Canada")
        self.urls = {
            "tourist": "https://www.canada.ca/en/immigration-refugees-citizenship/services/visit-canada.html",
            "student": "https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada.html",
            "work": "https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada.html"
        }
    
    def scrape(self) -> Dict:
        print(f"🇨🇦 Scraping {self.country_name} visa information...")
        
        data = {
            "country": self.country_name,
            "last_updated": datetime.now().strftime('%Y-%m-%d'),
            "visas": {},
            "sources": [
                {
                    "name": "Immigration, Refugees and Citizenship Canada",
                    "url": "https://www.canada.ca/en/immigration-refugees-citizenship.html",
                    "type": "official",
                    "domain_type": ".gc.ca"
                }
            ]
        }
        
        # Scrape tourist visa
        data["visas"]["tourist"] = self._scrape_tourist_visa()
        
        # Scrape student visa
        data["visas"]["student"] = self._scrape_student_visa()
        
        # Scrape work visa
        data["visas"]["work"] = self._scrape_work_visa()
        
        return data
    
    def _scrape_tourist_visa(self) -> Dict:
        return {
            "requirements": [
                "Valid passport",
                "Proof of funds (minimum $1,000 CAD/month)",
                "Purpose of travel",
                "Ties to home country",
                "No criminal record",
                "Medical exam (if required)"
            ],
            "documents": [
                "Bank statements (last 4 months)",
                "Employment letter",
                "Travel itinerary",
                "Invitation letter (if applicable)",
                "Travel history"
            ],
            "processing_time": "2-8 weeks depending on country",
            "fees": "$100 CAD",
            "validity": "Up to 10 years or passport expiry",
            "ielts_required": False,
            "biometrics_required": True
        }
    
    def _scrape_student_visa(self) -> Dict:
        return {
            "requirements": [
                "Acceptance letter from DLI",
                "Proof of funds (tuition + $10,000 CAD living expenses)",
                "No criminal record",
                "Medical exam",
                "Statement of purpose"
            ],
            "documents": [
                "Letter of acceptance",
                "Financial proof",
                "Academic transcripts",
                "IELTS/TOEFL scores",
                "Passport",
                "Digital photo"
            ],
            "processing_time": "4-8 weeks",
            "fees": "$150 CAD",
            "validity": "Duration of studies + 90 days",
            "ielts_required": True,
            "minimum_ielts_score": "6.0 overall",
            "biometrics_required": True
        }
    
    def _scrape_work_visa(self) -> Dict:
        return {
            "requirements": [
                "Job offer from Canadian employer",
                "LMIA (if required)",
                "Proof of qualifications",
                "Work experience",
                "No criminal record"
            ],
            "documents": [
                "Employment contract",
                "CV/Resume",
                "Qualification certificates",
                "Reference letters",
                "Police clearance"
            ],
            "processing_time": "2-6 months",
            "fees": "$155 - $1,000 CAD",
            "validity": "1-3 years (renewable)",
            "ielts_required": False,
            "biometrics_required": True
        }