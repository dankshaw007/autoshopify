import telebot
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import requests
# Removed: import tempfile
# Removed: import shutil
# Removed: import os (no longer needed for path.exists related to user_data_dir)

class ShopifyChecker:
    def __init__(self):
        self.driver = None
        self.shopify_store_url = None
        self.lowest_product_info = None # Stores product title, price, id etc.

    def initialize_driver(self):
        # Try to quit existing driver if it's running
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                print(f"Error quitting old driver: {e}")
            finally:
                # This 'finally' block is now empty as user_data_dir management is removed
                pass

        options = Options()
        options.add_argument("--headless")  # Run in headless mode (no GUI)
        options.add_argument("--no-sandbox") # Required for running as root in some environments (like Codespaces)
        options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems
        options.add_argument("--disable-gpu") # Recommended for headless
        options.add_argument("--window-size=1920,1080") # Set a window size for consistent rendering
        options.add_argument("--incognito") # Optional: run in incognito mode
        # Add user-agent to mimic a real browser
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Removed: code to create and pass --user-data-dir argument.
        # ChromeDriver will now manage its own temporary profile.
        print("--- DEBUG: Initializing WebDriver - No --user-data-dir used. ---") # <<< VERIFICATION PRINT

        try:
            # Assumes chromedriver is in PATH (e.g., /usr/local/bin/chromedriver as set up in devcontainer.json)
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30) # Set a page load timeout
            print("WebDriver initialized successfully.")
        except Exception as e:
            print(f"Error initializing WebDriver: {e}")
            self.driver = None
            # Removed: cleanup of self.user_data_dir on init failure
            raise # Re-raise to propagate the error up

    def set_store_url(self, url):
        self.shopify_store_url = url

    def get_bin_details(self, bin_number):
        if not bin_number or not bin_number.isdigit() or len(bin_number) < 6:
            return {"status": "error", "message": "Invalid BIN format."}

        api_url = f"https://api.binlist.net/v1/{bin_number}"
        try:
            response = requests.get(api_url, timeout=5)
            response.raise_for_status()
            data = response.json()

            scheme_type_brand = f"{data.get('scheme', 'N/A').upper()} {data.get('type', 'N/A').capitalize()} {data.get('brand', 'N/A').capitalize()}"
            bank = data.get('bank', {}).get('name', 'N/A')
            country = data.get('country', {}).get('name', 'N/A')
            country_emoji = data.get('country', {}).get('emoji', '')

            return {
                "status": "success",
                "data": {
                    "scheme_type_brand": scheme_type_brand,
                    "bank": bank,
                    "country": country,
                    "country_emoji": country_emoji
                }
            }
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": f"BIN lookup failed: {e}"}
        except json.JSONDecodeError:
            return {"status": "error", "message": "BIN lookup returned invalid JSON."}
        except Exception as e:
            return {"status": "error", "message": f"An unexpected error occurred during BIN lookup: {e}"}


    def check_card_with_selenium(self, card_string, customer_details):
        start_time = time.time()
        if not self.shopify_store_url:
            return {"status": "error", "message": "Shopify store URL not set.", "time_taken": 0}
        if not self.lowest_product_info:
            return {"status": "error", "message": "No product information available.", "time_taken": 0}

        card_parts = card_string.split('|')
        if len(card_parts) != 4:
            return {"status": "error", "message": "Invalid card format. Use CC|MM|YY|CVV", "time_taken": 0}

        cc, mm, yy, cvv = card_parts
        if len(yy) == 2:
            yy = f"20{yy}"

        try:
            # Ensure a driver is initialized, or initialize a new one if none exists
            if not self.driver:
                self.initialize_driver()
            if not self.driver: # Check again in case initialize_driver failed
                return {"status": "automation_error", "message": "WebDriver could not be initialized.", "time_taken": 0}

            product_handle = self.lowest_product_info['handle']
            variant_id = self.lowest_product_info['variant_id']
            checkout_url = f"{self.shopify_store_url}/cart/{variant_id}:1?checkout[shipping_address][first_name]={customer_details['first_name']}&checkout[shipping_address][last_name]={customer_details['last_name']}&checkout[shipping_address][address1]={customer_details['address1']}&checkout[shipping_address][city]={customer_details['city']}&checkout[shipping_address][province]={customer_details['province']}&checkout[shipping_address][zip]={customer_details['zip']}&checkout[shipping_address][country]={customer_details['country_code']}&checkout[email]={customer_details['email']}&checkout[shipping_address][phone]={customer_details['phone']}"

            print(f"Navigating to checkout URL: {checkout_url}")
            self.driver.get(checkout_url)

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, 'checkout_email'))
            )
            print("Email field found.")

            # Fill payment info (assuming Stripe or similar generic Shopify checkout form)
            WebDriverWait(self.driver, 10).until(
                EC.frame_to_be_available_and_switch_to_it((By.XPATH, '//iframe[contains(@id, "card-fields-number")]'))
            )
            card_number_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, 'number'))
            )
            card_number_input.send_keys(cc)
            self.driver.switch_to.default_content()

            WebDriverWait(self.driver, 10).until(
                EC.frame_to_be_available_and_switch_to_it((By.XPATH, '//iframe[contains(@id, "card-fields-expiry")]'))
            )
            card_expiry_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, 'expiry'))
            )
            card_expiry_input.send_keys(f"{mm}{yy}")
            self.driver.switch_to.default_content()

            WebDriverWait(self.driver, 10).until(
                EC.frame_to_be_available_and_switch_to_it((By.XPATH, '//iframe[contains(@id, "card-fields-verification_value")]'))
            )
            card_cvv_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, 'verification_value'))
            )
            card_cvv_input.send_keys(cvv)
            self.driver.switch_to.default_content()

            try:
                pay_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, 'checkout_reduce_wrapping_payment_due_button'))
                )
                pay_button.click()
                print("Clicked Pay Now button.")
            except Exception as e:
                print(f"Could not find or click typical pay button, trying alternative: {e}")
                try:
                    pay_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.NAME, 'button'))
                    )
                    pay_button.click()
                    print("Clicked alternative Pay Now button.")
                except Exception as e:
                    print(f"Failed to find any pay button: {e}")
                    pass

            time.sleep(5) # Give it a moment to process

            current_url = self.driver.current_url
            page_source = self.driver.page_source

            outcome = "unknown_outcome"
            message = "Could not determine outcome."

            if "thank_you" in current_url or "order_status" in current_url:
                outcome = "order_placed"
                message = "Order placed successfully."
            elif "card was declined" in page_source:
                outcome = "card_declined"
                message = "Card declined (Generic Decline)"
            elif "Incorrect CVV" in page_source:
                outcome = "card_declined"
                message = "Card declined (Incorrect CVV)"
            elif "Insufficient Funds" in page_source:
                outcome = "card_declined"
                message = "Card declined (Insufficient Funds)"
            elif "Invalid card number" in page_source:
                outcome = "card_declined"
                message = "Card declined (Invalid Card Number)"
            elif "card has expired" in page_source:
                outcome = "card_declined"
                message = "Card declined (Card Expired)"
            elif "address verification system" in page_source or "AVS mismatch" in page_source:
                outcome = "card_declined"
                message = "Card declined (AVS Mismatch)"
            elif "authentication required" in page_source or "3d_secure" in current_url:
                outcome = "3ds_required"
                message = "3DS authentication required."

            print(f"Selenium outcome: {outcome}, message: {message}")
            return {"status": outcome, "message": message, "time_taken": time.time() - start_time}

        except Exception as e:
            print(f"An error occurred during Selenium checkout: {e}")
            return {"status": "automation_error", "message": f"Automation error: {e}", "time_taken": time.time() - start_time}
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    print(f"Error quitting driver in finally block: {e}")
            # No user_data_dir cleanup here either
