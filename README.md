# Shopify Image Text Translator with Google Vision API

This app scans your Shopify product images, detects any non-English text, translates it to English using Google Translate, overlays it on the image, and uploads the updated image back to Shopify.

## Features

- Google Vision OCR
- Google Translate API
- Replaces Shopify product images with English-translated versions
- Flask API deployed to Railway

## Setup

1. Clone the repo
2. Create `.env` based on `.env.example`
3. Upload to Railway
4. Visit `/start` to trigger translation

## Deployment

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/YOUR_USERNAME/shopify-image-translator&envs=SHOPIFY_STORE_DOMAIN,SHOPIFY_ADMIN_TOKEN,GOOGLE_API_KEY)

