import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get('TRAVELBUDDY_API_KEY')
headers = {
    'X-RapidAPI-Key': api_key,
    'X-RapidAPI-Host': 'visa-requirement.p.rapidapi.com'
}

# Try GET with query parameters
base_url = "https://visa-requirement.p.rapidapi.com"

# Test GET endpoints
get_endpoints = [
    "/visa/PK/US",
    "/check/PK/US",
    "/requirements/PK/US",
    "/api/visa/PK/US",
    "/v2/visa/PK/US"
]

print("Testing GET endpoints:")
for endpoint in get_endpoints:
    url = base_url + endpoint
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"GET {endpoint:35} -> Status: {response.status_code}")
        if response.status_code == 200:
            print(f"  ✅ SUCCESS! Response: {response.text[:200]}")
            break
    except Exception as e:
        print(f"GET {endpoint:35} -> Error: {e}")