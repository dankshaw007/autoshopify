import re
import requests
from bs4 import BeautifulSoup # Not used in current bot, but keep if needed elsewhere
import random
import string
import os
import json

def generate_random_customer_details():
    # Generate random names
    first_names = ["John", "Jane", "Alice", "Bob", "Charlie", "David", "Eve", "Frank", "Grace", "Heidi", "Ashley", "Bennett", "Kim", "Caldwell"] # Added for example consistency
    last_names = ["Doe", "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Caldwell", "Kim", "Bennett"] # Added for example consistency
    first_name = random.choice(first_names)
    last_name = random.choice(last_names)

    # Generate random email
    email_domains = ["example.com", "test.com", "mail.com", "fake.org"]
    email = f"{first_name.lower()}{last_name.lower()}{random.randint(10, 99)}@{random.choice(email_domains)}"

    # Generate random address (simple placeholder)
    address1 = f"{random.randint(100, 9999)} {random.choice(string.ascii_uppercase)}{random.choice(string.ascii_lowercase)} Street Apt {random.randint(1, 200)}"
    city = random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose", "North Cynthiamouth"]) # Added for example consistency
    provinces = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]
    province = random.choice(provinces)
    zip_code = f"{random.randint(10000, 99999)}"
    country_code = "US" # Assuming US for simplicity
    phone = f"{random.randint(100, 999)}.{random.randint(100, 999)}.{random.randint(1000, 9999)}"

    return {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "address1": address1,
        "city": city,
        "province": province,
        "zip": zip_code,
        "country_code": country_code,
        "phone": phone
    }

def is_shopify_store(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        if "shopify" in response.text.lower() or "cdn.shopify.com" in response.text:
            return True
        if 'x-shopify-shop-api-call-limit' in response.headers:
            return True
        return False
    except requests.exceptions.RequestException as e:
        print(f"Error checking Shopify status for {url}: {e}")
        return False

def get_shopify_lowest_price(url):
    products_json_url = f"{url.rstrip('/')}/products.json"
    try:
        response = requests.get(products_json_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        products = data.get('products', [])
        if not products:
            return {"status": "error", "message": "No products found."}

        lowest_price = float('inf')
        lowest_product_info = None

        for product in products:
            for variant in product.get('variants', []):
                try:
                    price = float(variant.get('price'))
                    if price < lowest_price:
                        lowest_price = price
                        lowest_product_info = {
                            "title": product.get('title'),
                            "handle": product.get('handle'),
                            "price": price,
                            "currency": variant.get('price_currency', 'USD'),
                            "variant_id": variant.get('id')
                        }
                except (ValueError, TypeError):
                    continue

        if lowest_product_info:
            return {"status": "success", "data": lowest_product_info}
        else:
            return {"status": "error", "message": "Could not find valid product prices."}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Failed to fetch product data: {e}"}
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON response from products.json."}
    except Exception as e:
        return {"status": "error", "message": f"An unexpected error occurred: {e}"}

def detect_captcha(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        if "hcaptcha.com/1/api.js" in response.text or 'data-sitekey' in response.text and 'hcaptcha' in response.text:
            return True
        return False
    except requests.exceptions.RequestException as e:
        print(f"Error detecting captcha for {url}: {e}")
        return False

STORED_URLS_FILE = "stored_urls.json"

def load_stored_urls():
    if os.path.exists(STORED_URLS_FILE):
        with open(STORED_URLS_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_stored_urls(urls_dict):
    with open(STORED_URLS_FILE, 'w') as f:
        json.dump(urls_dict, f, indent=4)

def escape_markdown_v2(text):
    """Helper function to escape special characters for Telegram MarkdownV2."""
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)
