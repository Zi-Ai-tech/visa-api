from .base_scraper import BaseScraper
from datetime import datetime
from typing import Dict
import re

class USScraper(BaseScraper):
    def __init__(self):
        super().__init__("us", "United States")
        self.urls = {
            "tourist": "https://travel.state.gov/content/travel/en/us-visas/tourism-visit/visitor.html",
            "student": "https://travel.state.gov/content/travel/en/us-visas/study/student-visa.html",
            "work": "https://travel.state.gov/content/travel/en/us-visas/employment/visas-members-permanent-professions.html"
        }
    
    def scrape(self) -> Dict:
        print(f"🇺🇸 Scraping {self.country_name} visa information...")
        
        data = {
            "country": self.country_name,
            "last_updated": datetime.now().strftime('%Y-%m-%d'),
            "visas": {},
            "sources": []
        }
        
        # Scrape tourist visa
        tourist_data = self._scrape_tourist_visa()
        if tourist_data:
            data["visas"]["tourist"] = tourist_data
        
        # Scrape student visa
        student_data = self._scrape_student_visa()
        if student_data:
            data["visas"]["student"] = student_data
        
        # Scrape work visa
        work_data = self._scrape_work_visa()
        if work_data:
            data["visas"]["work"] = work_data
        
        # Add sources
        data["sources"] = [
            {
                "name": "U.S. Department of State",
                "url": "https://travel.state.gov",
                "type": "official",
                "domain_type": ".gov"
            },
            {
                "name": "USCIS",
                "url": "https://www.uscis.gov",
                "type": "official",
                "domain_type": ".gov"
            }
        ]
        
        return data
    
    def _scrape_tourist_visa(self) -> Dict:
        """Scrape B1/B2 tourist visa information"""
        soup = self._make_request(self.urls["tourist"])
        if not soup:
            return self._get_fallback_tourist_data()
        
        data = {
            "requirements": [],
            "documents": [],
            "processing_time": "2-4 weeks for interview scheduling",
            "fees": "$185",
            "validity": "10 years (B1/B2)",
            "ielts_required": False,
            "interview_required": True
        }
        
        # Extract requirements
        req_selectors = [
            ".tsg-rwd-text li",
            ".field-item li",
            "article li"
        ]
        data["requirements"] = self._extract_list(soup, req_selectors)[:8]
        
        # Extract fees
        fee_text = self._extract_text(soup, [".fee-info", ".fees", "p:contains('$')"])
        if fee_text:
            fee_match = re.search(r'\$\d+', fee_text)
            if fee_match:
                data["fees"] = fee_match.group()
        
        return data
    
    def _scrape_student_visa(self) -> Dict:
        """Scrape F1/M1 student visa information"""
        soup = self._make_request(self.urls["student"])
        if not soup:
            return self._get_fallback_student_data()
        
        data = {
            "requirements": [],
            "documents": [],
            "processing_time": "2-4 weeks",
            "fees": "$185 + $350 SEVIS fee",
            "validity": "Duration of studies",
            "ielts_required": True,
            "interview_required": True
        }
        
        req_selectors = [".tsg-rwd-text li", ".field-item li", "article li"]
        data["requirements"] = self._extract_list(soup, req_selectors)[:8]
        
        return data
    
    def _scrape_work_visa(self) -> Dict:
        """Scrape work visa information"""
        soup = self._make_request(self.urls["work"])
        if not soup:
            return self._get_fallback_work_data()
        
        data = {
            "requirements": [],
            "documents": [],
            "processing_time": "Varies by visa category",
            "fees": "$190 - $715",
            "validity": "1-3 years (renewable)",
            "ielts_required": False,
            "interview_required": True
        }
        
        return data
    
    def _get_fallback_tourist_data(self) -> Dict:
        """Fallback data if scraping fails"""
        return {
            "requirements": [
                "Valid passport (6 months validity)",
                "DS-160 form",
                "Visa fee payment receipt",
                "Passport photo",
                "Interview appointment",
                "Proof of ties to home country"
            ],
            "processing_time": "2-4 weeks",
            "fees": "$185",
            "validity": "10 years",
            "ielts_required": False,
            "interview_required": True
        }
    
    def _get_fallback_student_data(self) -> Dict:
        return {
            "requirements": [
                "I-20 form from SEVP school",
                "SEVIS fee payment",
                "DS-160 form",
                "Financial proof",
                "Academic documents"
            ],
            "processing_time": "2-4 weeks",
            "fees": "$185 + $350",
            "ielts_required": True,
            "interview_required": True
        }
    
    def _get_fallback_work_data(self) -> Dict:
        return {
            "requirements": [
                "Job offer from US employer",
                "Labor certification",
                "Petition approval",
                "Qualifications proof"
            ],
            "processing_time": "3-6 months",
            "fees": "$190 - $715",
            "ielts_required": False,
            "interview_required": True
        }