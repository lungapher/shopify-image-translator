import os
import requests
import base64
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, jsonify, request
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
    return '✅ Shopify Translator is running. Visit /start or /test-salibay to test a Chinese image.'

def detect_and_translate(image_url):
    try:
        print(f"📥 Fetching image: {image_url}")
        img_bytes = requests.get(image_url).content
        b64 = base64.b64encode(img_bytes).decode("utf-8")

        vision_payload = {
            "requests": [{
                "image": {"content": b64},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        vision_resp = requests.post(VISION_URL, json=vision_payload).json()
        print("🔍 Vision API response:", vision_resp)

        if "responses" not in vision_resp or not vision_resp["responses"]:
            print("❌ Vision API failed or returned no responses.")
            return None

        annotations = vision_resp["responses"][0].get("textAnnotations", [])
        if not annotations:
            print("⚠️ No text found in image.")
            return None

        base_img = Image.open(BytesIO(img_bytes)).convert("RGB")
        draw = ImageDraw.Draw(base_img)
        font = ImageFont.load_default()

        for text_data in annotations[1:]:  # skip the full block
            orig_text = text_data["description"]
            bbox = text_data["boundingPoly"]["vertices"]

            translate_resp = requests.post(TRANSLATE_URL, json={
                "q": orig_text,
                "target": "en",
                "format": "text"
            }).json()

            print(f"🔁 Translating: {orig_text}")
            translated = translate_resp.get("data", {}).get("translations", [{}])[0].get("translatedText")

            if not translated:
                print("⚠️ Translation failed for:", orig_text)
                continue

            x = bbox[0].get("x", 0)
            y = bbox[0].get("y", 0)

            draw.rectangle([x, y, x + 100, y + 20], fill="white")
            draw.text((x, y), translated, fill="black", font=font)

        output = BytesIO()
        base_img.save(output, format="JPEG")
        output.seek(0)
        print("✅ Image processed successfully.")
        return output
    except Exception as e:
        print(f"[ERROR] detect_and_translate failed: {e}")
        return None

@app.route('/start', methods=['GET'])
def process_products():
    url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products.json?limit=10"
    try:
        response = requests.get(url, headers=SHOPIFY_HEADERS)
        products = response.json().get("products", [])
    except Exception as e:
        return jsonify({"error": "Failed to fetch products", "details": str(e)}), 500

    results = []

    for product in products:
        print(f"🔄 Checking product: {product['title']}")
        for image in product.get("images", []):
            print(f"📷 Processing image ID {image['id']}")
            processed_image = detect_and_translate(image["src"])
            if processed_image:
                # Delete original image
                del_url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products/{product['id']}/images/{image['id']}.json"
                del_res = requests.delete(del_url, headers=SHOPIFY_HEADERS)
                print(f"🗑️ Deleted old image: {del_res.status_code}")

                # Upload translated image
                upload_result = upload_image_to_shopify(product["id"], processed_image)
                results.append(upload_result)
            else:
                print("⚠️ Image skipped (no text or error).")

    return jsonify({ "status": "done", "updated_images": len(results) })

@app.route('/preview')
def preview():
    image_url = request.args.get("image_url")
    if not image_url:
        return "❌ Please provide an image URL via ?image_url="
    result = detect_and_translate(image_url)
    return "✅ Image translated and processed." if result else "❌ Failed to process the image."

@app.route('/test-salibay')
def test_salibay():
    image_url = "https://salibay.com/cdn/shop/files/O1CN01hYSNtF1miYdArdBvr__2219787484988-0-cib.jpg"
    result = detect_and_translate(image_url)
    return "✅ Salibay image translated and processed." if result else "❌ Failed to process Salibay image."
