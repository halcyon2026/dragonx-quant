# -*- coding: utf-8 -*-
"""DragonX Pro - Professional-Grade Multi-Market Technical Analysis Streamlit App
Professional K-line charts with Plotly featuring TradingView-style dark theme.
Chinese convention: Red = up (涨), Green = down (跌)
Features: Watchlist, Right-side Decision Panel, Technical Indicator Sub-charts
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
import re
from datetime import datetime, timedelta
import ast
warnings.filterwarnings("ignore")

# Data source availability
try:
    import akshare as ak
    AK_OK = True
except ImportError:
    AK_OK = False

try:
    import baostock as bs
    BS_OK = True
except ImportError:
    BS_OK = False

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

# Streamlit page configuration
st.set_page_config(
    page_title="DragonX Pro - 量化分析",
    page_icon="X",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ Chinese Convention Dark Theme ============
TV_THEME = {
    'bg_color': '#131722', 'grid_color': '#1e222d', 'text_color': '#d1d4dc',
    'border_color': '#2a2e39', 'up_color': '#FF3333', 'down_color': '#00AA00',
    'sma20_color': '#2962ff', 'sma50_color': '#ff6d00', 'boll_color': '#787b86',
    'volume_up': 'rgba(255, 51, 51, 0.5)', 'volume_down': 'rgba(0, 170, 0, 0.5)',
    'macd_color': '#2962ff', 'signal_color': '#ff6d00', 'rsi_color': '#7c4dff',
    'k_color': '#2962ff', 'd_color': '#ff6d00', 'j_color': '#e040fb',
}

PERIOD_MAP = {
    "日线": {"bs_freq": "d", "yf_interval": "1d"},
    "60分钟": {"bs_freq": "60", "yf_interval": "60m"},
    "30分钟": {"bs_freq": "30", "yf_interval": "30m"},
    "15分钟": {"bs_freq": "15", "yf_interval": "15m"},
    "5分钟": {"bs_freq": "5", "yf_interval": "5m"},
}

# ============ Default Watchlist ============
DEFAULT_WATCHLIST = [
    ("000001", "平安银行"),
    ("600519", "贵州茅台"),
    ("601899", "紫金矿业"),
    ("000858", "五粮液"),
    ("300750", "宁德时代"),
]

# ============ Helper Functions ============

def mkt(code):
    """Determine market type based on stock code pattern."""
    code = str(code).upper().strip()
    if re.match(r"^(600|601|603|605|688)", code): return "A_sh"
    if re.match(r"^(000|001|002|003|300)", code): return "A_sz"
    if re.match(r"^[0-9]{4,5}$", code): return "HK"
    if re.match(r"^[A-Z]+$", code): return "US"
    return "Unknown"

def stock_name(code):
    """Get A-share stock name via baostock."""
    if not BS_OK: return code
    try:
        bs.login()
        market = "sh" if mkt(code) == "A_sh" else "sz"
        full_code = f"{market}.{code}"
        rs = bs.query_stock_info(code=full_code)
        data_list = []
        while (rs.error_code == "0") and rs.next(): data_list.append(rs.get_row_data())
        if data_list and len(data_list[0]) > 1 and data_list[0][1]: return data_list[0][1]
    except: pass
    finally:
        try: bs.logout()
        except: pass
    return code

def demo(code):
    """Generate random price data for demo/fallback."""
    np.random.seed(hash(code) % 2**32)
    dates = pd.date_range(end=datetime.now(), periods=250, freq="B")
    n = len(dates)
    close = 100 * (1 + np.cumsum(np.random.randn(n) * 0.02))
    high = close * (1 + np.abs(np.random.randn(n) * 0.015))
    low = close * (1 - np.abs(np.random.randn(n) * 0.015))
    open_ = close * (1 + np.random.randn(n) * 0.01)
    volume = np.random.randint(1000000, 10000000, n)
    df = pd.DataFrame({"date": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})
    df.set_index("date", inplace=True)
    df["_demo"] = True
    return df

def fetch(code, period="日线"):
    """Fetch stock data from multiple sources with period support."""
    market = mkt(code)
    msg = ""
    df = None
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    period_params = PERIOD_MAP.get(period, PERIOD_MAP["日线"])
    bs_freq = period_params["bs_freq"]
    yf_interval = period_params["yf_interval"]
    if period != "日线": start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    # Baostock for A-shares
    if market in ["A_sh", "A_sz"] and BS_OK:
        try:
            bs.login()
            bs_market = "sh" if market == "A_sh" else "sz"
            rs = bs.query_history_k_data_plus(f"{bs_market}.{code}", "date,open,high,low,close,volume",
                start_date=start_date, end_date=end_date, frequency=bs_freq, adjustflag="3")
            data_list = []
            while (rs.error_code == "0") and rs.next(): data_list.append(rs.get_row_data())
            if data_list:
                df = pd.DataFrame(data_list, columns=rs.fields)
                col_map = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"}
                df = df.rename(columns=col_map)
                for col in ["open", "high", "low", "close", "volume"]: df[col] = pd.to_numeric(df[col], errors="coerce")
                df["date"] = pd.to_datetime(df["date"])
                df.set_index("date", inplace=True)
                msg = f"Data from Baostock ({period})"
            bs.logout()
        except Exception as e: msg = f"Baostock error: {str(e)[:50]}"
    
    # Akshare as secondary
    if df is None and AK_OK and market in ["A_sh", "A_sz", "HK"] and period == "日线":
        try:
            if market in ["A_sh", "A_sz"]:
                df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date.replace("-", ""), end_date=end_date.replace("-", ""), adjust="qfq")
                col_map = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"}
                df.rename(columns=col_map, inplace=True)
            else: df = ak.stock_hk_daily(symbol=code, adjust="qfq")
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            df = df[["open", "high", "low", "close", "volume"]].dropna()
            msg = f"Data from Akshare ({period})"
        except Exception as e: msg = f"Akshare error: {str(e)[:50]}"
    
    # Yfinance for US stocks
    if df is None and YF_OK and market == "US":
        try:
            ticker = yf.Ticker(code)
            if period == "日线": df = ticker.history(period="1y")
            else: df = ticker.history(period="1mo", interval=yf_interval)
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.columns = ["open", "high", "low", "close", "volume"]
            msg = f"Data from Yahoo Finance ({period})"
        except Exception as e: msg = f"Yfinance error: {str(e)[:50]}"
    
    if df is None or len(df) < 10:
        df = demo(code)
        msg = "使用演示数据 - 真实数据获取失败"
        is_demo = True
    else: is_demo = False
    return df, msg, is_demo

# ============ Technical Indicators ============

def SMA(df, period=20): return df["close"].rolling(window=period).mean().iloc[-1]
def EMA(df, period=20): return df["close"].ewm(span=period, adjust=False).mean().iloc[-1]

def MACD(df, fast=12, slow=26, signal=9):
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]

def MACD_series(df, fast=12, slow=26, signal=9):
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def RSI(df, period=14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def RSI_series(df, period=14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def KDJ(df, n=9, m1=3, m2=3):
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n + 1e-10) * 100
    k = rsv.ewm(alpha=1/m1, adjust=False).mean()
    d = k.ewm(alpha=1/m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k.iloc[-1], d.iloc[-1], j.iloc[-1]

def BOLL(df, period=20, std_dev=2):
    middle = df["close"].rolling(window=period).mean()
    std = df["close"].rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper.iloc[-1], middle.iloc[-1], lower.iloc[-1]

def ATR(df, period=14):
    high, low, close = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
    return tr.rolling(window=period).mean().iloc[-1]

def FIB(df, lookback=50):
    recent = df.tail(lookback)
    high, low = recent["high"].max(), recent["low"].min()
    diff = high - low
    return {"0%": low, "23.6%": high - 0.236 * diff, "38.2%": high - 0.382 * diff,
            "50%": high - 0.5 * diff, "61.8%": high - 0.618 * diff, "100%": high}

def chan_fx(df):
    df = df.copy()
    df["fx_peak"], df["fx_trough"] = False, False
    for i in range(1, len(df) - 1):
        if df["high"].iloc[i] > df["high"].iloc[i-1] and df["high"].iloc[i] > df["high"].iloc[i+1]:
            df.loc[df.index[i], "fx_peak"] = True
        if df["low"].iloc[i] < df["low"].iloc[i-1] and df["low"].iloc[i] < df["low"].iloc[i+1]:
            df.loc[df.index[i], "fx_trough"] = True
    return df

def detect_bi(df):
    if "fx_peak" not in df.columns: df = chan_fx(df)
    bi_list, fractals = [], []
    for i in range(len(df)):
        if df["fx_peak"].iloc[i]: fractals.append({"idx": i, "date": df.index[i], "price": df["high"].iloc[i], "type": "peak"})
        elif df["fx_trough"].iloc[i]: fractals.append({"idx": i, "date": df.index[i], "price": df["low"].iloc[i], "type": "trough"})
    for i in range(len(fractals) - 1):
        curr, next_frac = fractals[i], fractals[i + 1]
        if curr["type"] != next_frac["type"] and next_frac["idx"] - curr["idx"] >= 4:
            bi_list.append({"start_date": curr["date"], "end_date": next_frac["date"],
                "start_price": curr["price"], "end_price": next_frac["price"],
                "start_idx": curr["idx"], "end_idx": next_frac["idx"], "type": f"{curr['type']}_to_{next_frac['type']}"})
    return bi_list

def detect_zhongshu(df, bi_list):
    zhongshu_list = []
    if len(bi_list) < 3: return zhongshu_list
    for i in range(len(bi_list) - 2):
        bi1, bi2, bi3 = bi_list[i], bi_list[i + 1], bi_list[i + 2]
        bi1_h, bi1_l = max(bi1["start_price"], bi1["end_price"]), min(bi1["start_price"], bi1["end_price"])
        bi2_h, bi2_l = max(bi2["start_price"], bi2["end_price"]), min(bi2["start_price"], bi2["end_price"])
        bi3_h, bi3_l = max(bi3["start_price"], bi3["end_price"]), min(bi3["start_price"], bi3["end_price"])
        overlap_h, overlap_l = min(bi1_h, bi2_h, bi3_h), max(bi1_l, bi2_l, bi3_l)
        if overlap_h > overlap_l:
            zhongshu_list.append({"start_date": bi1["start_date"], "end_date": bi3["end_date"],
                "zg": overlap_h, "zd": overlap_l, "bi_indices": [i, i + 1, i + 2]})
    return zhongshu_list

def detect_beichi(df):
    ema_fast = df["close"].ewm(span=12, adjust=False).mean()
    ema_slow = df["close"].ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    if len(histogram) < 20: return {"has_divergence": False, "details": "数据不足"}
    recent_hist = histogram.tail(20).values
    current_area, previous_area = np.sum(np.abs(recent_hist[-10:])), np.sum(np.abs(recent_hist[-20:-10]))
    return {"has_divergence": current_area < previous_area * 0.8, "current_area": float(current_area),
            "previous_area": float(previous_area), "ratio": float(current_area / (previous_area + 1e-10))}

def detect_chan_buy_sell_points(df, zhongshu_list):
    points = []
    if len(zhongshu_list) == 0 or len(df) < 30: return points
    zg, zd = zhongshu_list[-1]["zg"], zhongshu_list[-1]["zd"]
    beichi_info = detect_beichi(df)
    recent_prices = df["close"].tail(10).values
    current_price = recent_prices[-1]
    if current_price < zd and beichi_info["has_divergence"]: points.append({"type": "一买", "date": df.index[-1], "price": float(current_price), "signal": "BUY"})
    if len(recent_prices) >= 5 and recent_prices[-5] > zg and zd <= current_price <= zg: points.append({"type": "二买", "date": df.index[-1], "price": float(current_price), "signal": "BUY"})
    if len(recent_prices) >= 5 and recent_prices[-5] > zg and zd <= current_price <= zg and current_price >= zg * 0.98: points.append({"type": "三买", "date": df.index[-1], "price": float(current_price), "signal": "BUY"})
    if current_price > zg and beichi_info["has_divergence"]: points.append({"type": "一卖", "date": df.index[-1], "price": float(current_price), "signal": "SELL"})
    if len(recent_prices) >= 5 and recent_prices[-5] < zd and zd <= current_price <= zg: points.append({"type": "二卖", "date": df.index[-1], "price": float(current_price), "signal": "SELL"})
    if len(recent_prices) >= 5 and recent_prices[-5] < zd and zd <= current_price <= zg and current_price <= zd * 1.02: points.append({"type": "三卖", "date": df.index[-1], "price": float(current_price), "signal": "SELL"})
    return points

def detect_chan_signals(df, lookback=20):
    signals = []
    if "fx_peak" not in df.columns: df = chan_fx(df)
    recent = df.tail(lookback)
    for i in range(1, len(recent)):
        prev_close = df["close"].iloc[df.index.get_loc(recent.index[i]) - 1]
        curr_close = df["close"].iloc[df.index.get_loc(recent.index[i])]
        loc = df.index.get_loc(recent.index[i])
        for j in range(max(0, loc - lookback), loc):
            if df["fx_peak"].iloc[j] and prev_close <= df["high"].iloc[j] < curr_close:
                signals.append({"type": "BUY", "date": recent.index[i], "price": float(curr_close)}); break
        for j in range(max(0, loc - lookback), loc):
            if df["fx_trough"].iloc[j] and prev_close >= df["low"].iloc[j] > curr_close:
                signals.append({"type": "SELL", "date": recent.index[i], "price": float(curr_close)}); break
    signals.sort(key=lambda x: x["date"], reverse=True)
    return signals

def wyckoff(df):
    if len(df) < 50: return "数据不足"
    recent = df.tail(50)
    close = recent["close"].iloc[-1]
    avg_vol, recent_vol = recent["volume"].mean(), recent["volume"].iloc[-5:].mean()
    price_change = (recent["close"].iloc[-1] - recent["close"].iloc[0]) / recent["close"].iloc[0] * 100
    ma20, ma50 = SMA(recent, 20), SMA(df.tail(100) if len(df) >= 100 else df, min(50, len(df)))
    if close > ma20 > ma50 and price_change > 5: return "上涨趋势（做多）"
    elif close < ma20 < ma50 and price_change < -5: return "下跌趋势（做空）"
    elif recent_vol < avg_vol * 0.7 and abs(price_change) < 3: return "吸筹阶段（横盘整理）"
    elif recent_vol > avg_vol * 1.3 and abs(price_change) < 5: return "派发阶段（顶部构建）"
    return "过渡期（中性）"

def analyze(df):
    if df is None or len(df) < 30: return {"error": "Insufficient data"}
    df = chan_fx(df)
    sma20, sma50, ema20 = SMA(df, 20), SMA(df, 50), EMA(df, 20)
    macd_val, signal_val, hist_val = MACD(df)
    rsi_val = RSI(df, 14)
    k_val, d_val, j_val = KDJ(df)
    boll_upper, boll_mid, boll_lower = BOLL(df)
    atr_val = ATR(df, 14)
    fib_levels = FIB(df, 50)
    wyckoff_phase = wyckoff(df)
    close, high, low = df["close"].iloc[-1], df["high"].iloc[-1], df["low"].iloc[-1]
    score = 0
    if close > sma20: score += 15
    else: score -= 15
    if sma20 > sma50: score += 10
    else: score -= 10
    if macd_val > signal_val: score += 15
    else: score -= 15
    if hist_val > 0: score += 10
    else: score -= 10
    if rsi_val <= 30: score += 20
    elif rsi_val >= 70: score -= 20
    if j_val < 0: score += 15
    elif j_val > 100: score -= 15
    if close < boll_lower: score += 10
    elif close > boll_upper: score -= 10
    if score >= 40: signal = "STRONG BUY"
    elif score >= 20: signal = "BUY"
    elif score <= -40: signal = "STRONG SELL"
    elif score <= -20: signal = "SELL"
    else: signal = "HOLD"
    recent_high, recent_low = df["high"].tail(20).max(), df["low"].tail(20).min()
    return {"close": close, "high": high, "low": low, "sma20": sma20, "sma50": sma50, "ema20": ema20,
        "macd": macd_val, "macd_signal": signal_val, "macd_hist": hist_val, "rsi": rsi_val,
        "kdj_k": k_val, "kdj_d": d_val, "kdj_j": j_val, "boll_upper": boll_upper, "boll_mid": boll_mid, "boll_lower": boll_lower,
        "atr": atr_val, "fib_levels": fib_levels, "wyckoff_phase": wyckoff_phase, "score": score, "signal": signal,
        "support": recent_low, "resistance": recent_high, "target_up": close + atr_val * 2, "target_down": close - atr_val * 2,
        "atr_risk": atr_val, "df": df}

# ============ Decision Panel Functions ============

def get_action_display(signal):
    action_map = {"STRONG BUY": ("强烈买入", "#FF3333", "🔴🔴"), "BUY": ("买入", "#FF6666", "🔴"),
        "HOLD": ("持有", "#2962ff", "🔵"), "SELL": ("卖出", "#00AA00", "🟢"), "STRONG SELL": ("强烈卖出", "#00CC00", "🟢🟢")}
    return action_map.get(signal, ("观望", "#888888", "⚪"))

def get_position_suggestion(score):
    if score >= 50: return "满仓", 100, "#FF3333"
    elif score >= 30: return "八成仓", 80, "#FF6666"
    elif score >= 10: return "半仓", 50, "#ff6d00"
    elif score >= -10: return "三成仓", 30, "#2962ff"
    elif score >= -30: return "一成仓", 10, "#00AA00"
    else: return "空仓", 0, "#00CC00"

def calculate_key_levels(df, result, zhongshu_list):
    atr_val, close = result['atr'], result['close']
    recent_low = df["low"].tail(20).min()
    stop_loss = recent_low - atr_val
    fib = result['fib_levels']
    target1 = min(result['resistance'], fib.get("38.2%", close * 1.05))
    target2 = max(fib.get("61.8%", close * 1.10), close + (close - recent_low) * 1.618)
    return {"stop_loss": stop_loss, "target1": target1, "target2": target2}

def get_recent_signals(chan_points, all_signals, limit=3):
    recent = []
    if chan_points:
        for p in chan_points[:limit]: recent.append({"date": p["date"], "price": p["price"], "type": p["type"], "signal": p["signal"]})
    if len(recent) < limit and all_signals:
        for s in all_signals[:limit - len(recent)]: recent.append({"date": s["date"], "price": s["price"], "type": "买" if s["type"] == "BUY" else "卖", "signal": s["type"]})
    return recent[:limit]

# ============ Combined Chart with Sub-charts ============

def create_combined_chart(df, buy_signals=None, sell_signals=None, bi_list=None, zhongshu_list=None, chan_points=None):
    """Create combined chart with 4 rows: K-line(50%), MACD(15%), RSI(15%), Volume(20%)"""
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.02,
        row_heights=[0.50, 0.15, 0.15, 0.20], subplot_titles=("", "MACD", "RSI", "成交量"))
    
    sma20 = df["close"].rolling(window=20).mean()
    sma50 = df["close"].rolling(window=50).mean()
    boll_mid = df["close"].rolling(window=20).mean()
    boll_std = df["close"].rolling(window=20).std()
    boll_upper, boll_lower = boll_mid + 2 * boll_std, boll_mid - 2 * boll_std
    
    # Row 1: K-line
    fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="K线", increasing_line_color='#FF3333', decreasing_line_color='#00AA00',
        increasing_fillcolor='#FF3333', decreasing_fillcolor='#00AA00'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=sma20, name="MA20", line=dict(color='#2962ff', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=sma50, name="MA50", line=dict(color='#ff6d00', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=boll_upper, name="BOLL上轨", line=dict(color='#787b86', width=1, dash='dash'), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=boll_mid, name="BOLL中轨", line=dict(color='#787b86', width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=boll_lower, name="BOLL下轨", line=dict(color='#787b86', width=1, dash='dash'),
        fill='tonexty', fillcolor='rgba(120, 123, 134, 0.1)', showlegend=False), row=1, col=1)
    
    # Fractals
    peaks = df[df["fx_peak"] == True]
    troughs = df[df["fx_trough"] == True]
    if len(peaks) > 0:
        fig.add_trace(go.Scatter(x=peaks.index, y=peaks["high"] * 1.005, mode="markers", name="顶分型",
            marker=dict(symbol="triangle-down", size=10, color='#FF3333')), row=1, col=1)
    if len(troughs) > 0:
        fig.add_trace(go.Scatter(x=troughs.index, y=troughs["low"] * 0.995, mode="markers", name="底分型",
            marker=dict(symbol="triangle-up", size=10, color='#00AA00')), row=1, col=1)
    
    # Bi lines
    if bi_list is not None and len(bi_list) > 0:
        for i, bi in enumerate(bi_list[-15:]):
            fig.add_trace(go.Scatter(x=[bi["start_date"], bi["end_date"]], y=[bi["start_price"], bi["end_price"]],
                mode="lines", name="笔" if i == 0 else "", line=dict(color='#4488FF', width=1.5, dash='dot'), showlegend=(i == 0)), row=1, col=1)
    
    # Zhongshu
    if zhongshu_list is not None and len(zhongshu_list) > 0:
        for zs in zhongshu_list[-5:]:
            fig.add_shape(type="rect", x0=zs["start_date"], x1=zs["end_date"], y0=zs["zd"], y1=zs["zg"],
                fillcolor='rgba(255,200,0,0.15)', line=dict(color='rgba(255,200,0,0.6)', width=1), layer="below", row=1, col=1)
    
    # Buy/Sell signals
    if buy_signals is None: buy_signals = []
    if sell_signals is None: sell_signals = []
    if buy_signals:
        fig.add_trace(go.Scatter(x=[s["date"] for s in buy_signals], y=[s["price"] * 0.99 for s in buy_signals],
            mode="markers", name="买点", marker=dict(symbol="triangle-up", size=12, color='#00CC00')), row=1, col=1)
    if sell_signals:
        fig.add_trace(go.Scatter(x=[s["date"] for s in sell_signals], y=[s["price"] * 1.01 for s in sell_signals],
            mode="markers", name="卖点", marker=dict(symbol="triangle-down", size=12, color='#FF3333')), row=1, col=1)
    
    # Chan points
    if chan_points is not None and len(chan_points) > 0:
        buy_pts = [p for p in chan_points if p["signal"] == "BUY"]
        sell_pts = [p for p in chan_points if p["signal"] == "SELL"]
        if buy_pts:
            for i, bp in enumerate(buy_pts):
                fig.add_trace(go.Scatter(x=[bp["date"]], y=[bp["price"] * 0.985], mode="markers+text", name="缠论买点" if i == 0 else "",
                    marker=dict(symbol="triangle-up", size=18 if bp["type"] == "一买" else 15, color='#00CC00'),
                    text=[bp["type"]], textposition="bottom center", textfont=dict(size=10, color='#00FF00'), showlegend=(i == 0)), row=1, col=1)
        if sell_pts:
            for i, sp in enumerate(sell_pts):
                fig.add_trace(go.Scatter(x=[sp["date"]], y=[sp["price"] * 1.015], mode="markers+text", name="缠论卖点" if i == 0 else "",
                    marker=dict(symbol="triangle-down", size=18 if sp["type"] == "一卖" else 15, color='#FF3333'),
                    text=[sp["type"]], textposition="top center", textfont=dict(size=10, color='#FF6666'), showlegend=(i == 0)), row=1, col=1)
    
    # Row 2: MACD with annotations
    macd_line, signal_line, histogram = MACD_series(df)
    hist_colors = ['#FF3333' if h >= 0 else '#00AA00' for h in histogram]
    fig.add_trace(go.Bar(x=df.index, y=histogram, name="MACD柱", marker_color=hist_colors, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=macd_line, name="MACD", line=dict(color='#2962ff', width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=signal_line, name="信号线", line=dict(color='#ff6d00', width=1.5)), row=2, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color='#2a2e39', opacity=0.5, row=2, col=1)
    
    # MACD Cross annotations (金叉/死叉)
    cross_annotations = []
    for i in range(1, len(df)):
        prev_diff = macd_line.iloc[i-1] - signal_line.iloc[i-1]
        curr_diff = macd_line.iloc[i] - signal_line.iloc[i]
        if prev_diff <= 0 and curr_diff > 0:  # 金叉
            cross_annotations.append(dict(x=df.index[i], y=macd_line.iloc[i], text="金叉▲", showarrow=False,
                font=dict(color='#FF3333', size=10), xref='x2', yref='y2'))
        elif prev_diff >= 0 and curr_diff < 0:  # 死叉
            cross_annotations.append(dict(x=df.index[i], y=macd_line.iloc[i], text="死叉▼", showarrow=False,
                font=dict(color='#00AA00', size=10), xref='x2', yref='y2'))
    
    # Row 3: RSI
    rsi_vals = RSI_series(df)
    fig.add_trace(go.Scatter(x=df.index, y=rsi_vals, name="RSI", line=dict(color='#7c4dff', width=1.5),
        fill='tozeroy', fillcolor='rgba(124, 77, 255, 0.1)'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color='#00AA00', opacity=0.7, row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color='#FF3333', opacity=0.7, row=3, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color='#2a2e39', opacity=0.5, row=3, col=1)
    
    # Row 4: Volume
    vol_colors = ['#FF3333' if df["close"].iloc[i] >= df["open"].iloc[i] else '#00AA00' for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="成交量", marker_color=vol_colors, showlegend=False), row=4, col=1)
    
    # Layout
    fig.update_layout(template="plotly_dark", paper_bgcolor='#131722', plot_bgcolor='#131722',
        height=800, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
        margin=dict(l=50, r=50, t=30, b=30), xaxis_rangeslider_visible=False, annotations=cross_annotations)
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#1e222d', linecolor='#2a2e39')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#1e222d', linecolor='#2a2e39')
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(showticklabels=False, row=3, col=1)
    fig.update_xaxes(showticklabels=True, row=4, col=1)
    fig.update_yaxes(range=[0, 100], row=3, col=1)
    return fig

# ============ Main Streamlit UI ============

def main():
    # Initialize session state for watchlist
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = DEFAULT_WATCHLIST.copy()
    
    # Sidebar - Watchlist at TOP
    st.sidebar.title("🐉 DragonX Pro")
    st.sidebar.write("---")
    
    # ============ Feature 5: Watchlist ============
    st.sidebar.subheader("📋 自选股列表")
    
    # Watchlist display as selectbox
    watchlist_options = [f"{code} - {name}" for code, name in st.session_state.watchlist]
    selected_idx = st.sidebar.selectbox("选择股票", range(len(watchlist_options)), format_func=lambda i: watchlist_options[i], index=0)
    
    selected_code, selected_name = st.session_state.watchlist[selected_idx]
    
    # Custom stock input
    st.sidebar.write("---")
    st.sidebar.subheader("➕ 添加自选股")
    new_code = st.sidebar.text_input("股票代码", value="", key="new_stock_code", placeholder="如: 600036")
    if st.sidebar.button("添加到自选股", key="add_watchlist_btn"):
        if new_code and new_code not in [c for c, n in st.session_state.watchlist]:
            new_name = stock_name(new_code) if mkt(new_code) in ["A_sh", "A_sz"] else new_code
            st.session_state.watchlist.append((new_code, new_name))
            st.sidebar.success(f"已添加: {new_code}")
            st.rerun()
    
    # Remove from watchlist
    if st.sidebar.button("移除当前股票", key="remove_watchlist_btn"):
        if len(st.session_state.watchlist) > 1:
            st.session_state.watchlist.pop(selected_idx)
            st.rerun()
    
    st.sidebar.write("---")
    
    # Data source status
    with st.sidebar.expander("📊 数据源状态"):
        st.write(f"AkShare: {'✅' if AK_OK else '❌'}")
        st.write(f"Baostock: {'✅' if BS_OK else '❌'}")
        st.write(f"YFinance: {'✅' if YF_OK else '❌'}")
    
    st.sidebar.write("---")
    
    # Period selector
    st.sidebar.subheader("⏱️ 周期选择")
    period = st.sidebar.selectbox("K线周期", ["日线", "60分钟", "30分钟", "15分钟", "5分钟"], index=0)
    
    st.sidebar.write("---")
    st.sidebar.caption("DragonX Pro v3.0 | 缠论分析")
    
    # Main area
    st.title(f"📈 DragonX 量化分析看板 - {selected_name}")
    
    # Fetch data
    with st.spinner("正在获取数据..."):
        df, fetch_msg, is_demo = fetch(selected_code, period)
    
    if is_demo:
        st.error("⚠️ 演示数据 - 真实数据获取失败")
        st.warning("以下价格为随机生成，请勿用于交易")
    else:
        st.info(f"📡 数据来源：{fetch_msg} | 市场：{mkt(selected_code)}")
    
    if df is None or len(df) < 10:
        st.error("获取数据失败，请检查股票代码")
        return
    
    name = stock_name(selected_code) if mkt(selected_code) in ["A_sh", "A_sz"] else selected_code
    if is_demo: name = f"{name} (演示)"
    
    # Run analysis
    result = analyze(df)
    if "error" in result:
        st.error(result["error"])
        return
    df = result["df"]
    
    # Chan theory signals
    all_signals = detect_chan_signals(df, lookback=20)
    buy_signals = [s for s in all_signals if s["type"] == "BUY"]
    sell_signals = [s for s in all_signals if s["type"] == "SELL"]
    bi_list = detect_bi(df)
    zhongshu_list = detect_zhongshu(df, bi_list)
    chan_points = detect_chan_buy_sell_points(df, zhongshu_list)
    beichi_info = detect_beichi(df)
    
    # ============ Layout: Main Chart | Decision Panel ============
    col_chart, col_decision = st.columns([3, 1])
    
    with col_chart:
        st.subheader("📊 专业K线图 (含技术指标副图)")
        fig_main = create_combined_chart(df, buy_signals, sell_signals, bi_list, zhongshu_list, chan_points)
        st.plotly_chart(fig_main, use_container_width=True)
    
    # ============ Feature 3: Right-side Decision Panel ============
    with col_decision:
        st.subheader("🎯 决策面板")
        st.write("---")
        
        # Current Action
        action_text, action_color, action_icon = get_action_display(result["signal"])
        st.markdown(f"### 当前操作建议")
        st.markdown(f"<h2 style='color:{action_color};'>{action_icon} {action_text}</h2>", unsafe_allow_html=True)
        
        st.write("---")
        
        # Suggested Position
        pos_text, pos_pct, pos_color = get_position_suggestion(result["score"])
        st.markdown(f"### 建议仓位")
        st.markdown(f"<h3 style='color:{pos_color};'>{pos_text} ({pos_pct}%)</h3>", unsafe_allow_html=True)
        st.progress(pos_pct / 100)
        st.metric("信号评分", result["score"])
        
        st.write("---")
        
        # Key Price Levels
        key_levels = calculate_key_levels(df, result, zhongshu_list)
        st.markdown(f"### 关键价位")
        st.metric("止损位", f"{key_levels['stop_loss']:.2f}", delta=f"{((key_levels['stop_loss']/result['close'])-1)*100:.1f}%")
        st.metric("第一目标", f"{key_levels['target1']:.2f}", delta=f"{((key_levels['target1']/result['close'])-1)*100:.1f}%")
        st.metric("第二目标", f"{key_levels['target2']:.2f}", delta=f"{((key_levels['target2']/result['close'])-1)*100:.1f}%")
        
        st.write("---")
        
        # Recent Signals
        recent_sigs = get_recent_signals(chan_points, all_signals, limit=3)
        st.markdown(f"### 最近买卖点")
        if recent_sigs:
            for sig in recent_sigs:
                sig_color = "#FF3333" if sig["signal"] == "BUY" else "#00AA00"
                sig_date = sig["date"].strftime("%m-%d") if hasattr(sig["date"], "strftime") else str(sig["date"])[:10]
                st.markdown(f"<span style='color:{sig_color};'>● {sig['type']}</span> | {sig_date} | {sig['price']:.2f}", unsafe_allow_html=True)
        else:
            st.info("暂无信号")
    
    st.write("---")
    
    # Price data summary
    st.subheader("📈 价格数据")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("最新价", f"{result['close']:.2f}")
    with col2: st.metric("最高价", f"{result['high']:.2f}")
    with col3: st.metric("最低价", f"{result['low']:.2f}")
    with col4: st.metric("支撑位", f"{result['support']:.2f}")
    with col5: st.metric("阻力位", f"{result['resistance']:.2f}")
    
    st.write("---")
    
    # Technical Indicators
    st.subheader("📊 技术指标")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("RSI", f"{result['rsi']:.1f}")
        if result['rsi'] < 30: st.success("超卖")
        elif result['rsi'] > 70: st.warning("超买")
    with col2:
        st.metric("MACD", f"{result['macd']:.3f}")
        st.metric("信号线", f"{result['macd_signal']:.3f}")
    with col3:
        st.metric("K", f"{result['kdj_k']:.1f}")
        st.metric("D", f"{result['kdj_d']:.1f}")
        st.metric("J", f"{result['kdj_j']:.1f}")
    with col4:
        st.metric("ATR", f"{result['atr']:.3f}")
        st.metric("布林上轨", f"{result['boll_upper']:.2f}")
        st.metric("布林下轨", f"{result['boll_lower']:.2f}")
    
    st.write("---")
    
    # Chan Theory Analysis
    st.subheader("🔮 缠论分析")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if len(zhongshu_list) > 0: st.metric("中枢上界 (ZG)", f"{zhongshu_list[-1]['zg']:.2f}")
        else: st.metric("中枢上界 (ZG)", "N/A")
    with col2:
        if len(zhongshu_list) > 0: st.metric("中枢下界 (ZD)", f"{zhongshu_list[-1]['zd']:.2f}")
        else: st.metric("中枢下界 (ZD)", "N/A")
    with col3: st.metric("笔数量", len(bi_list) if len(bi_list) > 0 else 0)
    with col4: st.metric("中枢数量", len(zhongshu_list) if len(zhongshu_list) > 0 else 0)
    
    # Price position
    st.write("**当前价格位置：**")
    if len(zhongshu_list) > 0:
        zg, zd = zhongshu_list[-1]["zg"], zhongshu_list[-1]["zd"]
        price = result['close']
        if price > zg: st.success(f"✅ 价格 {price:.2f} 在中枢上方 (ZG: {zg:.2f})")
        elif price < zd: st.error(f"❌ 价格 {price:.2f} 在中枢下方 (ZD: {zd:.2f})")
        else: st.info(f"➡️ 价格 {price:.2f} 在中枢内部 (ZD: {zd:.2f} - ZG: {zg:.2f})")
    else: st.warning("中枢数据不足")
    
    # Divergence
    st.write("**背驰状态：**")
    if beichi_info["has_divergence"]: st.warning(f"⚠️ 检测到背驰信号 (比率: {beichi_info['ratio']:.2f})")
    else: st.info(f"✅ 无背驰信号 (比率: {beichi_info['ratio']:.2f})")
    
    st.write("---")
    
    # Signal summary
    st.subheader("📡 买卖信号")
    col_b, col_s = st.columns(2)
    with col_b:
        st.success(f"**买入信号（近20根K线）：** {len(buy_signals)}")
        for s in buy_signals[:5]: st.write(f"  {s['date'].strftime('%Y-%m-%d')} - {s['price']:.2f}")
    with col_s:
        st.error(f"**卖出信号（近20根K线）：** {len(sell_signals)}")
        for s in sell_signals[:5]: st.write(f"  {s['date'].strftime('%Y-%m-%d')} - {s['price']:.2f}")
    
    st.write("---")
    
    # Wyckoff phase
    st.subheader("📊 市场阶段")
    st.write(f"**威科夫阶段：** {result['wyckoff_phase']}")
    
    # Fibonacci
    st.subheader("📐 斐波那契回撤位")
    fib_cols = st.columns(len(result['fib_levels']))
    for i, (level, value) in enumerate(result['fib_levels'].items()):
        with fib_cols[i]: st.metric(level, f"{value:.2f}")
    
    st.write("---")
    
    if is_demo: st.error("⚠️ 免责声明：以上数据均为演示数据，请勿据此做出交易决策。")
    else: st.caption("DragonX 量化分析系统 | 数据可能有延迟 | 仅供学习参考，不构成投资建议")

if __name__ == "__main__":
    main()