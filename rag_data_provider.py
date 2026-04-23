import os
import json

DATA_DIR = os.path.join(os.path.dirname(__file__), "visa_data")


def load_country_data(country: str):
    try:
        file_path = os.path.join(DATA_DIR, f"{country}.json")
        if not os.path.exists(file_path):
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


def get_visa_info(country: str, visa_type: str):
    data = load_country_data(country)
    if not data:
        return None

    visas = data.get("visas", {})
    return visas.get(visa_type)