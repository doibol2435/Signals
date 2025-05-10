import os
import json
import requests

def load_json(file_path, default=None):
    if not os.path.exists(file_path):
        return default
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default

def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

def send_telegram_message(message, bot_token="7205500896:AAEN3lfmN3qfme3f4k7Tt8zqr6vzCt-oEaA", chat_id="-1002170227400"):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        requests.post(url, json=payload)
    except requests.RequestException as e:
        print(f"Lỗi gửi Telegram: {e}")
