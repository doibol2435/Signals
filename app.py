import requests
import pandas as pd
import json
import os
import logging
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, flash
from data_collector import get_multi_timeframe_data, get_bybit_supported_pairs, get_bybit_top_pairs
from ta_processor import compute_multi_timeframe_indicators
from signal_generator import generate_multi_timeframe_signals
from datetime import datetime, timezone, timedelta

BOT_TOKEN = "8142201280:AAH9KCcOZXH5XvlvPOPKmvPMy9pKmgPqAFs"
CHAT_ID = "-1002394411271"

app = Flask(__name__)
app.secret_key = "your-very-secret-key-123456"

LAST_SIGNAL_FILE = "last_signal.json"
ACTIVE_SIGNAL_FILE = "active_signals.json"
NEW_SIGNALS_FILE = "new_signals.json"

logging.basicConfig(filename="signals.log", level=logging.INFO,
                    format="%(asctime)s - %(message)s")

BYBIT_PAIRS_CACHE = get_bybit_supported_pairs(market_type="futures")

def log_signal(symbol: str, signal: str, timeframe: str, duration: str = None):
    timestamp = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M")
    log_message = f"{timestamp} | {symbol} | {timeframe} | {signal}"
    if duration:
        log_message += f" | Duration: {duration}"
    logging.info(log_message)

def load_last_signals():
    if not os.path.exists(LAST_SIGNAL_FILE):
        return {}
    try:
        with open(LAST_SIGNAL_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_last_signals(data):
    with open(LAST_SIGNAL_FILE, "w") as f:
        json.dump(data, f)

def load_active_signals():
    if not os.path.exists(ACTIVE_SIGNAL_FILE):
        return []
    try:
        with open(ACTIVE_SIGNAL_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_active_signals(signals):
    unique_signals = {}
    for signal in signals:
        key = f"{signal['symbol']}_{signal['timeframe']}"
        if key in unique_signals:
            if unique_signals[key]["time"] < signal["time"]:
                unique_signals[key] = signal
        else:
            unique_signals[key] = signal
    with open(ACTIVE_SIGNAL_FILE, "w") as f:
        json.dump(list(unique_signals.values()), f, indent=2)

def load_new_signals():
    if not os.path.exists(NEW_SIGNALS_FILE):
        return []
    try:
        with open(NEW_SIGNALS_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_new_signals(signals):
    with open(NEW_SIGNALS_FILE, "w") as f:
        json.dump(signals, f, indent=2)

def send_telegram_message_newbot(message, signal_time=None, current_price=None):
    BOT_TOKEN_NEW = "8142201280:AAH9KCcOZXH5XvlvPOPKmvPMy9pKmgPqAFs"
    CHAT_ID_NEW = "-1002394411271"
    if current_price:
        message += f"\n💰 Current Price: ${current_price:.4f}"
    if signal_time:
        message += f"\n🕒 Time: {signal_time}"
    url = f"https://api.telegram.org/bot{BOT_TOKEN_NEW}/sendMessage"
    payload = {"chat_id": CHAT_ID_NEW, "text": message}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Error sending Telegram new bot: {e}")

def is_duplicate_signal(symbol: str, signal: str, timeframe: str, hours: int = 3) -> bool:
    data = load_last_signals()
    key = f"{symbol}_{timeframe}"
    if key not in data:
        return False
    last_time_str, last_signal = data[key]
    last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return signal == last_signal and (now - last_time) < timedelta(hours=hours)

def update_last_signal(symbol: str, signal: str, timeframe: str):
    data = load_last_signals()
    now = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M")
    data[f"{symbol}_{timeframe}"] = [now, signal]
    save_last_signals(data)

def update_signal_status(signal_item):
    from data_collector import get_bybit_price_data
    try:
        df = get_bybit_price_data(signal_item["symbol"], interval=signal_item["timeframe"], limit=2, market_type="futures" if "FUTURES" in signal_item["signal"] else "spot")
        current_price = df["close"].iloc[-1] if not df.empty else signal_item["current_price"]
        entry_price = signal_item["entry"]
        tp_price = signal_item["tp"]
        sl_price = signal_item["sl"]
        raw_signal = signal_item["signal"]
        signal_time = signal_item["time"]

        signal_type = "LONG" if "LONG" in raw_signal.upper() else "SHORT" if "SHORT" in raw_signal.upper() else ""

        signal_item["current_price"] = current_price
        sent_flag = signal_item.get("sent_flag", False)

        reached_tp = False
        reached_sl = False
        change_pct = 0

        # Tính thời gian từ khi bắt đầu đến hiện tại
        start_time = datetime.strptime(signal_time, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        end_time = datetime.now(timezone.utc) + timedelta(hours=7)  # Thời gian hiện tại (UTC+7)
        duration = end_time - start_time
        days = duration.days
        seconds = duration.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        duration_str = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"

        if signal_type == "LONG":
            change_pct = ((current_price - entry_price) / entry_price) * 100
            if current_price >= tp_price:
                signal_item["status"] = "✅ Đạt TP"
                reached_tp = True
            elif current_price <= sl_price:
                signal_item["status"] = "❌ Dừng lỗ"
                reached_sl = True
            else:
                signal_item["status"] = f"⏳ Đang theo dõi ({change_pct:+.2f}%)"
        elif signal_type == "SHORT":
            change_pct = ((entry_price - current_price) / entry_price) * 100
            if current_price <= tp_price:
                signal_item["status"] = "✅ Đạt TP"
                reached_tp = True
            elif current_price >= sl_price:
                signal_item["status"] = "❌ Dừng lỗ"
                reached_sl = True
            else:
                signal_item["status"] = f"⏳ Đang theo dõi ({change_pct:+.2f}%)"
        else:
            signal_item["status"] = "⚠️ Tín hiệu không xác định"

        if (reached_tp or reached_sl) and not sent_flag:
            message = (
                f"📊 Coin: #{signal_item['symbol']} ({signal_item['timeframe']})\n"
                f"📈 TA: {signal_item['signal']}\n"
                f"🎯 Entry: ${entry_price:.4f}\n"
                f"✅ TP: ${tp_price:.4f}\n"
                f"❌ SL: ${sl_price:.4f}\n"
                f"📊 Change: {change_pct:+.2f}%\n"
                f"⏳ Duration: {duration_str}\n"
                f"Status: {signal_item['status']}"
            )
            send_telegram_message_newbot(message, signal_time, current_price)
            signal_item["sent_flag"] = True
            signal_item["duration"] = duration_str

            stats = load_win_loss_stats()
            if signal_type in stats:
                if reached_tp:
                    stats[signal_type]["win"] += 1
                elif reached_sl:
                    stats[signal_type]["loss"] += 1
                stats[signal_type]["count"] = stats[signal_type]["win"] + stats[signal_type]["loss"]
                save_win_loss_stats(stats)

            log_signal(signal_item["symbol"], signal_item["signal"], signal_item["timeframe"], duration_str)
            return False
        return True
    except Exception as e:
        signal_item["status"] = "⚠️ Lỗi cập nhật"
        print(f"Error updating signal for {signal_item['symbol']} ({signal_item['timeframe']}): {e}")
        return True

def update_signal_counts(signal_item):
    stats = load_win_loss_stats()
    signal_type = "LONG" if "LONG" in signal_item["signal"].upper() else "SHORT"
    stats[signal_type]["count"] = stats[signal_type].get("count", 0) + 1
    save_win_loss_stats(stats)

def send_telegram_signal_and_track(signal_item):
    if is_duplicate_signal(signal_item['symbol'], signal_item['signal'], signal_item['timeframe']):
        print(f"Bỏ qua {signal_item['symbol']} ({signal_item['timeframe']}): Tín hiệu trùng lặp.")
        return

    message = (
        f"📊 Coin: #{signal_item['symbol']} ({signal_item['timeframe']})\n"
        f"💰 Price: ${signal_item['current_price']:.4f}\n"
        f"📈 TA: {signal_item['signal']}\n"
        f"🎯 Entry: ${signal_item['entry']:.4f}\n"
        f"✅ TP: ${signal_item['tp']:.4f}\n"
        f"❌ SL: ${signal_item['sl']:.4f}\n"
        f"Status: {signal_item['status']}\n"
        f"🕒 Time: {signal_item['time']}"
    )
    send_telegram_message_newbot(message)
    update_signal_counts(signal_item)
    new_signals = load_new_signals()
    new_signals.append(signal_item)
    save_new_signals(new_signals)

def clean_finished_signals():
    active_signals = load_active_signals()
    updated_signals = []
    for signal in active_signals:
        if update_signal_status(signal):
            updated_signals.append(signal)
    save_active_signals(updated_signals)
    return updated_signals

def get_top_coins_with_signals():
    top_pairs = get_bybit_top_pairs(limit=20, market_type="futures")
    timeframes = ["15m", "30m", "1h", "4h", "1d"]
    top_coins = []
    active_signals = load_active_signals()
    signal_counts = {tf: 0 for tf in timeframes}

    for pair in top_pairs:
        symbol = pair["symbol"]
        if symbol not in BYBIT_PAIRS_CACHE:
            print(f"Skipping {symbol}: Not available on Bybit.")
            continue

        try:
            market_type = "futures"
            data = get_multi_timeframe_data(symbol, timeframes, market_type=market_type)
            data_with_indicators = compute_multi_timeframe_indicators(
                data, ema_periods=[20, 50, 200],
                indicators=['macd', 'ema', 'atr', 'adx', 'bb', 'rsi', 'stochastic', 'volume']
            )
            signals = generate_multi_timeframe_signals(
                data_with_indicators,
                min_data_points=50,
                macd_threshold=0.03,
                atr_period=14,
                atr_threshold=0.4,
                adx_period=14,
                adx_threshold=20.0,
                bb_period=20,
                bb_threshold=0.02,
                rsi_period=14,
                rsi_upper=85,
                rsi_lower=15,
                stochastic_period=14,
                stochastic_upper=95,
                stochastic_lower=5,
                risk_reward_ratio=1.8,
                volume_threshold=1.05,
                signal_cooldown=3,
                max_price_change=0.08,
                lookback_period=2,
                ema_slope_threshold=0.001,
                futures_risk_reward_ratio=0.8,
                futures_atr_multiplier=0.8,
                futures_breakout_period=5,
                futures_volume_spike=1.2,
                fast_ema_period=20,
                futures_rsi_period=6,
                futures_stochastic_period=6
            )

            for timeframe, signal_info in signals.items():
                signal = signal_info["signal"]
                if signal in ["🟢⬆️ LONG", "🔻 SHORT", "🟢🚀 FUTURES LONG", "🔻🚀 FUTURES SHORT"]:
                    if is_duplicate_signal(symbol, signal, timeframe):
                        print(f"Skipping {symbol} ({timeframe}): Duplicate signal.")
                        continue

                    existing_signal = next((s for s in active_signals if s["symbol"] == symbol and s["timeframe"] == timeframe and s["signal"] == signal), None)
                    if existing_signal:
                        print(f"Skipping {symbol} ({timeframe}): Signal already active.")
                        continue

                    now = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M")
                    signal_item = {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "signal": signal,
                        "entry": signal_info["entry"],
                        "tp": signal_info["tp"],
                        "sl": signal_info["sl"],
                        "current_price": signal_info["current_price"],
                        "time": now,
                        "status": "Đang theo dõi"
                    }

                    top_coins.append(signal_item)
                    send_telegram_signal_and_track(signal_item)
                    log_signal(symbol, signal, timeframe)
                    update_last_signal(symbol, signal, timeframe)
                    active_signals.append(signal_item)
                    signal_counts[timeframe] += 1

        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    save_active_signals(active_signals)
    logging.info(f"Signal counts: {signal_counts}")
    return top_coins

@app.route('/', methods=['GET', 'POST'])
def index():
    coin = request.form.get("coin", "BTCUSDT").upper()
    timeframes = ["15m", "30m", "1h", "4h", "1d"]
    signals = {}

    if coin not in BYBIT_PAIRS_CACHE:
        flash(f"Cặp giao dịch {coin} không tồn tại trên Bybit.", "error")
        return render_template("index.html", coin=coin, signals={}, top_coins=[], active_signals=[])

    try:
        data = get_multi_timeframe_data(coin, timeframes, market_type="futures")
        data_with_indicators = compute_multi_timeframe_indicators(
            data, ema_periods=[20, 50, 200],
            indicators=['macd', 'ema', 'atr', 'adx', 'bb', 'rsi', 'stochastic', 'volume']
        )
        signals = generate_multi_timeframe_signals(
            data_with_indicators,
            min_data_points=50,
            macd_threshold=0.03,
            atr_period=14,
            atr_threshold=0.4,
            adx_period=14,
            adx_threshold=20.0,
            bb_period=20,
            bb_threshold=0.02,
            rsi_period=14,
            rsi_upper=85,
            rsi_lower=15,
            stochastic_period=14,
            stochastic_upper=95,
            stochastic_lower=5,
            risk_reward_ratio=1.8,
            volume_threshold=1.05,
            signal_cooldown=3,
            max_price_change=0.08,
            lookback_period=2,
            ema_slope_threshold=0.001,
            futures_risk_reward_ratio=0.8,
            futures_atr_multiplier=0.8,
            futures_breakout_period=5,
            futures_volume_spike=1.2,
            fast_ema_period=20,
            futures_rsi_period=6,
            futures_stochastic_period=6
        )
    except Exception as e:
        flash(f"Lỗi khi phân tích {coin}: {e}", "error")

    top_coins = get_top_coins_with_signals()
    active_signals = clean_finished_signals()
    stats = load_win_loss_stats()

    return render_template("index.html", coin=coin, signals=signals, top_coins=top_coins,
                           active_signals=active_signals, win_loss_stats=stats)

@app.route('/send', methods=['POST'])
def send():
    coin = request.form.get("coin", "BTCUSDT").upper()
    timeframes = ["15m", "30m", "1h", "4h", "1d"]

    if coin not in BYBIT_PAIRS_CACHE:
        flash(f"Cặp giao dịch {coin} không tồn tại trên Bybit.", "error")
        return redirect(url_for('index'))

    try:
        data = get_multi_timeframe_data(coin, timeframes, market_type="futures")
        data_with_indicators = compute_multi_timeframe_indicators(
            data, ema_periods=[20, 50, 200],
            indicators=['macd', 'ema', 'atr', 'adx', 'bb', 'rsi', 'stochastic', 'volume']
        )
        signals = generate_multi_timeframe_signals(
            data_with_indicators,
            min_data_points=50,
            macd_threshold=0.03,
            atr_period=14,
            atr_threshold=0.4,
            adx_period=14,
            adx_threshold=20.0,
            bb_period=20,
            bb_threshold=0.02,
            rsi_period=14,
            rsi_upper=85,
            rsi_lower=15,
            stochastic_period=14,
            stochastic_upper=95,
            stochastic_lower=5,
            risk_reward_ratio=1.8,
            volume_threshold=1.05,
            signal_cooldown=3,
            max_price_change=0.08,
            lookback_period=2,
            ema_slope_threshold=0.001,
            futures_risk_reward_ratio=0.8,
            futures_atr_multiplier=0.8,
            futures_breakout_period=5,
            futures_volume_spike=1.2,
            fast_ema_period=20,
            futures_rsi_period=6,
            futures_stochastic_period=6
        )

        active_signals = load_active_signals()
        for timeframe, signal_info in signals.items():
            signal = signal_info["signal"]
            if signal in ["🟢⬆️ LONG", "🔻 SHORT", "🟢🚀 FUTURES LONG", "🔻🚀 FUTURES SHORT"]:
                if is_duplicate_signal(coin, signal, timeframe):
                    print(f"Skipping {coin} ({timeframe}): Duplicate signal.")
                    continue

                now = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M")
                signal_item = {
                    "symbol": coin,
                    "timeframe": timeframe,
                    "signal": signal,
                    "entry": signal_info["entry"],
                    "tp": signal_info["tp"],
                    "sl": signal_info["sl"],
                    "current_price": signal_info["current_price"],
                    "time": now,
                    "status": "Đang theo dõi"
                }
                send_telegram_signal_and_track(signal_item)
                log_signal(coin, signal, timeframe)
                update_last_signal(coin, signal, timeframe)
                active_signals.append(signal_item)

        save_active_signals(active_signals)
    except Exception as e:
        flash(f"Lỗi khi gửi tín hiệu cho {coin}: {e}", "error")

    return redirect(url_for('index'))

@app.route('/get_latest_signals')
def get_latest_signals():
    active_signals = load_active_signals()
    top_coins = get_top_coins_with_signals()
    active_signals_data = [
        {
            "symbol": s["symbol"],
            "timeframe": s["timeframe"],
            "signal": s["signal"],
            "entry": s["entry"],
            "tp": s["tp"],
            "sl": s["sl"],
            "current_price": s.get("current_price"),
            "status": s["status"],
            "time": s["time"],
            "duration": s.get("duration")  # Thêm duration
        }
        for s in active_signals
    ]
    top_coins_data = [
        {
            "symbol": c["symbol"],
            "timeframe": c["timeframe"],
            "current_price": c["current_price"],
            "signal": c["signal"],
            "entry": c["entry"],
            "tp": c["tp"],
            "sl": c["sl"]
        }
        for c in top_coins
    ]
    return jsonify({
        "top_coins": top_coins_data,
        "active_signals": active_signals_data
    })

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.route('/test_newbot', methods=['POST'])
def test_newbot():
    BOT_TOKEN_NEW = "8142201280:AAH9KCcOZXH5XvlvPOPKmvPMy9pKmgPqAFs"
    CHAT_ID_NEW = "-1002394411271"
    url = f"https://api.telegram.org/bot{BOT_TOKEN_NEW}/sendMessage"
    payload = {"chat_id": CHAT_ID_NEW, "text": "✅ Bot test thành công!"}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        flash("Đã gửi test thành công tới Telegram bot mới.", "success")
    except Exception as e:
        flash(f"Lỗi gửi test bot mới: {e}", "danger")
    return redirect(url_for('index'))

def load_win_loss_stats():
    stats_file = "win_loss_stats.json"
    if not os.path.exists(stats_file):
        return {"LONG": {"count": 0, "win": 0, "loss": 0}, "SHORT": {"count": 0, "win": 0, "loss": 0}}
    try:
        with open(stats_file, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"LONG": {"count": 0, "win": 0, "loss": 0}, "SHORT": {"count": 0, "win": 0, "loss": 0}}

def save_win_loss_stats(stats):
    stats_file = "win_loss_stats.json"
    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)

def update_win_loss_stats(signal_item):
    stats = load_win_loss_stats()
    signal_type = "LONG" if "LONG" in signal_item["signal"].upper() else "SHORT"
    if "✅ Đạt TP" in signal_item["status"]:
        stats[signal_type]["win"] += 1
    elif "❌ Dừng lỗ" in signal_item["status"]:
        stats[signal_type]["loss"] += 1
    stats[signal_type]["count"] = stats[signal_type]["win"] + stats[signal_type]["loss"]
    save_win_loss_stats(stats)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5002)