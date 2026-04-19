#!/usr/bin/env python3
"""Automated scheduler for visa scraping"""

import schedule
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper_service import VisaScraperService

service = VisaScraperService()

def job_scrape_all():
    """Daily scraping job"""
    print("\n" + "=" * 60)
    print("🔄 SCHEDULED SCRAPE STARTING...")
    print("=" * 60)
    
    try:
        results = service.scrape_all_countries(parallel=True)
        print(f"✅ Scheduled scrape completed: {len(results)} countries")
    except Exception as e:
        print(f"❌ Scheduled scrape failed: {e}")

def job_scrape_high_priority():
    """Scrape high-priority countries more frequently"""
    priority_countries = ["us", "uk", "canada", "australia", "ireland"]
    
    print(f"\n🔄 Scraping priority countries: {priority_countries}")
    
    for country in priority_countries:
        try:
            service.scrape_single_country(country)
            print(f"  ✅ {country}")
        except Exception as e:
            print(f"  ❌ {country}: {e}")
        time.sleep(2)

# Schedule jobs
schedule.every().day.at("02:00").do(job_scrape_all)  # Daily at 2 AM
schedule.every().day.at("08:00").do(job_scrape_high_priority)
schedule.every().day.at("14:00").do(job_scrape_high_priority)
schedule.every().day.at("20:00").do(job_scrape_high_priority)

print("🕐 Scheduler started. Waiting for jobs...")
print("Press Ctrl+C to stop")

while True:
    schedule.run_pending()
    time.sleep(60)  # Check every minute