#!/usr/bin/env python3
"""
Main Visa Scraper Service
Coordinates scraping for all supported countries
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import all scrapers
from scrapers.us_scraper import USScraper
from scrapers.uk_scraper import UKScraper
from scrapers.canada_scraper import CanadaScraper
from scrapers.australia_scraper import AustraliaScraper
from scrapers.ireland_scraper import IrelandScraper
from scrapers.schengen_scraper import SchengenScraper
from scrapers.asia_scraper import AsiaScraper
from scrapers.middle_east_scraper import MiddleEastScraper

class VisaScraperService:
    """Main service to orchestrate all visa scraping"""
    
    def __init__(self):
        self.data_dir = "visa_data"
        self.log_file = "scraper_log.txt"
        
        # Create data directory
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Initialize all scrapers
        self.scrapers = {
            "us": USScraper(),
            "uk": UKScraper(),
            "canada": CanadaScraper(),
            "australia": AustraliaScraper(),
            "ireland": IrelandScraper(),
            "schengen": SchengenScraper(),
            "asia": AsiaScraper(),
            "middle_east": MiddleEastScraper()
        }
    
    def scrape_all_countries(self, parallel: bool = True) -> Dict:
        """Scrape all countries"""
        self._log("Starting full scrape of all countries")
        start_time = datetime.now()
        
        results = {}
        
        if parallel:
            # Parallel scraping
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {}
                
                # Submit individual country scrapers
                for code, scraper in self.scrapers.items():
                    if code not in ["schengen", "asia", "middle_east"]:
                        futures[executor.submit(self._scrape_single, code, scraper)] = code
                
                # Submit regional scrapers
                for region in ["schengen", "asia", "middle_east"]:
                    futures[executor.submit(self._scrape_region, region)] = region
                
                # Collect results
                for future in as_completed(futures):
                    code = futures[future]
                    try:
                        result = future.result()
                        if result:
                            results.update(result)
                            self._log(f"✅ Completed: {code}")
                    except Exception as e:
                        self._log(f"❌ Failed {code}: {e}")
        else:
            # Sequential scraping
            for code, scraper in self.scrapers.items():
                try:
                    if code in ["schengen", "asia", "middle_east"]:
                        result = self._scrape_region(code)
                    else:
                        result = self._scrape_single(code, scraper)
                    
                    if result:
                        results.update(result)
                        self._log(f"✅ Completed: {code}")
                except Exception as e:
                    self._log(f"❌ Failed {code}: {e}")
                
                time.sleep(2)  # Polite delay
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        summary = {
            "total_countries": len(results),
            "countries_scraped": list(results.keys()),
            "duration_seconds": duration,
            "timestamp": end_time.isoformat()
        }
        
        self._save_summary(summary)
        self._log(f"Scraping completed in {duration:.2f} seconds")
        
        return results
    
    def _scrape_single(self, code: str, scraper) -> Dict:
        """Scrape a single country"""
        try:
            data = scraper.scrape()
            file_path = scraper.save_data(data)
            return {code: {"file": file_path, "status": "success"}}
        except Exception as e:
            self._log(f"Error scraping {code}: {e}")
            return {}
    
    def _scrape_region(self, region: str) -> Dict:
        """Scrape a region of countries"""
        scraper = self.scrapers[region]
        try:
            return scraper.scrape_all()
        except Exception as e:
            self._log(f"Error scraping region {region}: {e}")
            return {}
    
    def scrape_single_country(self, country_code: str) -> Dict:
        """Scrape a specific country"""
        self._log(f"Scraping single country: {country_code}")
        
        if country_code in self.scrapers:
            scraper = self.scrapers[country_code]
            if country_code not in ["schengen", "asia", "middle_east"]:
                return self._scrape_single(country_code, scraper)
        
        # Check if it's in a region
        for region in ["schengen", "asia", "middle_east"]:
            if country_code in self.scrapers[region].countries:
                return {country_code: {"status": "in_region", "region": region}}
        
        return {"error": f"Unknown country: {country_code}"}
    
    def get_all_data(self) -> Dict:
        """Load all scraped data from files"""
        all_data = {}
        
        for filename in os.listdir(self.data_dir):
            if filename.endswith('.json'):
                country_code = filename.replace('.json', '')
                file_path = os.path.join(self.data_dir, filename)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        all_data[country_code] = json.load(f)
                except Exception as e:
                    print(f"Error loading {filename}: {e}")
        
        return all_data
    
    def get_country_data(self, country_code: str) -> Dict:
        """Get data for a specific country"""
        file_path = os.path.join(self.data_dir, f"{country_code}.json")
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return {}
    
    def _log(self, message: str):
        """Log message to file and console"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        
        print(log_message)
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + '\n')
    
    def _save_summary(self, summary: Dict):
        """Save scraping summary"""
        file_path = os.path.join(self.data_dir, "_summary.json")
        with open(file_path, 'w') as f:
            json.dump(summary, f, indent=2)
    
    def get_statistics(self) -> Dict:
        """Get scraping statistics"""
        stats = {
            "total_countries": 0,
            "last_scraped": {},
            "data_size": {},
            "visa_types": {}
        }
        
        for filename in os.listdir(self.data_dir):
            if filename.endswith('.json') and not filename.startswith('_'):
                country_code = filename.replace('.json', '')
                file_path = os.path.join(self.data_dir, filename)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    stats["total_countries"] += 1
                    stats["last_scraped"][country_code] = data.get("last_scraped", "Unknown")
                    stats["data_size"][country_code] = os.path.getsize(file_path)
                    
                    visa_types = list(data.get("visas", {}).keys())
                    stats["visa_types"][country_code] = visa_types
                    
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
        
        return stats

# CLI Interface
if __name__ == "__main__":
    import sys
    
    service = VisaScraperService()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "scrape-all":
            print("🌍 Starting full scrape of all countries...")
            results = service.scrape_all_countries()
            print(f"\n✅ Scraped {len(results)} countries")
            
        elif command == "scrape-country" and len(sys.argv) > 2:
            country = sys.argv[2]
            print(f"🇺🇳 Scraping {country}...")
            result = service.scrape_single_country(country)
            print(result)
            
        elif command == "stats":
            stats = service.get_statistics()
            print(json.dumps(stats, indent=2))
            
        elif command == "list":
            data = service.get_all_data()
            print(f"📊 Available countries: {list(data.keys())}")
            
        else:
            print("Usage:")
            print("  python scraper_service.py scrape-all")
            print("  python scraper_service.py scrape-country <code>")
            print("  python scraper_service.py stats")
            print("  python scraper_service.py list")
    else:
        print("Please specify a command")