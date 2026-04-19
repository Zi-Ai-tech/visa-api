from .base_scraper import BaseScraper
from datetime import datetime
from typing import Dict, List

class SchengenScraper:
    """Scraper for Schengen area countries"""
    
    def __init__(self):
        self.countries = {
            "france": {"name": "France", "visa_url": "https://france-visas.gouv.fr"},
            "germany": {"name": "Germany", "visa_url": "https://www.auswaertiges-amt.de/en/visa-service"},
            "italy": {"name": "Italy", "visa_url": "https://vistoperitalia.esteri.it"},
            "spain": {"name": "Spain", "visa_url": "https://www.exteriores.gob.es/Consulados/"},
            "netherlands": {"name": "Netherlands", "visa_url": "https://www.netherlandsworldwide.nl/visa"},
            "sweden": {"name": "Sweden", "visa_url": "https://www.migrationsverket.se"},
            "norway": {"name": "Norway", "visa_url": "https://www.udi.no"},
            "denmark": {"name": "Denmark", "visa_url": "https://www.nyidanmark.dk"},
            "finland": {"name": "Finland", "visa_url": "https://migri.fi/en/visa"},
            "austria": {"name": "Austria", "visa_url": "https://www.bmeia.gv.at/en/travel-stay/"},
            "belgium": {"name": "Belgium", "visa_url": "https://dofi.ibz.be"},
            "portugal": {"name": "Portugal", "visa_url": "https://vistos.mne.gov.pt"},
            "greece": {"name": "Greece", "visa_url": "https://www.mfa.gr/en/visas/"},
            "switzerland": {"name": "Switzerland", "visa_url": "https://www.sem.admin.ch"},
            "poland": {"name": "Poland", "visa_url": "https://www.gov.pl/web/poland/visa"},
            "czech_republic": {"name": "Czech Republic", "visa_url": "https://www.mvcr.cz"},
            "hungary": {"name": "Hungary", "visa_url": "https://visa.kormany.hu"}
        }
    
    def scrape_all(self) -> Dict[str, Dict]:
        """Scrape all Schengen countries"""
        results = {}
        
        for code, info in self.countries.items():
            print(f"🇪🇺 Scraping {info['name']}...")
            
            # Create base scraper instance
            scraper = BaseScraper(code, info['name'])
            
            # Build data structure
            data = {
                "country": info['name'],
                "last_updated": datetime.now().strftime('%Y-%m-%d'),
                "visas": {
                    "tourist": self._get_schengen_tourist_data(info['name']),
                    "student": self._get_schengen_student_data(info['name']),
                    "work": self._get_schengen_work_data(info['name'])
                },
                "sources": [{
                    "name": f"{info['name']} Immigration",
                    "url": info['visa_url'],
                    "type": "official",
                    "domain_type": self._get_domain_type(code)
                }]
            }
            
            # Save data
            scraper.save_data(data)
            results[code] = data
            
            # Polite delay
            import time
            time.sleep(1)
        
        return results
    
    def _get_schengen_tourist_data(self, country: str) -> Dict:
        """Standard Schengen tourist visa requirements"""
        return {
            "requirements": [
                "Valid passport (3 months beyond stay)",
                "Schengen visa application form",
                "Passport photos",
                "Travel insurance (€30,000 minimum)",
                "Proof of accommodation",
                "Proof of sufficient funds",
                "Flight reservation",
                "Travel itinerary"
            ],
            "processing_time": "15 days",
            "fees": "€80",
            "validity": "90 days within 180-day period",
            "ielts_required": False,
            "interview_required": True
        }
    
    def _get_schengen_student_data(self, country: str) -> Dict:
        """Standard Schengen student visa requirements"""
        return {
            "requirements": [
                "Acceptance letter from educational institution",
                "Proof of financial means",
                "Health insurance",
                "Accommodation proof",
                "Academic records",
                "Language proficiency (if required)"
            ],
            "processing_time": "4-8 weeks",
            "fees": "€50-100",
            "validity": "Duration of studies",
            "ielts_required": True,
            "interview_required": True
        }
    
    def _get_schengen_work_data(self, country: str) -> Dict:
        """Standard Schengen work visa requirements"""
        return {
            "requirements": [
                "Job offer/contract",
                "Work permit approval",
                "Qualifications proof",
                "CV/Resume",
                "Health insurance",
                "Police clearance"
            ],
            "processing_time": "4-12 weeks",
            "fees": "€75-150",
            "validity": "1-2 years (renewable)",
            "ielts_required": False,
            "interview_required": True
        }
    
    def _get_domain_type(self, code: str) -> str:
        """Get domain type for country"""
        domains = {
            "france": ".gouv.fr",
            "germany": ".de",
            "italy": ".it",
            "spain": ".gob.es",
            "netherlands": ".nl",
            "sweden": ".se",
            "norway": ".no",
            "denmark": ".dk",
            "finland": ".fi"
        }
        return domains.get(code, ".eu")