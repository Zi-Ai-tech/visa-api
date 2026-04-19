import requests
import time
import json

BASE_URL = "http://localhost:5000"

def test_single_query(query):
    """Test a single query"""
    print(f"\n{'='*50}")
    print(f"Testing: {query}")
    print('='*50)
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/ask",
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Country: {data.get('country')}")
            print(f"Confidence: {data.get('confidence', {}).get('level')} ({data.get('confidence', {}).get('score', 0)*100:.0f}%)")
            print(f"Sources: {len(data.get('sources', []))} official sources")
            print(f"\nAnswer Preview:\n{data.get('direct_answer', '')[:300]}...")
        else:
            print(f"Error: {response.json()}")
            
    except Exception as e:
        print(f"Request failed: {e}")

def test_rate_limiting():
    """Test rate limiting with multiple rapid requests"""
    print(f"\n{'='*50}")
    print("Testing Rate Limiting (12 rapid requests)")
    print('='*50)
    
    for i in range(1, 13):
        print(f"\nRequest {i}:")
        try:
            response = requests.post(
                f"{BASE_URL}/api/ask",
                json={"query": "US visa"},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                print(f"  ✓ Success")
            elif response.status_code == 429:
                print(f"  ✗ Rate limited! (as expected)")
                error_data = response.json()
                print(f"  Message: {error_data.get('message')}")
            else:
                print(f"  Status: {response.status_code}")
                
        except Exception as e:
            print(f"  Error: {e}")
        
        time.sleep(0.1)  # Small delay to not overwhelm

def test_input_validation():
    """Test security features"""
    print(f"\n{'='*50}")
    print("Testing Input Validation")
    print('='*50)
    
    malicious_queries = [
        "<script>alert('xss')</script>",
        "'; DROP TABLE users; --",
        "../etc/passwd",
        "A" * 1000,  # Too long
        "SELECT * FROM users",
    ]
    
    for query in malicious_queries:
        print(f"\nTesting: {query[:50]}...")
        response = requests.post(
            f"{BASE_URL}/api/ask",
            json={"query": query}
        )
        
        if response.status_code == 400:
            data = response.json()
            print(f"  ✓ Blocked: {data.get('error')}")
        else:
            print(f"  ⚠ Allowed (status: {response.status_code})")

def test_countries_endpoint():
    """Test the countries list endpoint"""
    print(f"\n{'='*50}")
    print("Testing Countries Endpoint")
    print('='*50)
    
    response = requests.get(f"{BASE_URL}/api/countries")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Total Countries: {data.get('total')}")
        for country in data.get('countries', []):
            print(f"  • {country['name']} - Confidence: {country['confidence']}")
    else:
        print(f"Error: {response.status_code}")

if __name__ == "__main__":
    print("Starting API Tests...")
    print(f"Target: {BASE_URL}")
    
    # Check if server is running
    try:
        health = requests.get(f"{BASE_URL}/api/health", timeout=2)
        if health.status_code == 200:
            print(f"✓ Server is running: {health.json().get('message')}")
        else:
            print("✗ Server not responding properly")
            exit(1)
    except:
        print("✗ Cannot connect to server. Is it running?")
        print("  Run: python app.py")
        exit(1)
    
    # Run tests
    test_single_query("US visa requirements")
    test_single_query("UK student visa for Pakistani")
    test_single_query("Canada work permit")
    test_countries_endpoint()
    test_input_validation()
    test_rate_limiting()
    
    print(f"\n{'='*50}")
    print("All tests completed!")
    print('='*50)