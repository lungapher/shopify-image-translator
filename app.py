from flask import Flask, jsonify, request, send_file
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import base64
import os
import requests
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Load environment variables
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE_DOMAIN")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Headers
SHOPIFY_HEADERS = {
    "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
    "Content-Type": "application/json"
}

VISION_URL = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_API_KEY}"
TRANSLATE_URL = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"

@app.route('/')
def home():
    return '✅ Shopify Translator is running. Use /start or /test-ocr?img=URL'

def detect_and_translate(image_url):
    try:
        print(f"🔍 Fetching image: {image_url}")
        img_bytes = requests.get(image_url).content
        b64 = base64.b64encode(img_bytes).decode("utf-8")

        # Vision API call
        vision_payload = {
            "requests": [{
                "image": {"content": b64},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }
        vision_resp = requests.post(VISION_URL, json=vision_payload).json()
        annotations = vision_resp.get("responses", [{}])[0].get("textAnnotations", [])

        if not annotations:
            print("⚠️ No text found.")
            return None

        # Prepare image for drawing
        base_img = Image.open(BytesIO(img_bytes)).convert("RGB")
        draw = ImageDraw.Draw(base_img)
        font = ImageFont.truetype("arial.ttf", 12) if os.path.exists("arial.ttf") else ImageFont.load_default()

        for text_data in annotations[1:]:
            orig_text = text_data["description"]
            bbox = text_data["boundingPoly"]["vertices"]

            # Translate text
            trans_resp = requests.post(TRANSLATE_URL, json={
                "q": orig_text, "target": "en", "format": "text"
            }).json()

            translated = trans_resp.get("data", {}).get("translations", [{}])[0].get("translatedText")
            if not translated:
                continue

            print(f"✅ {orig_text} ➜ {translated}")
            x = bbox[0].get("x", 0)
            y = bbox[0].get("y", 0)

            # Draw white background
            text_width = draw.textlength(translated, font=font)
            draw.rectangle([x, y, x + text_width + 10, y + 20], fill="white")
            draw.text((x, y), translated, fill="black", font=font)

        output = BytesIO()
        base_img.save(output, format="JPEG")
        output.seek(0)
        return output

    except Exception as e:
        print(f"❌ Error in detect_and_translate: {e}")
        return None

def upload_image_to_shopify(product_id, image_data):
    try:
        encoded = base64.b64encode(image_data.read()).decode()
        payload = {"image": {"attachment": encoded}}
        url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products/{product_id}/images.json"
        resp = requests.post(url, headers=SHOPIFY_HEADERS, json=payload)
        print(f"📤 Uploaded to Shopify (status {resp.status_code})")
        return resp.json()
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return None

@app.route('/start', methods=['GET'])
def process_products():
    url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products.json?limit=10"
    try:
        response = requests.get(url, headers=SHOPIFY_HEADERS)
        response.raise_for_status()
        products = response.json().get("products", [])
        if not products:
            print("⚠️ No products found")
            return jsonify({"status": "no products"}), 200
    except Exception as e:
        return jsonify({"error": "Failed to fetch products", "details": str(e)}), 500

    updated_images = 0

    for product in products:
        product_id = product.get("id")
        if not product_id:
            continue

        print(f"\n📦 Processing product: {product.get('title')} ({product_id})")

        for image in product.get("images", []):
            img_src = image.get("src")
            img_id = image.get("id")
            if not img_src or not img_id:
                print("⚠️ Skipping invalid image")
                continue

            print(f"🖼️ Translating image {img_id}")
            processed = detect_and_translate(img_src)

            if processed:
                try:
                    # Delete old
                    del_url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products/{product_id}/images/{img_id}.json"
                    del_resp = requests.delete(del_url, headers=SHOPIFY_HEADERS)
                    print(f"🗑️ Deleted old image {img_id} - status {del_resp.status_code}")

                    # Upload new
                    upload_image_to_shopify(product_id, processed)
                    updated_images += 1
                except Exception as e:
                    print(f"❌ Error updating product {product_id}: {e}")
            else:
                print("❌ Image translation failed")

    return jsonify({"status": "done", "updated_images": updated_images})

@app.route('/test-ocr')
def test_ocr():
    img = request.args.get("img")
    if not img:
        return "❌ Provide ?img=image_url", 400
    processed = detect_and_translate(img)
    return send_file(processed, mimetype="image/jpeg") if processed else ("❌ Failed to process image", 500)
