#!/usr/bin/env python3
"""
Auto-update script for visa data
Run daily via cron: 0 2 * * * cd /path/to/project && python scripts/update_data.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.scraper import VisaScraper
from datetime import datetime

# Configuration for countries to update
COUNTRIES_CONFIG = {
    "ireland": {
        "urls": [
            {
                "name": "Irish Immigration Service",
                "url": "https://www.irishimmigration.ie",
                "type": "general"
            }
        ]
    },
    "uk": {
        "urls": [
            {
                "name": "UK Visas and Immigration",
                "url": "https://www.gov.uk/browse/visas-immigration",
                "type": "general"
            }
        ]
    }
    # Add more countries as needed
}

def main():
    print(f"Starting visa data update - {datetime.now()}")
    scraper = VisaScraper()
    
    for country_code, config in COUNTRIES_CONFIG.items():
        print(f"Updating {country_code}...")
        try:
            data = scraper.scrape_country(country_code, config["urls"])
            scraper.save_country_data(country_code, data)
            print(f"✓ Updated {country_code}")
        except Exception as e:
            print(f"✗ Failed to update {country_code}: {e}")
    
    print(f"Update completed - {datetime.now()}")

if __name__ == "__main__":
    main()