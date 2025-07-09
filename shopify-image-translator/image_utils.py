from google.cloud import vision
from google.cloud import translate_v2 as translate
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import os

def process_image(image_url):
    # Load image from URL
    image_data = requests.get(image_url).content
    image = vision.Image(content=image_data)

    # OCR
    vision_client = vision.ImageAnnotatorClient()
    response = vision_client.text_detection(image=image)
    annotations = response.text_annotations
    if not annotations:
        return None

    original_text = annotations[0].description.strip()
    translate_client = translate.Client()
    translated = translate_client.translate(original_text, target_language='en')
    translated_text = translated["translatedText"]

    # Draw on image
    pil_img = Image.open(BytesIO(image_data)).convert("RGB")
    draw = ImageDraw.Draw(pil_img)
    font = ImageFont.truetype("arial.ttf", 30)
    draw.text((10, 10), translated_text, fill="black", font=font)

    output = BytesIO()
    pil_img.save(output, format="JPEG")
    return output.getvalue()
