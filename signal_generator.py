import pandas as pd
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(filename="signals.log", level=logging.INFO,
                    format="%(asctime)s - %(message)s")

def generate_signal(df, timeframe, min_data_points=50, macd_threshold=0.03, atr_period=14, atr_threshold=0.4,
                    adx_period=14, adx_threshold=20.0, bb_period=20, bb_threshold=0.02,
                    rsi_period=14, rsi_upper=85, rsi_lower=15, stochastic_period=14,
                    stochastic_upper=95, stochastic_lower=5, risk_reward_ratio=1.8,
                    volume_threshold=1.05, signal_cooldown=3, max_price_change=0.08,
                    lookback_period=2, ema_slope_threshold=0.001,
                    futures_risk_reward_ratio=0.8, futures_atr_multiplier=0.8,
                    futures_breakout_period=5, futures_volume_spike=1.2,
                    fast_ema_period=20, futures_rsi_period=6, futures_stochastic_period=6):
    """
    Generate trading signal for a single timeframe.
    
    Parameters:
        df (pd.DataFrame): DataFrame with pre-computed indicators.
        timeframe (str): Timeframe (e.g., '15m', '30m', '1h', '4h', '1d').
        min_data_points (int): Minimum number of data points required.
        ... (other parameters relaxed for more signals)

    Returns:
        tuple: (signal, entry_price, tp_price, sl_price)
    """
    if len(df) < min_data_points:
        logging.warning(f"Not enough data for {timeframe}: {len(df)} < {min_data_points}")
        return "⚠️ Not enough data", None, None, None

    latest = df.iloc[-1]
    current_price = latest["close"]
    try:
        macd = latest["macd"]
        ema_20 = latest["ema_20"]
        atr = latest["atr"]
        adx = latest["adx"]
        bb_upper = latest["bb_upper"]
        bb_lower = latest["bb_lower"]
        rsi = latest["rsi"]
        stoch_k = latest["stoch_k"]
        volume = latest["volume"]
        volume_ma = latest["volume_ma"]
    except KeyError as e:
        logging.error(f"Missing indicator for {timeframe}: {e}")
        return "⚠️ Missing indicators", None, None, None

    # Adjust conditions based on timeframe
    timeframe_multipliers = {
        "15m": {"macd": 0.6, "adx": 0.8, "volume": 1.3},
        "30m": {"macd": 0.7, "adx": 0.85, "volume": 1.2},
        "1h": {"macd": 0.9, "adx": 0.9, "volume": 1.1},
        "4h": {"macd": 1.0, "adx": 1.0, "volume": 1.0},
        "1d": {"macd": 1.1, "adx": 1.1, "volume": 0.9}
    }
    tf = timeframe_multipliers.get(timeframe, {"macd": 1.0, "adx": 1.0, "volume": 1.0})

    # Spot signal conditions (relaxed)
    long_conditions = (
        current_price > ema_20 and
        macd > macd_threshold * tf["macd"] and
        adx > adx_threshold * tf["adx"] and
        current_price < bb_upper * (1 - bb_threshold) and
        volume > volume_ma * volume_threshold * tf["volume"]
    )
    short_conditions = (
        current_price < ema_20 and
        macd < -macd_threshold * tf["macd"] and
        adx > adx_threshold * tf["adx"] and
        current_price > bb_lower * (1 + bb_threshold) and
        volume > volume_ma * volume_threshold * tf["volume"]
    )

    # Futures signal conditions (relaxed, short-term focus)
    futures_long_conditions = (
        timeframe in ["15m", "30m", "1h"] and
        current_price > ema_20 and
        macd > macd_threshold * tf["macd"] * 1.0 and
        adx > adx_threshold * tf["adx"] * 0.8 and
        volume > volume_ma * futures_volume_spike * tf["volume"]
    )
    futures_short_conditions = (
        timeframe in ["15m", "30m", "1h"] and
        current_price < ema_20 and
        macd < -macd_threshold * tf["macd"] * 1.0 and
        adx > adx_threshold * tf["adx"] * 0.8 and
        volume > volume_ma * futures_volume_spike * tf["volume"]
    )

    # Calculate entry, TP, SL
    entry_price = current_price
    if long_conditions:
        signal = "🟢⬆️ LONG"
        tp_price = entry_price + atr * risk_reward_ratio
        sl_price = entry_price - atr
    elif short_conditions:
        signal = "🔻 SHORT"
        tp_price = entry_price - atr * risk_reward_ratio
        sl_price = entry_price + atr
    elif futures_long_conditions:
        signal = "🟢🚀 FUTURES LONG"
        tp_price = entry_price + atr * futures_atr_multiplier * futures_risk_reward_ratio
        sl_price = entry_price - atr * futures_atr_multiplier
    elif futures_short_conditions:
        signal = "🔻🚀 FUTURES SHORT"
        tp_price = entry_price - atr * futures_atr_multiplier * futures_risk_reward_ratio
        sl_price = entry_price + atr * futures_atr_multiplier
    else:
        signal = "⚠️ No signal"
        entry_price = tp_price = sl_price = None

    if signal != "⚠️ No signal":
        logging.info(f"Generated signal for {timeframe}: {signal}")

    return signal, entry_price, tp_price, sl_price

def generate_multi_timeframe_signals(data: dict, **kwargs) -> dict:
    """
    Generate signals for multiple timeframes.
    
    Parameters:
        data (dict): Dictionary with timeframe as key and DataFrame as value.
        **kwargs: Parameters for generate_signal.

    Returns:
        dict: Dictionary with timeframe as key and signal tuple as value.
    """
    signals = {}
    for timeframe, df in data.items():
        if not df.empty:
            signal, entry, tp, sl = generate_signal(df, timeframe, **kwargs)
            signals[timeframe] = {
                "signal": signal,
                "entry": entry,
                "tp": tp,
                "sl": sl,
                "current_price": df["close"].iloc[-1] if not df.empty else None
            }
        else:
            signals[timeframe] = {
                "signal": "⚠️ No data",
                "entry": None,
                "tp": None,
                "sl": None,
                "current_price": None
            }
    return signals