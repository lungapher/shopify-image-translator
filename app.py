import os
import requests
import base64
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
app.config["DEBUG"] = True  # Turn off in production!

@app.route('/')
def home():
    return '✅ Shopify Translator is running. Use /start or /test-ocr?img=URL'

def detect_and_translate(image_url):
    try:
        print(f"🔍 Processing image: {image_url}")
        img_bytes = requests.get(image_url).content
        b64 = base64.b64encode(img_bytes).decode("utf-8")

        vision_payload = {
            "requests": [{
                "image": {"content": b64},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        vision_resp = requests.post(VISION_URL, json=vision_payload).json()
        print("📦 Vision API response:", vision_resp)

        if "responses" not in vision_resp or not vision_resp["responses"]:
            print("❌ No response from Vision API")
            return None

        annotations = vision_resp["responses"][0].get("textAnnotations", [])
        if not annotations:
            print("⚠️ No text detected in image")
            return None

        base_img = Image.open(BytesIO(img_bytes)).convert("RGB")
        draw = ImageDraw.Draw(base_img)
        font = ImageFont.truetype("arial.ttf", 12) if os.path.exists("arial.ttf") else ImageFont.load_default()

        for text_data in annotations[1:]:
            orig_text = text_data["description"]
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
        print(f"⬆️ Uploading image to {url}")
        res = requests.post(url, headers=SHOPIFY_HEADERS, json=payload)
        print("📦 Shopify response:", res.text)
        return res.json()
    except Exception as e:
        print(f"❌ Error uploading image: {e}")
        return {}

@app.route('/start', methods=['GET'])
def process_products():
    print("🚀 Starting product processing...")
    url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products.json?limit=10"

    try:
        response = requests.get(url, headers=SHOPIFY_HEADERS)
        response.raise_for_status()
        products = response.json().get("products", [])
        print(f"✅ Fetched {len(products)} products")
    except Exception as e:
        print(f"❌ Failed to fetch products: {e}")
        return jsonify({"error": "Failed to fetch products", "details": str(e)}), 500

    results = []

    for product in products:
        print(f"🛒 Processing product: {product.get('title')} (ID: {product['id']})")
        for image in product.get("images", []):
            print(f"🖼️ Processing image: {image['src']}")
            processed_image = detect_and_translate(image["src"])
            if processed_image:
                try:
                    del_url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products/{product['id']}/images/{image['id']}.json"
                    requests.delete(del_url, headers=SHOPIFY_HEADERS)
                    upload_result = upload_image_to_shopify(product["id"], processed_image)
                    results.append(upload_result)
                    print("✅ Image updated successfully")
                except Exception as e:
                    print(f"❌ Failed to update image: {e}")
            else:
                print("⚠️ Skipped image: processing failed")

    return jsonify({"status": "done", "updated_images": len(results)})

@app.route('/test-ocr')
def test_ocr():
    img = request.args.get("img")
    if not img:
        return "❌ Provide ?img=image_url", 400
    processed_image = detect_and_translate(img)
    if processed_image:
        return send_file(processed_image, mimetype='image/jpeg')
    return "❌ Failed to process image", 500
