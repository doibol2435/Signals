import pandas as pd
import ta
import logging

# Configure logging
logging.basicConfig(filename="signals.log", level=logging.INFO,
                    format="%(asctime)s - %(message)s")

def compute_indicators(df, ema_periods=None, indicators=None, dropna=True):
    """
    Compute technical indicators for a DataFrame.
    
    Parameters:
        df (pd.DataFrame): DataFrame with 'close', 'high', 'low', 'volume' columns.
        ema_periods (list): List of EMA periods (default [20, 50, 200]).
        indicators (list): List of indicators to compute (default all).
        dropna (bool): Drop NaN values after computation (default True).

    Returns:
        pd.DataFrame: DataFrame with added indicator columns.
    """
    if df.empty:
        logging.error("DataFrame is empty. Please provide valid data.")
        raise ValueError("DataFrame is empty. Please provide valid data.")
    
    required_columns = ["close"]
    if not all(col in df.columns for col in required_columns):
        logging.error("Missing required column: 'close'.")
        raise ValueError("Missing required column: 'close'.")

    df = df.copy()

    if ema_periods is None:
        ema_periods = [20, 50, 200]

    if not all(isinstance(period, int) and period > 0 for period in ema_periods):
        logging.error(f"Invalid ema_periods: {ema_periods}. Must be positive integers.")
        raise ValueError("All EMA periods must be positive integers.")

    all_indicators = ['macd', 'ema', 'atr', 'adx', 'bb', 'rsi', 'stochastic', 'volume']
    if indicators is None:
        indicators = all_indicators
    else:
        invalid_indicators = [ind for ind in indicators if ind not in all_indicators]
        if invalid_indicators:
            logging.error(f"Invalid indicators: {invalid_indicators}. Valid: {all_indicators}")
            raise ValueError(f"Invalid indicators: {invalid_indicators}. Valid: {all_indicators}")

    try:
        if 'macd' in indicators:
            macd_indicator = ta.trend.MACD(close=df["close"])
            df["macd"] = macd_indicator.macd_diff()
            df["macd_line"] = macd_indicator.macd()
            df["signal_line"] = macd_indicator.macd_signal()

        if 'ema' in indicators:
            for period in ema_periods:
                df[f"ema_{period}"] = df["close"].ewm(span=period, adjust=False).mean()

        if 'atr' in indicators and all(col in df.columns for col in ["high", "low", "close"]):
            df["atr"] = ta.volatility.AverageTrueRange(
                high=df["high"], low=df["low"], close=df["close"], window=14
            ).average_true_range()

        if 'adx' in indicators and all(col in df.columns for col in ["high", "low", "close"]):
            df["adx"] = ta.trend.ADXIndicator(
                high=df["high"], low=df["low"], close=df["close"], window=14
            ).adx()

        if 'bb' in indicators:
            bb_indicator = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
            df["bb_upper"] = bb_indicator.bollinger_hband()
            df["bb_lower"] = bb_indicator.bollinger_lband()
            df["bb_mid"] = bb_indicator.bollinger_mavg()

        if 'rsi' in indicators:
            df["rsi"] = ta.momentum.RSIIndicator(close=df["close"], window=14).rsi()

        if 'stochastic' in indicators and all(col in df.columns for col in ["high", "low", "close"]):
            stoch_indicator = ta.momentum.StochasticOscillator(
                high=df["high"], low=df["low"], close=df["close"], window=14, smooth_window=3
            )
            df["stoch_k"] = stoch_indicator.stoch()
            df["stoch_d"] = stoch_indicator.stoch_signal()

        if 'volume' in indicators and "volume" in df.columns:
            df["volume_ma"] = df["volume"].rolling(window=20).mean()

    except Exception as e:
        logging.error(f"Error computing indicators: {e}")
        raise RuntimeError(f"Error computing indicators: {e}")

    if dropna:
        df.dropna(inplace=True)

    return df

def compute_multi_timeframe_indicators(data: dict, ema_periods=None, indicators=None, dropna=True) -> dict:
    """
    Compute indicators for multiple timeframes.
    
    Parameters:
        data (dict): Dictionary with timeframe as key and DataFrame as value.
        ema_periods (list): List of EMA periods.
        indicators (list): List of indicators to compute.
        dropna (bool): Drop NaN values.

    Returns:
        dict: Dictionary with timeframe as key and DataFrame with indicators as value.
    """
    result = {}
    for timeframe, df in data.items():
        if not df.empty:
            try:
                result[timeframe] = compute_indicators(df, ema_periods, indicators, dropna)
            except Exception as e:
                logging.warning(f"Failed to compute indicators for {timeframe}: {e}")
                result[timeframe] = pd.DataFrame()
        else:
            result[timeframe] = df
    return result