#!/usr/bin/env python3
"""Manual script to run scrapers"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper_service import VisaScraperService

def main():
    service = VisaScraperService()
    
    print("=" * 60)
    print("🌍 VISA SCRAPER SERVICE")
    print("=" * 60)
    print("\nOptions:")
    print("1. Scrape all countries")
    print("2. Scrape single country")
    print("3. View statistics")
    print("4. List available countries")
    print("5. Exit")
    
    choice = input("\nSelect option (1-5): ").strip()
    
    if choice == "1":
        print("\n🚀 Starting full scrape...")
        results = service.scrape_all_countries(parallel=True)
        print(f"\n✅ Completed! Scraped {len(results)} countries")
        
    elif choice == "2":
        country = input("Enter country code (e.g., us, uk, france): ").strip().lower()
        result = service.scrape_single_country(country)
        print(f"\nResult: {result}")
        
    elif choice == "3":
        stats = service.get_statistics()
        print(f"\n📊 Statistics:")
        print(f"Total countries: {stats['total_countries']}")
        print("\nLast scraped:")
        for country, date in stats['last_scraped'].items():
            print(f"  {country}: {date}")
            
    elif choice == "4":
        data = service.get_all_data()
        print(f"\n📋 Available countries ({len(data)}):")
        for code, info in data.items():
            print(f"  {code}: {info.get('country', code)}")
            
    elif choice == "5":
        print("Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()