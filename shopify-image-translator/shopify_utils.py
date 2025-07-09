import requests
import base64
import os

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_PASSWORD = os.getenv("SHOPIFY_API_PASSWORD")
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")

def get_product_images():
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_STORE}/admin/api/2024-04/products.json"
    res = requests.get(url)
    products = res.json().get("products", [])
    images = []
    for product in products:
        for image in product.get("images", []):
            images.append({
                "product_id": product["id"],
                "image_id": image["id"],
                "src": image["src"]
            })
    return images

def upload_new_image(product_id, image_bytes):
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_STORE}/admin/api/2024-04/products/{product_id}/images.json"
    payload = {
        "image": {
            "attachment": encoded
        }
    }
    res = requests.post(url, json=payload)
    return res.json()
