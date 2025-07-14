# Upgraded `app.py` with enhanced /start debug logging and error handling

from flask import Flask, jsonify, request, send_file
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import base64
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE_DOMAIN")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

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
            return None

        annotations = vision_resp["responses"][0].get("textAnnotations", [])
        if not annotations:
            return None

        base_img = Image.open(BytesIO(img_bytes)).convert("RGB")
        draw = ImageDraw.Draw(base_img)
        font = ImageFont.truetype("arial.ttf", size=12) if os.path.exists("arial.ttf") else ImageFont.load_default()

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
            draw.rectangle([x, y, x + 120, y + 25], fill="white")
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
        return requests.post(url, headers=SHOPIFY_HEADERS, json=payload).json()
    except Exception as e:
        print(f"❌ Error uploading image to Shopify: {e}")
        return None

@app.route('/start', methods=['GET'])
def process_products():
    url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products.json?limit=10"
    try:
        response = requests.get(url, headers=SHOPIFY_HEADERS)
        response.raise_for_status()
        products = response.json().get("products", [])
    except Exception as e:
        return jsonify({"error": "Failed to fetch products", "details": str(e)}), 500

    if not products:
        return jsonify({"status": "no products found"}), 200

    results = []
    failed = []

    for product in products:
        product_id = product.get("id")
        images = product.get("images", [])

        if not images:
            print(f"❌ No images for product {product.get('title', 'Unknown')}")
            continue

        for image in images:
            img_src = image.get("src")
            if not img_src:
                print(f"⚠️ Skipping image with no 'src' in product ID {product_id}")
                continue

            processed_image = detect_and_translate(img_src)
            if not processed_image:
                failed.append({"product_id": product_id, "image_src": img_src, "reason": "OCR failed"})
                continue

            try:
                # If image ID exists, delete the original image
                image_id = image.get("id")
                if product_id and image_id:
                    del_url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products/{product_id}/images/{image_id}.json"
                    del_resp = requests.delete(del_url, headers=SHOPIFY_HEADERS)
                    print(f"🗑️ Deleted image {image_id} of product {product_id}: {del_resp.status_code}")
                else:
                    print(f"⚠️ Missing product_id or image_id — skipping deletion")

                # Upload new image
                upload_result = upload_image_to_shopify(product_id, processed_image)
                if upload_result and upload_result.get("image"):
                    results.append(upload_result)
                else:
                    failed.append({"product_id": product_id, "image_src": img_src, "reason": "Upload failed"})

            except Exception as e:
                failed.append({"product_id": product_id, "image_src": img_src, "reason": str(e)})
                print(f"❌ Error processing product {product_id}: {e}")

    return jsonify({
        "status": "done",
        "updated_images": len(results),
        "failed_updates": len(failed),
        "failed_logs": failed
    })


@app.route('/test-ocr')
def test_ocr():
    img = request.args.get("img")
    if not img:
        return "❌ Provide ?img=image_url", 400
    processed_image = detect_and_translate(img)
    if processed_image:
        return send_file(processed_image, mimetype='image/jpeg')
    return "❌ Failed to process image", 500

