import requests

TELEGRAM_TOKEN = "8142201280:AAH9KCcOZXH5XvlvPOPKmvPMy9pKmgPqAFs"
CHAT_ID = "-1002394411271"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=data)
