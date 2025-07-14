from flask import Flask, jsonify, request, send_file
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import base64
import os
import requests
from dotenv import load_dotenv
import logging

load_dotenv()

app = Flask(__name__)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_env_variable(name, required=True):
    value = os.getenv(name)
    if required and not value:
        logger.error(f"Missing required environment variable: {name}")
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value

SHOPIFY_STORE = get_env_variable("SHOPIFY_STORE_DOMAIN")
SHOPIFY_ADMIN_TOKEN = get_env_variable("SHOPIFY_ADMIN_TOKEN")
GOOGLE_API_KEY = get_env_variable("GOOGLE_API_KEY")

SHOPIFY_HEADERS = {
    "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
    "Content-Type": "application/json"
}

VISION_URL = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_API_KEY}"
TRANSLATE_URL = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}"

FONT_PATH = "arial.ttf"

@app.route('/')
def home():
    return '✅ Shopify Translator is running. Use /start or /test-ocr?img=URL'

def detect_and_translate(image_url: str) -> BytesIO | None:
    """
    Detects and translates text in the given image URL, overlays the translation, and returns the new image as a BytesIO buffer.
    If any step fails, returns None.
    """
    try:
        logger.info(f"🔍 Processing image: {image_url}")
        img_response = requests.get(image_url)
        img_response.raise_for_status()
        img_bytes = img_response.content
        b64 = base64.b64encode(img_bytes).decode("utf-8")

        vision_payload = {
            "requests": [{
                "image": {"content": b64},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        vision_resp = requests.post(VISION_URL, json=vision_payload)
        vision_resp.raise_for_status()
        vision_data = vision_resp.json()
        logger.debug(f"📦 Vision API response: {vision_data}")

        if "responses" not in vision_data or not vision_data["responses"]:
            logger.warning("No responses from Vision API")
            return None

        annotations = vision_data["responses"][0].get("textAnnotations", [])
        if not annotations:
            logger.warning("No textAnnotations found")
            return None

        base_img = Image.open(BytesIO(img_bytes)).convert("RGB")
        draw = ImageDraw.Draw(base_img)
        font = ImageFont.truetype(FONT_PATH, size=12) if os.path.exists(FONT_PATH) else ImageFont.load_default()

        for text_data in annotations[1:]:
            orig_text = text_data.get("description")
            bbox = text_data.get("boundingPoly", {}).get("vertices", [])

            if not orig_text or len(bbox) < 2:
                continue

            translate_resp = requests.post(
                TRANSLATE_URL,
                json={"q": orig_text, "target": "en", "format": "text"}
            )
            translate_resp.raise_for_status()
            translations = translate_resp.json().get("data", {}).get("translations", [])
            translated = translations[0].get("translatedText") if translations else None

            if not translated:
                logger.warning(f"Translation failed for: '{orig_text}'")
                continue

            logger.info(f"✅ '{orig_text}' ➜ '{translated}'")

            x = bbox[0].get("x", 0)
            y = bbox[0].get("y", 0)
            x2 = bbox[2].get("x", x + 120) if len(bbox) > 2 else x + 120
            y2 = bbox[2].get("y", y + 25) if len(bbox) > 2 else y + 25
            draw.rectangle([x, y, x2, y2], fill="white")
            draw.text((x, y), translated, fill="black", font=font)

        output = BytesIO()
        base_img.save(output, format="JPEG")
        output.seek(0)
        return output

    except Exception as e:
        logger.error(f"❌ Error in detect_and_translate: {e}", exc_info=True)
        return None

def upload_image_to_shopify(product_id: int, image_data: BytesIO) -> dict | None:
    """
    Uploads image to Shopify for the given product ID.
    Returns API response dict or None on error.
    """
    try:
        encoded = base64.b64encode(image_data.read()).decode()
        payload = {"image": {"attachment": encoded}}
        url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products/{product_id}/images.json"
        resp = requests.post(url, headers=SHOPIFY_HEADERS, json=payload)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"❌ Error uploading image to Shopify: {e}", exc_info=True)
        return None

@app.route('/start', methods=['GET'])
def process_products():
    """
    Fetches up to 10 products from Shopify, processes their images for OCR and translation,
    replaces the original images with processed ones, and returns a summary JSON.
    """
    url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products.json?limit=10"
    logger.info(f"Fetching products from: {url}")
    try:
        response = requests.get(url, headers=SHOPIFY_HEADERS)
        logger.info(f"Shopify response status: {response.status_code}")
        logger.debug(f"Shopify response body: {response.text}")
        response.raise_for_status()
        products = response.json().get("products", [])
    except Exception as e:
        logger.error("Error fetching products", exc_info=True)
        return jsonify({"error": "Failed to fetch products", "details": str(e)}), 500

    if not products:
        return jsonify({"status": "no products found"}), 200

    results = []
    failed = []

    for product in products:
        product_id = product.get("id")
        images = product.get("images", [])

        if not images:
            logger.warning(f"No images for product {product.get('title', 'Unknown')} (ID: {product_id})")
            continue

        for image in images:
            img_src = image.get("src")
            if not img_src:
                logger.warning(f"Skipping image with no 'src' in product ID {product_id}")
                continue

            processed_image = detect_and_translate(img_src)
            if not processed_image:
                failed.append({"product_id": product_id, "image_src": img_src, "reason": "OCR failed"})
                continue

            try:
                # Delete the original image if image ID exists
                image_id = image.get("id")
                if product_id and image_id:
                    del_url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products/{product_id}/images/{image_id}.json"
                    del_resp = requests.delete(del_url, headers=SHOPIFY_HEADERS)
                    logger.info(f"🗑️ Deleted image {image_id} of product {product_id}: {del_resp.status_code}")
                else:
                    logger.warning(f"Missing product_id or image_id — skipping deletion")

                # Upload new image
                upload_result = upload_image_to_shopify(product_id, processed_image)
                if upload_result and upload_result.get("image"):
                    results.append(upload_result)
                else:
                    failed.append({"product_id": product_id, "image_src": img_src, "reason": "Upload failed"})

            except Exception as e:
                failed.append({"product_id": product_id, "image_src": img_src, "reason": str(e)})
                logger.error(f"❌ Error processing product {product_id}: {e}", exc_info=True)

    return jsonify({
        "status": "done",
        "updated_images": len(results),
        "failed_updates": len(failed),
        "failed_logs": failed
    })

@app.route('/test-ocr')
def test_ocr():
    """
    Test OCR and translation by passing an image URL as the 'img' query parameter.
    Returns the processed image or an error.
    """
    img = request.args.get("img")
    if not img:
        return "❌ Provide ?img=image_url", 400
    processed_image = detect_and_translate(img)
    if processed_image:
        return send_file(processed_image, mimetype='image/jpeg')
    return "❌ Failed to process image", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
