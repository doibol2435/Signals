import lightgbm as lgb
import pandas as pd
import numpy as np
import os
import requests
import time
import threading
import signal
import sys

# Cảnh báo: Không nên hard-code trong thực tế
BOT_TOKEN = "7205500896:AAEN3lfmN3qfme3f4k7Tt8zqr6vzCt-oEaA"  # Thay thế bằng token bot của bạn
CHAT_ID = "-1002170227400"  # Thay thế bằng chat ID của bạn

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, short_window=12, long_window=26, signal_window=9):
    ema_short = series.ewm(span=short_window, adjust=False).mean()
    ema_long = series.ewm(span=long_window, adjust=False).mean()
    macd = ema_short - ema_long
    signal = macd.ewm(span=signal_window, adjust=False).mean()
    return macd - signal

def calculate_bollinger_width(series, window=20):
    sma = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return (2 * std) / sma

def add_features(df):
    df["rsi"] = calculate_rsi(df["close"])
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["macd"] = calculate_macd(df["close"])
    df["boll_width"] = calculate_bollinger_width(df["close"])
    df["price_change"] = df["close"].pct_change()
    df["volume_change"] = df["volume"].pct_change()
    df["volatility_3candle"] = df["close"].rolling(window=3).std()
    return df

# ================= MODEL =================
FEATURES = ["rsi", "ema20", "macd", "boll_width", "price_change", "volume_change", "volatility_3candle"]
MODEL_PATH = "model/lgb_model.txt"

def train_model(df):
    df = add_features(df.copy()).dropna()
    if len(df) < 50:
        print("❌ Không đủ dữ liệu để huấn luyện.")
        return

    df["label"] = (df["close"].shift(-1) > df["close"] * 1.002).astype(int)
    X, y = df[FEATURES], df["label"]

    model = lgb.LGBMClassifier()
    model.fit(X, y)
    acc = model.score(X, y)

    os.makedirs("model", exist_ok=True)
    model.booster_.save_model(MODEL_PATH)
    print(f"✅ Model trained | Accuracy: {acc:.2%}")

def predict(df):
    if not os.path.exists(MODEL_PATH):
        return "NO_MODEL"

    df = add_features(df.copy()).dropna()
    if len(df) < 1:
        return "NO_DATA"

    model = lgb.Booster(model_file=MODEL_PATH)
    latest = df[FEATURES].iloc[-1: ]
    pred = model.predict(latest)

    # Sửa: trả về tín hiệu có emoji cho AI
    return "AI LONG ✅" if pred[0] > 0.5 else "AI SHORT 🔻"

# ================= DATA =================
def get_price_data(symbol="BTCUSDT", interval="4h", limit=150):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
        return df[["timestamp", "close", "volume"]]
    except Exception as e:
        print(f"❌ Lỗi lấy dữ liệu: {e}")
        return pd.DataFrame()

# ================= TELEGRAM =================
def send_telegram_signal(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ BOT_TOKEN hoặc CHAT_ID không hợp lệ.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("📬 Đã gửi tín hiệu Telegram.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Gửi tín hiệu Telegram thất bại: {e}")

# ================= MAIN =================
# Global flag to stop the loop
stop_event = threading.Event()

def signal_handler(sig, frame):
    """
    Handle termination signals (e.g., Ctrl+C).
    """
    print("🛑 Dừng chương trình.")
    stop_event.set()

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main_loop():
    """
    Main loop for fetching data, training the model, and sending signals.
    """
    try:
        while not stop_event.is_set():
            price_data = get_price_data("BTCUSDT", "4h", 150)
            if not price_data.empty:
                if not os.path.exists(MODEL_PATH):
                    print("🔁 Huấn luyện mô hình...")
                    train_model(price_data)

                signal = predict(price_data)
                print("📈 Tín hiệu AI:", signal)
                send_telegram_signal(f"Tín hiệu mới:\n{signal}")
            else:
                print("❌ Không lấy được dữ liệu.")

            stop_event.wait(2 * 60)  # Wait with timeout instead of sleep
    except Exception as e:
        print(f"⚠️ Lỗi trong vòng lặp chính: {e}")
    finally:
        print("✅ Đã dọn dẹp tài nguyên và thoát.")

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("🛑 Dừng chương trình.")
    finally:
        print("✅ Đã dọn dẹp tài nguyên và thoát.")
        sys.exit(0)