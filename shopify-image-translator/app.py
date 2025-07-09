from flask import Flask, jsonify
from dotenv import load_dotenv
from shopify_utils import get_product_images, upload_new_image
from image_utils import process_image
import os

load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

app = Flask(__name__)

@app.route("/start-translation")
def translate_images():
    images = get_product_images()
    updated = 0
    for img in images:
        try:
            print(f"Processing image: {img['src']}")
            new_image = process_image(img["src"])
            if new_image:
                upload_new_image(img["product_id"], new_image)
                updated += 1
        except Exception as e:
            print(f"Error processing image {img['src']}: {e}")
    return jsonify({"message": f"{updated} images translated and replaced."})

if __name__ == "__main__":
    app.run(debug=True)
