import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get('TRAVELBUDDY_API_KEY')
print(f"API Key configured: {bool(api_key)}")
print(f"API Key length: {len(api_key) if api_key else 0}")
print(f"API Key preview: {api_key[:15]}..." if api_key else "None")

if api_key:
    headers = {
        'X-RapidAPI-Key': api_key,
        'X-RapidAPI-Host': 'visa-requirement.p.rapidapi.com',
        'Content-Type': 'application/json'
    }
    
    params = {"passport": "PK", "destination": "US"}
    url = "https://visa-requirement.p.rapidapi.com/VisaRequirements"
    
    print(f"\n🌐 Calling: {url}")
    print(f"📋 Params: {params}")
    
    try:
        response = requests.post(url, headers=headers, json=params, timeout=15)
        print(f"\n📥 Status: {response.status_code}")
        print(f"📄 Response: {response.text}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
else:
    print("\n❌ No API key found in .env file")
    print("Please add TRAVELBUDDY_API_KEY to your .env file")