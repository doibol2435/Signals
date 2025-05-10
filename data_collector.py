import requests
import pandas as pd
from datetime import datetime, timedelta
from time import sleep
import logging

# Configure logging
logging.basicConfig(filename="signals.log", level=logging.INFO,
                    format="%(asctime)s - %(message)s")

# Cache for pairs with repeated timeouts or failures
TIMEOUT_PAIRS_CACHE = set()
FAILED_PAIRS_CACHE = set()
CACHE_EXPIRATION = timedelta(hours=1)
TIMEOUT_CACHE_TIMESTAMP = datetime.now()
FAILED_CACHE_TIMESTAMP = datetime.now()

def clear_caches():
    """Clear timeout and failed pairs caches if expired."""
    global TIMEOUT_PAIRS_CACHE, FAILED_PAIRS_CACHE, TIMEOUT_CACHE_TIMESTAMP, FAILED_CACHE_TIMESTAMP
    now = datetime.now()
    if now - TIMEOUT_CACHE_TIMESTAMP > CACHE_EXPIRATION:
        TIMEOUT_PAIRS_CACHE.clear()
        TIMEOUT_CACHE_TIMESTAMP = now
        logging.info("Cleared TIMEOUT_PAIRS_CACHE")
    if now - FAILED_CACHE_TIMESTAMP > CACHE_EXPIRATION:
        FAILED_PAIRS_CACHE.clear()
        FAILED_CACHE_TIMESTAMP = now
        logging.info("Cleared FAILED_PAIRS_CACHE")

def get_bybit_price_data(symbol: str, interval: str, limit: int = 150, market_type: str = "spot", retries: int = 3, timeout: int = 10) -> pd.DataFrame:
    """
    Fetch price data from Bybit API for Spot or Futures Market.
    
    Parameters:
        symbol (str): Trading pair (e.g., BTCUSDT).
        interval (str): Time interval (e.g., 15m, 30m, 1h, 4h, 1d).
        limit (int): Number of records (default 150).
        market_type (str): Market type ("spot" or "futures").
        retries (int): Number of retries on connection errors.
        timeout (int): Request timeout in seconds.

    Returns:
        pd.DataFrame: DataFrame with OHLCV data.
    """
    interval_mapping = {
        "1m": "1", "5m": "5", "15m": "15", "30m": "30",
        "1h": "60", "4h": "240", "1d": "D", "1w": "W"
    }

    bybit_interval = interval_mapping.get(interval)
    if not bybit_interval:
        logging.error(f"Invalid interval: {interval}. Valid: {list(interval_mapping.keys())}")
        raise ValueError(f"Invalid interval: {interval}. Valid: {list(interval_mapping.keys())}")

    url = {
        "spot": "https://api.bybit.com/v5/market/kline",
        "futures": "https://api.bybit.com/v5/market/kline"
    }.get(market_type)

    if not url:
        logging.error(f"Invalid market_type: {market_type}. Valid: 'spot' or 'futures'.")
        raise ValueError(f"Invalid market_type: {market_type}. Valid: 'spot' or 'futures'.")

    category = "spot" if market_type == "spot" else "linear"
    params = {
        "category": category,
        "symbol": symbol,
        "interval": bybit_interval,
        "limit": min(limit, 1000)  # Bybit API limit
    }

    clear_caches()

    if symbol in TIMEOUT_PAIRS_CACHE:
        logging.warning(f"Skipping {symbol}: Timed out multiple times.")
        print(f"⏳ Skipping {symbol}: Timed out multiple times.")
        return pd.DataFrame()

    if symbol in FAILED_PAIRS_CACHE:
        logging.warning(f"Skipping {symbol}: Failed multiple times.")
        print(f"⏳ Skipping {symbol}: Failed multiple times.")
        return pd.DataFrame()

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            if data["retCode"] != 0:
                logging.warning(f"Bybit API error for {symbol}: {data['retMsg']}")
                return pd.DataFrame()

            klines = data["result"]["list"]
            if not klines:
                logging.warning(f"No data for {symbol} on {market_type.upper()}.")
                print(f"⚠️ No data for {symbol} on {market_type.upper()}.")
                return pd.DataFrame()

            df = pd.DataFrame(klines, columns=[
                "timestamp", "open", "high", "low", "close", "volume", "turnover"
            ])

            df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms")
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = df[col].astype(float)

            df = df.rename(columns={"turnover": "quote_volume"})
            return df[["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]].sort_values("timestamp")

        except requests.exceptions.Timeout:
            logging.error(f"Timeout fetching data for {symbol} ({attempt}/{retries})")
            print(f"⏱️ Timeout fetching data for {symbol} ({attempt}/{retries})")
            if attempt == retries:
                TIMEOUT_PAIRS_CACHE.add(symbol)
        except requests.exceptions.ConnectionError:
            logging.error(f"Connection error fetching data for {symbol} ({attempt}/{retries})")
            print(f"🔌 Connection error fetching data for {symbol} ({attempt}/{retries})")
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTPError: {http_err} fetching data for {symbol} ({attempt}/{retries})")
            print(f"❗ HTTPError: {http_err} fetching data for {symbol} ({attempt}/{retries})")
        except Exception as e:
            logging.error(f"Unknown error fetching data for {symbol}: {e} ({attempt}/{retries})")
            print(f"❓ Unknown error fetching data for {symbol}: {e} ({attempt}/{retries})")

        sleep(2)

    logging.error(f"Failed to fetch data for {symbol} after {retries} attempts.")
    print(f"❌ Failed to fetch data for {symbol} after {retries} attempts.")
    FAILED_PAIRS_CACHE.add(symbol)
    return pd.DataFrame()

def get_bybit_supported_pairs(market_type: str = "spot"):
    """
    Fetch supported trading pairs from Bybit API.
    
    Parameters:
        market_type (str): Market type ("spot" or "futures").

    Returns:
        set: Set of supported trading pairs.
    """
    url = "https://api.bybit.com/v5/market/tickers"
    category = "spot" if market_type == "spot" else "linear"
    params = {"category": category}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data["retCode"] != 0:
            logging.error(f"Bybit API error: {data['retMsg']}")
            return set()
        symbols = {item["symbol"].upper() for item in data["result"]["list"]}
        return symbols
    except Exception as e:
        logging.error(f"Error fetching Bybit pairs: {e}")
        return set()

def get_bybit_top_pairs(limit: int = 20, market_type: str = "futures"):
    """
    Fetch top trading pairs by 24h volume from Bybit API.
    
    Parameters:
        limit (int): Number of top pairs to return.
        market_type (str): Market type ("spot" or "futures").

    Returns:
        list: List of dictionaries with symbol and volume data.
    """
    url = "https://api.bybit.com/v5/market/tickers"
    category = "spot" if market_type == "spot" else "linear"
    params = {"category": category}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data["retCode"] != 0:
            logging.error(f"Bybit API error: {data['retMsg']}")
            return []
        tickers = data["result"]["list"]
        # Filter for USDT pairs and sort by 24h turnover
        usdt_pairs = [
            {"symbol": item["symbol"].upper(), "volume_24h": float(item["turnover24h"])}
            for item in tickers if item["symbol"].endswith("USDT")
        ]
        usdt_pairs.sort(key=lambda x: x["volume_24h"], reverse=True)
        return usdt_pairs[:limit]
    except Exception as e:
        logging.error(f"Error fetching Bybit top pairs: {e}")
        return []

def get_multi_timeframe_data(symbol: str, intervals: list, market_type: str = "spot") -> dict:
    """
    Fetch price data for multiple timeframes from Bybit.
    
    Parameters:
        symbol (str): Trading pair (e.g., BTCUSDT).
        intervals (list): List of intervals (e.g., ['15m', '30m', '1h', '4h', '1d']).
        market_type (str): Market type ("spot" or "futures").

    Returns:
        dict: Dictionary with timeframe as key and DataFrame as value.
    """
    timeframe_limits = {
        "15m": 2880,  # ~30 days (30 * 24 * 4)
        "30m": 1440,  # ~30 days (30 * 24 * 2)
        "1h": 720,    # ~30 days (30 * 24)
        "4h": 180,    # ~30 days (30 * 6)
        "1d": 30      # ~30 days
    }

    data = {}
    for interval in intervals:
        limit = timeframe_limits.get(interval, 150)
        df = get_bybit_price_data(symbol, interval, limit=limit, market_type=market_type)
        data[interval] = df
    return data