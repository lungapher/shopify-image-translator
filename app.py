import os
import requests
import base64
import re
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, jsonify, send_file, request
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE_DOMAIN")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

SHOPIFY_HEADERS = {
    "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
    "Content-Type": "application/json"
}

VISION_URL = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_API_KEY}"
TRANSLATE_URL = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"

app = Flask(__name__)

@app.route('/')
def home():
    return '✅ Shopify Translator is running. Use /start or /test-ocr?img=URL'

def contains_chinese(text):
    """Detect Chinese characters using Unicode ranges"""
    return any('\u4e00' <= char <= '\u9fff' for char in text)

def detect_and_translate(image_url):
    try:
        print(f"🔍 Processing image: {image_url}")
        
        vision_payload = {
            "requests": [{
                "image": {
                    "source": {
                        "imageUri": image_url
                    }
                },
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        vision_resp = requests.post(VISION_URL, json=vision_payload).json()
        annotations = vision_resp.get("responses", [{}])[0].get("textAnnotations", [])
        if not annotations:
            print("⚠️ No text found in image.")
            return None

        img_bytes = requests.get(image_url).content
        base_img = Image.open(BytesIO(img_bytes)).convert("RGB")
        draw = ImageDraw.Draw(base_img)
        font = ImageFont.load_default()

        found_chinese = False

        for text_data in annotations[1:]:
            orig_text = text_data["description"]
            if not contains_chinese(orig_text):
                continue

            found_chinese = True
            bbox = text_data["boundingPoly"]["vertices"]

            translate_resp = requests.post(TRANSLATE_URL, json={
                "q": orig_text,
                "target": "en",
                "format": "text"
            }).json()

            translated = translate_resp.get("data", {}).get("translations", [{}])[0].get("translatedText")
            if not translated:
                continue

            print(f"✅ '{orig_text}' ➜ '{translated}'")

            x = bbox[0].get("x", 0)
            y = bbox[0].get("y", 0)
            draw.rectangle([x, y, x + 100, y + 20], fill="white")
            draw.text((x, y), translated, fill="black", font=font)

        if not found_chinese:
            print("🚫 No Chinese text detected. Skipping image.")
            return None

        output = BytesIO()
        base_img.save(output, format="JPEG")
        output.seek(0)
        return output
    except Exception as e:
        print(f"❌ Error in detect_and_translate: {e}")
        return None

def upload_image_to_shopify(product_id, image_data):
    encoded = base64.b64encode(image_data.read()).decode()
    payload = {"image": {"attachment": encoded}}

    url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products/{product_id}/images.json"
    return requests.post(url, headers=SHOPIFY_HEADERS, json=payload).json()

@app.route('/start', methods=['GET'])
def process_products():
    url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products.json?limit=10"
    try:
        response = requests.get(url, headers=SHOPIFY_HEADERS)
        products = response.json().get("products", [])
    except Exception as e:
        return jsonify({"error": "Failed to fetch products", "details": str(e)}), 500

    updated = []

    for product in products:
        title = product.get("title")
        print(f"\n📦 Processing Product: {title}")

        for image in product.get("images", []):
            image_url = image["src"]
            processed_image = detect_and_translate(image_url)

            if processed_image:
                del_url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products/{product['id']}/images/{image['id']}.json"
                requests.delete(del_url, headers=SHOPIFY_HEADERS)
                upload_result = upload_image_to_shopify(product["id"], processed_image)
                updated.append({
                    "product_title": title,
                    "image_url": upload_result.get("image", {}).get("src")
                })

    return jsonify({"status": "done", "updated_images": len(updated), "details": updated})

@app.route('/test-ocr')
def test_ocr():
    img = request.args.get("img")
    if not img:
        return "❌ Provide ?img=image_url", 400
    processed_image = detect_and_translate(img)
    if processed_image:
        return send_file(processed_image, mimetype='image/jpeg')
    return "❌ Failed to process image", 500
