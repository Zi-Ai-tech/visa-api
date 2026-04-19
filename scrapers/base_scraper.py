import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import time
import random

class BaseScraper:
    """Base scraper class with common functionality"""
    
    def __init__(self, country_code: str, country_name: str):
        self.country_code = country_code
        self.country_name = country_name
        self.data_dir = "visa_data"
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        # Create data directory if not exists
        os.makedirs(self.data_dir, exist_ok=True)
    
    def _get_headers(self) -> Dict:
        """Get random headers to avoid blocking"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def _make_request(self, url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
        """Make HTTP request with retries"""
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url, 
                    headers=self._get_headers(),
                    timeout=15
                )
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except Exception as e:
                print(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
        return None
    
    def _extract_text(self, soup: BeautifulSoup, selectors: List[str]) -> str:
        """Extract text using multiple possible selectors"""
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)
        return ""
    
    def _extract_list(self, soup: BeautifulSoup, selectors: List[str]) -> List[str]:
        """Extract list items using multiple possible selectors"""
        items = []
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                items.extend([el.get_text(strip=True) for el in elements])
        return list(set(items))  # Remove duplicates
    
    def scrape(self) -> Dict:
        """Main scrape method - to be implemented by child classes"""
        raise NotImplementedError("Child classes must implement scrape()")
    
    def save_data(self, data: Dict) -> str:
        """Save scraped data to JSON file"""
        file_path = os.path.join(self.data_dir, f"{self.country_code}.json")
        
        # Add metadata
        data.update({
            "country_code": self.country_code,
            "last_scraped": datetime.now().isoformat(),
            "scraper_version": "2.0"
        })
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved data for {self.country_name} to {file_path}")
        return file_path
    
    def load_existing_data(self) -> Optional[Dict]:
        """Load existing data if available"""
        file_path = os.path.join(self.data_dir, f"{self.country_code}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None