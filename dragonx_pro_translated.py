# -*- coding: utf-8 -*-
"""DragonX Pro - Professional-Grade Multi-Market Technical Analysis Streamlit App
Professional K-line charts with Plotly featuring TradingView-style dark theme.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
import re
from datetime import datetime, timedelta
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

# ============ TradingView-Style Dark Theme ============
TV_THEME = {
    'bg_color': '#131722',
    'grid_color': '#1e222d',
    'text_color': '#d1d4dc',
    'border_color': '#2a2e39',
    'up_color': '#26a69a',
    'down_color': '#ef5350',
    'sma20_color': '#2962ff',
    'sma50_color': '#ff6d00',
    'boll_color': '#787b86',
    'volume_up': 'rgba(38, 166, 154, 0.5)',
    'volume_down': 'rgba(239, 83, 80, 0.5)',
    'macd_color': '#2962ff',
    'signal_color': '#ff6d00',
    'rsi_color': '#7c4dff',
    'k_color': '#2962ff',
    'd_color': '#ff6d00',
    'j_color': '#e040fb',
}

# ============ Helper Functions ============

def mkt(code):
    """Determine market type based on stock code pattern."""
    code = str(code).upper().strip()
    if re.match(r"^(600|601|603|605|688)", code):
        return "A_sh"
    if re.match(r"^(000|001|002|003|300)", code):
        return "A_sz"
    if re.match(r"^[0-9]{4,5}$", code):
        return "HK"
    if re.match(r"^[A-Z]+$", code):
        return "US"
    return "Unknown"


def stock_name(code):
    """Get A-share stock name via baostock."""
    if not BS_OK:
        return code
    try:
        bs.login()
        market = "sh" if mkt(code) == "A_sh" else "sz"
        full_code = f"{market}.{code}"
        rs = bs.query_stock_info(code=full_code)
        data_list = []
        while (rs.error_code == "0") and rs.next():
            data_list.append(rs.get_row_data())
        if data_list and len(data_list[0]) > 1 and data_list[0][1]:
            return data_list[0][1]
    except Exception:
        pass
    finally:
        try:
            bs.logout()
        except:
            pass
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
    df = pd.DataFrame({
        "date": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    })
    df.set_index("date", inplace=True)
    df["_demo"] = True
    return df


def fetch(code):
    """Fetch stock data from multiple sources."""
    market = mkt(code)
    msg = ""
    df = None
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    
    # Baostock for A-shares (primary)
    if market in ["A_sh", "A_sz"] and BS_OK:
        try:
            bs.login()
            bs_market = "sh" if market == "A_sh" else "sz"
            rs = bs.query_history_k_data_plus(
                f"{bs_market}.{code}",
                "date,open,high,low,close,volume",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3"
            )
            data_list = []
            while (rs.error_code == "0") and rs.next():
                data_list.append(rs.get_row_data())
            if data_list:
                df = pd.DataFrame(data_list, columns=rs.fields)
                col_map = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"}
                df = df.rename(columns=col_map)
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df["date"] = pd.to_datetime(df["date"])
                df.set_index("date", inplace=True)
                msg = "Data from Baostock"
            bs.logout()
        except Exception as e:
            msg = f"Baostock error: {str(e)[:50]}"
    
    # Akshare as secondary for A-shares and HK
    if df is None and AK_OK and market in ["A_sh", "A_sz", "HK"]:
        try:
            if market in ["A_sh", "A_sz"]:
                df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date.replace("-", ""), end_date=end_date.replace("-", ""), adjust="qfq")
                col_map = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"}
                df.rename(columns=col_map, inplace=True)
            else:
                df = ak.stock_hk_daily(symbol=code, adjust="qfq")
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            df = df[["open", "high", "low", "close", "volume"]].dropna()
            msg = "Data from Akshare"
        except Exception as e:
            msg = f"Akshare error: {str(e)[:50]}"
    
    # Yfinance for US stocks
    if df is None and YF_OK and market == "US":
        try:
            ticker = yf.Ticker(code)
            df = ticker.history(period="1y")
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.columns = ["open", "high", "low", "close", "volume"]
            msg = "Data from Yahoo Finance"
        except Exception as e:
            msg = f"Yfinance error: {str(e)[:50]}"
    
    # Demo fallback
    if df is None or len(df) < 10:
        df = demo(code)
        msg = "使用演示数据 - 真实数据获取失败"
        is_demo = True
    else:
        is_demo = False
    
    return df, msg, is_demo


# ============ Technical Indicators ============

def SMA(df, period=20):
    """Simple Moving Average."""
    return df["close"].rolling(window=period).mean().iloc[-1]


def EMA(df, period=20):
    """Exponential Moving Average."""
    return df["close"].ewm(span=period, adjust=False).mean().iloc[-1]


def MACD(df, fast=12, slow=26, signal=9):
    """MACD indicator - returns (macd, signal, histogram)."""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]


def RSI(df, period=14):
    """Relative Strength Index."""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]


def KDJ(df, n=9, m1=3, m2=3):
    """KDJ stochastic indicator."""
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n + 1e-10) * 100
    k = rsv.ewm(alpha=1/m1, adjust=False).mean()
    d = k.ewm(alpha=1/m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k.iloc[-1], d.iloc[-1], j.iloc[-1]


def BOLL(df, period=20, std_dev=2):
    """Bollinger Bands - returns (upper, middle, lower)."""
    middle = df["close"].rolling(window=period).mean()
    std = df["close"].rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper.iloc[-1], middle.iloc[-1], lower.iloc[-1]


def ATR(df, period=14):
    """Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1]


def FIB(df, lookback=50):
    """Fibonacci retracement levels."""
    recent = df.tail(lookback)
    high = recent["high"].max()
    low = recent["low"].min()
    diff = high - low
    levels = {
        "0%": low,
        "23.6%": high - 0.236 * diff,
        "38.2%": high - 0.382 * diff,
        "50%": high - 0.5 * diff,
        "61.8%": high - 0.618 * diff,
        "100%": high
    }
    return levels


def chan_fx(df):
    """Mark fractal peaks and troughs (Chan theory)."""
    df = df.copy()
    df["fx_peak"] = False
    df["fx_trough"] = False
    
    for i in range(1, len(df) - 1):
        if df["high"].iloc[i] > df["high"].iloc[i-1] and df["high"].iloc[i] > df["high"].iloc[i+1]:
            df.loc[df.index[i], "fx_peak"] = True
        if df["low"].iloc[i] < df["low"].iloc[i-1] and df["low"].iloc[i] < df["low"].iloc[i+1]:
            df.loc[df.index[i], "fx_trough"] = True
    
    return df


def detect_chan_signals(df, lookback=20):
    """
    Detect Chan theory buy/sell signals from fractal breaks.
    """
    signals = []
    if "fx_peak" not in df.columns:
        df = chan_fx(df)
    
    recent = df.tail(lookback)
    
    for i in range(1, len(recent)):
        prev_close = df["close"].iloc[df.index.get_loc(recent.index[i]) - 1]
        curr_close = df["close"].iloc[df.index.get_loc(recent.index[i])]
        
        loc = df.index.get_loc(recent.index[i])
        for j in range(max(0, loc - lookback), loc):
            if df["fx_peak"].iloc[j]:
                peak_high = df["high"].iloc[j]
                if prev_close <= peak_high < curr_close:
                    signals.append({
                        "type": "BUY",
                        "date": recent.index[i],
                        "price": float(curr_close)
                    })
                    break
        
        for j in range(max(0, loc - lookback), loc):
            if df["fx_trough"].iloc[j]:
                trough_low = df["low"].iloc[j]
                if prev_close >= trough_low > curr_close:
                    signals.append({
                        "type": "SELL",
                        "date": recent.index[i],
                        "price": float(curr_close)
                    })
                    break
    
    signals.sort(key=lambda x: x["date"], reverse=True)
    return signals


def wyckoff(df):
    """Detect Wyckoff market phase."""
    if len(df) < 50:
        return "数据不足"
    
    recent = df.tail(50)
    close = recent["close"].iloc[-1]
    avg_vol = recent["volume"].mean()
    recent_vol = recent["volume"].iloc[-5:].mean()
    
    price_change = (recent["close"].iloc[-1] - recent["close"].iloc[0]) / recent["close"].iloc[0] * 100
    
    ma20 = SMA(recent, 20)
    ma50_period = min(50, len(df))
    ma50 = SMA(df.tail(100) if len(df) >= 100 else df, ma50_period)
    
    if close > ma20 > ma50 and price_change > 5:
        phase = "上涨趋势（做多）"
    elif close < ma20 < ma50 and price_change < -5:
        phase = "下跌趋势（做空）"
    elif recent_vol < avg_vol * 0.7 and abs(price_change) < 3:
        phase = "吸筹阶段（横盘整理）"
    elif recent_vol > avg_vol * 1.3 and abs(price_change) < 5:
        phase = "派发阶段（顶部构建）"
    else:
        phase = "过渡期（中性）"
    
    return phase


def analyze(df):
    """Comprehensive technical analysis."""
    if df is None or len(df) < 30:
        return {"error": "Insufficient data"}
    
    df = chan_fx(df)
    
    sma20 = SMA(df, 20)
    sma50 = SMA(df, 50)
    ema20 = EMA(df, 20)
    macd_val, signal_val, hist_val = MACD(df)
    rsi_val = RSI(df, 14)
    k_val, d_val, j_val = KDJ(df)
    boll_upper, boll_mid, boll_lower = BOLL(df)
    atr_val = ATR(df, 14)
    fib_levels = FIB(df, 50)
    wyckoff_phase = wyckoff(df)
    
    close = df["close"].iloc[-1]
    high = df["high"].iloc[-1]
    low = df["low"].iloc[-1]
    
    # Composite score calculation
    score = 0
    
    if close > sma20:
        score += 15
    else:
        score -= 15
    
    if sma20 > sma50:
        score += 10
    else:
        score -= 10
    
    if macd_val > signal_val:
        score += 15
    else:
        score -= 15
    
    if hist_val > 0:
        score += 10
    else:
        score -= 10
    
    if 30 < rsi_val < 70:
        score += 0
    elif rsi_val <= 30:
        score += 20
    elif rsi_val >= 70:
        score -= 20
    
    if j_val < 0:
        score += 15
    elif j_val > 100:
        score -= 15
    
    if close < boll_lower:
        score += 10
    elif close > boll_upper:
        score -= 10
    
    if score >= 40:
        signal = "STRONG BUY"
    elif score >= 20:
        signal = "BUY"
    elif score <= -40:
        signal = "STRONG SELL"
    elif score <= -20:
        signal = "SELL"
    else:
        signal = "HOLD"
    
    recent_high = df["high"].tail(20).max()
    recent_low = df["low"].tail(20).min()
    
    target_up = close + atr_val * 2
    target_down = close - atr_val * 2
    
    return {
        "close": close,
        "high": high,
        "low": low,
        "sma20": sma20,
        "sma50": sma50,
        "ema20": ema20,
        "macd": macd_val,
        "macd_signal": signal_val,
        "macd_hist": hist_val,
        "rsi": rsi_val,
        "kdj_k": k_val,
        "kdj_d": d_val,
        "kdj_j": j_val,
        "boll_upper": boll_upper,
        "boll_mid": boll_mid,
        "boll_lower": boll_lower,
        "atr": atr_val,
        "fib_levels": fib_levels,
        "wyckoff_phase": wyckoff_phase,
        "score": score,
        "signal": signal,
        "support": recent_low,
        "resistance": recent_high,
        "target_up": target_up,
        "target_down": target_down,
        "atr_risk": atr_val,
        "df": df
    }


# ============ Professional Chart Functions ============

def create_main_kline_chart(df, buy_signals=None, sell_signals=None):
    """Create professional K-line chart with volume at bottom."""
    # Create figure with 2 rows: main chart + volume
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
        subplot_titles=("", "")
    )
    
    # Calculate indicators
    sma20 = df["close"].rolling(window=20).mean()
    sma50 = df["close"].rolling(window=50).mean()
    boll_mid = df["close"].rolling(window=20).mean()
    boll_std = df["close"].rolling(window=20).std()
    boll_upper = boll_mid + 2 * boll_std
    boll_lower = boll_mid - 2 * boll_std
    
    # 1. Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
            increasing_line_color=TV_THEME['up_color'],
            decreasing_line_color=TV_THEME['down_color'],
            increasing_fillcolor=TV_THEME['up_color'],
            decreasing_fillcolor=TV_THEME['down_color']
        ),
        row=1, col=1
    )
    
    # 2. SMA20
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=sma20,
            name="均线20",
            line=dict(color=TV_THEME['sma20_color'], width=1.5),
            hovertemplate='均线20: %{y:.2f}<extra></extra>'
        ),
        row=1, col=1
    )
    
    # 3. SMA50
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=sma50,
            name="均线50",
            line=dict(color=TV_THEME['sma50_color'], width=1.5),
            hovertemplate='均线50: %{y:.2f}<extra></extra>'
        ),
        row=1, col=1
    )
    
    # 4. Bollinger Bands
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=boll_upper,
            name="布林上轨",
            line=dict(color=TV_THEME['boll_color'], width=1, dash='dash'),
            hoverinfo='skip'
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=boll_mid,
            name="布林中轨",
            line=dict(color=TV_THEME['boll_color'], width=1),
            hovertemplate='布林中轨: %{y:.2f}<extra></extra>'
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=boll_lower,
            name="布林下轨",
            line=dict(color=TV_THEME['boll_color'], width=1, dash='dash'),
            fill='tonexty',
            fillcolor='rgba(120, 123, 134, 0.1)',
            hoverinfo='skip'
        ),
        row=1, col=1
    )
    
    # 5. Fractal markers
    peaks = df[df["fx_peak"] == True]
    troughs = df[df["fx_trough"] == True]
    
    if len(peaks) > 0:
        fig.add_trace(
            go.Scatter(
                x=peaks.index,
                y=peaks["high"] * 1.005,
                mode="markers",
                name="顶分型",
                marker=dict(symbol="triangle-down", size=10, color="#ff9800"),
                hovertemplate='顶分型: %{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    if len(troughs) > 0:
        fig.add_trace(
            go.Scatter(
                x=troughs.index,
                y=troughs["low"] * 0.995,
                mode="markers",
                name="底分型",
                marker=dict(symbol="triangle-up", size=10, color="#4caf50"),
                hovertemplate='底分型: %{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    # 6. Buy/Sell signals
    if buy_signals is None:
        buy_signals = []
    if sell_signals is None:
        sell_signals = []
    
    if buy_signals:
        buy_dates = [s["date"] for s in buy_signals]
        buy_prices = [s["price"] * 0.995 for s in buy_signals]
        fig.add_trace(
            go.Scatter(
                x=buy_dates,
                y=buy_prices,
                mode="markers",
                name="买点",
                marker=dict(symbol="triangle-up", size=15, color="#00e676", line=dict(width=2, color="#1b5e20")),
                hovertemplate='买点<br>日期: %{x|%Y-%m-%d}<br>价格: %{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    if sell_signals:
        sell_dates = [s["date"] for s in sell_signals]
        sell_prices = [s["price"] * 1.005 for s in sell_signals]
        fig.add_trace(
            go.Scatter(
                x=sell_dates,
                y=sell_prices,
                mode="markers",
                name="卖点",
                marker=dict(symbol="triangle-down", size=15, color="#ff1744", line=dict(width=2, color="#b71c1c")),
                hovertemplate='卖点<br>日期: %{x|%Y-%m-%d}<br>价格: %{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    # 7. Volume bars
    vol_colors = [TV_THEME['volume_up'] if df["close"].iloc[i] >= df["open"].iloc[i] 
                  else TV_THEME['volume_down'] for i in range(len(df))]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["volume"],
            name="成交量",
            marker_color=vol_colors,
            hovertemplate='成交量: %{y:,.0f}<extra></extra>'
        ),
        row=2, col=1
    )
    
    # Update layout
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=TV_THEME['bg_color'],
        plot_bgcolor=TV_THEME['bg_color'],
        height=600,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=10)
        ),
        margin=dict(l=50, r=50, t=30, b=30),
        xaxis_rangeslider_visible=False
    )
    
    # Update axes
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor=TV_THEME['grid_color'],
        linecolor=TV_THEME['border_color'],
        linewidth=1
    )
    fig.update_yaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor=TV_THEME['grid_color'],
        linecolor=TV_THEME['border_color'],
        linewidth=1
    )
    
    # Hide volume x-axis labels (shared with main)
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=True, row=2, col=1)
    
    return fig


def create_macd_chart(df):
    """Create MACD chart with histogram."""
    ema_fast = df["close"].ewm(span=12, adjust=False).mean()
    ema_slow = df["close"].ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    
    fig = go.Figure()
    
    # Histogram
    hist_colors = [TV_THEME['up_color'] if h >= 0 else TV_THEME['down_color'] for h in histogram]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=histogram,
            name="柱状图",
            marker_color=hist_colors,
            hovertemplate='柱状图: %{y:.4f}<extra></extra>'
        )
    )
    
    # MACD line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=macd_line,
            name="MACD",
            line=dict(color=TV_THEME['macd_color'], width=1.5),
            hovertemplate='MACD: %{y:.4f}<extra></extra>'
        )
    )
    
    # Signal line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=signal_line,
            name="信号线",
            line=dict(color=TV_THEME['signal_color'], width=1.5),
            hovertemplate='信号线: %{y:.4f}<extra></extra>'
        )
    )
    
    # Zero line
    fig.add_hline(y=0, line_dash="dot", line_color=TV_THEME['border_color'], opacity=0.5)
    
    fig.update_layout(
        title=dict(text="MACD", font=dict(size=12, color=TV_THEME['text_color'])),
        template="plotly_dark",
        paper_bgcolor=TV_THEME['bg_color'],
        plot_bgcolor=TV_THEME['bg_color'],
        height=250,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=9)),
        margin=dict(l=40, r=40, t=40, b=20),
        xaxis_rangeslider_visible=False
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor=TV_THEME['grid_color'])
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor=TV_THEME['grid_color'])
    
    return fig


def create_rsi_chart(df):
    """Create RSI chart with reference lines."""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi_vals = 100 - (100 / (1 + rs))
    
    fig = go.Figure()
    
    # RSI line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=rsi_vals,
            name="RSI",
            line=dict(color=TV_THEME['rsi_color'], width=1.5),
            fill='tozeroy',
            fillcolor='rgba(124, 77, 255, 0.1)',
            hovertemplate='RSI: %{y:.1f}<extra></extra>'
        )
    )
    
    # Reference lines
    fig.add_hline(y=70, line_dash="dash", line_color=TV_THEME['down_color'], opacity=0.7,
                  annotation_text="70", annotation_position="right", annotation_font_size=10)
    fig.add_hline(y=30, line_dash="dash", line_color=TV_THEME['up_color'], opacity=0.7,
                  annotation_text="30", annotation_position="right", annotation_font_size=10)
    fig.add_hline(y=50, line_dash="dot", line_color=TV_THEME['border_color'], opacity=0.5)
    
    fig.update_layout(
        title=dict(text="RSI (14)", font=dict(size=12, color=TV_THEME['text_color'])),
        template="plotly_dark",
        paper_bgcolor=TV_THEME['bg_color'],
        plot_bgcolor=TV_THEME['bg_color'],
        height=250,
        showlegend=False,
        margin=dict(l=40, r=40, t=40, b=20),
        yaxis_range=[0, 100],
        xaxis_rangeslider_visible=False
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor=TV_THEME['grid_color'])
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor=TV_THEME['grid_color'])
    
    return fig


def create_kdj_chart(df):
    """Create KDJ chart."""
    low_n = df["low"].rolling(window=9).min()
    high_n = df["high"].rolling(window=9).max()
    rsv = (df["close"] - low_n) / (high_n - low_n + 1e-10) * 100
    k_vals = rsv.ewm(alpha=1/3, adjust=False).mean()
    d_vals = k_vals.ewm(alpha=1/3, adjust=False).mean()
    j_vals = 3 * k_vals - 2 * d_vals
    
    fig = go.Figure()
    
    # K line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=k_vals,
            name="K",
            line=dict(color=TV_THEME['k_color'], width=1.5),
            hovertemplate='K: %{y:.1f}<extra></extra>'
        )
    )
    
    # D line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=d_vals,
            name="D",
            line=dict(color=TV_THEME['d_color'], width=1.5),
            hovertemplate='D: %{y:.1f}<extra></extra>'
        )
    )
    
    # J line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=j_vals,
            name="J",
            line=dict(color=TV_THEME['j_color'], width=1),
            hovertemplate='J: %{y:.1f}<extra></extra>'
        )
    )
    
    # Reference lines
    fig.add_hline(y=80, line_dash="dash", line_color=TV_THEME['down_color'], opacity=0.5)
    fig.add_hline(y=20, line_dash="dash", line_color=TV_THEME['up_color'], opacity=0.5)
    
    fig.update_layout(
        title=dict(text="KDJ", font=dict(size=12, color=TV_THEME['text_color'])),
        template="plotly_dark",
        paper_bgcolor=TV_THEME['bg_color'],
        plot_bgcolor=TV_THEME['bg_color'],
        height=250,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=9)),
        margin=dict(l=40, r=40, t=40, b=20),
        xaxis_rangeslider_visible=False
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor=TV_THEME['grid_color'])
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor=TV_THEME['grid_color'])
    
    return fig


# ============ Main Streamlit UI ============

def main():
    # Sidebar
    st.sidebar.title("DragonX 控制面板")
    st.sidebar.write("---")
    
    # Data source status
    st.sidebar.subheader("数据源状态")
    st.sidebar.write(f"AkShare: {'✓' if AK_OK else '✗'}")
    st.sidebar.write(f"Baostock: {'✓' if BS_OK else '✗'}")
    if YF_OK:
        st.sidebar.write("YFinance: ✓")
    
    st.sidebar.write("---")
    
    # Stock code input
    st.sidebar.subheader("股票选择")
    code_input = st.sidebar.text_input("输入股票代码", value="000001", help="示例：000001(深A), 600000(沪A), AAPL(美股), 0700(港股)")
    
    # Market indicator
    market_type = mkt(code_input)
    st.sidebar.info(f"识别市场：{market_type}")
    
    # Time period
    period = st.sidebar.selectbox("数据周期", ["1个月", "3个月", "6个月", "1年", "2年"], index=3)
    
    st.sidebar.write("---")
    st.sidebar.caption("DragonX 量化分析系统 v2.0")
    
    # Main area
    st.title("DragonX 量化分析看板")
    
    # Fetch data
    with st.spinner("正在获取股票数据..."):
        df, fetch_msg, is_demo = fetch(code_input)
    
    # Show fetch status
    if is_demo:
        st.error("使用演示数据 - 真实数据获取失败")
        st.warning("以下所有价格均为随机生成，请勿用于实际交易")
    else:
        st.info(f"数据来源：{fetch_msg} | 市场：{market_type}")
    
    if df is None or len(df) < 10:
        st.error("获取数据失败，请检查股票代码。")
        return
    
    # Get stock name for A-shares
    name = stock_name(code_input) if market_type in ["A_sh", "A_sz"] else code_input
    if is_demo:
        name = f"{name} (演示数据)"
    
    # Header with stock info
    st.subheader("股票信息")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("股票名称", name)
    with col2:
        st.metric("股票代码", code_input)
    with col3:
        st.metric("数据点数", len(df))
    
    st.write("---")
    
    # Run analysis
    result = analyze(df)
    
    if "error" in result:
        st.error(result["error"])
        return
    
    df = result["df"]
    
    # Signal display
    signal = result["signal"]
    signal_emoji = {
        "STRONG BUY": "[强烈买入]",
        "BUY": "[买入]",
        "HOLD": "[持有]",
        "SELL": "[卖出]",
        "STRONG SELL": "[强烈卖出]"
    }.get(signal, "[未知]")
    
    st.subheader(f"交易信号：{signal_emoji}")
    st.write(f"评分：{result['score']}")
    
    # Key metrics - Price Data
    st.subheader("价格数据")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("最新价", f"{result['close']:.2f}")
    with col2:
        st.metric("最高价", f"{result['high']:.2f}")
    with col3:
        st.metric("最低价", f"{result['low']:.2f}")
    with col4:
        st.metric("均线20", f"{result['sma20']:.2f}")
    
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("均线50", f"{result['sma50']:.2f}")
    with col6:
        st.metric("指数均线20", f"{result['ema20']:.2f}")
    with col7:
        st.metric("支撑位", f"{result['support']:.2f}")
    with col8:
        st.metric("阻力位", f"{result['resistance']:.2f}")
    
    st.write("---")
    
    # Technical Indicators
    st.subheader("技术指标")
    
    # RSI
    st.write("**RSI分析：**")
    rsi_val = result['rsi']
    st.metric("RSI", f"{rsi_val:.1f}")
    if rsi_val < 30:
        st.success("RSI超卖 - 潜在买入机会")
    elif rsi_val > 70:
        st.warning("RSI超买 - 潜在卖出机会")
    else:
        st.info("RSI中性区间")
    
    # MACD
    st.write("**MACD分析：**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("MACD", f"{result['macd']:.3f}")
    with col2:
        st.metric("MACD信号线", f"{result['macd_signal']:.3f}")
    with col3:
        st.metric("MACD柱状图", f"{result['macd_hist']:.3f}")
    
    # KDJ
    st.write("**KDJ分析：**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("K", f"{result['kdj_k']:.1f}")
    with col2:
        st.metric("D", f"{result['kdj_d']:.1f}")
    with col3:
        st.metric("J", f"{result['kdj_j']:.1f}")
    
    j_val = result['kdj_j']
    if j_val < 0:
        st.success("KDJ超卖 - 潜在买入机会")
    elif j_val > 100:
        st.warning("KDJ超买 - 潜在卖出机会")
    else:
        st.info("KDJ中性区间")
    
    # Bollinger Bands
    st.write("**布林带：**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("布林上轨", f"{result['boll_upper']:.2f}")
    with col2:
        st.metric("布林中轨", f"{result['boll_mid']:.2f}")
    with col3:
        st.metric("布林下轨", f"{result['boll_lower']:.2f}")
    
    # ATR
    st.write("**ATR波动率（14）：**")
    st.metric("ATR", f"{result['atr']:.3f}")
    
    st.write("---")
    
    # Wyckoff phase
    st.subheader("市场阶段分析")
    st.write(f"**威科夫阶段：** {result['wyckoff_phase']}")
    
    # Support/Resistance and Forecast
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("支撑与阻力")
        st.write(f"支撑位：{result['support']:.2f}")
        st.write(f"阻力位：{result['resistance']:.2f}")
        st.write(f"布林下轨：{result['boll_lower']:.2f}")
        st.write(f"布林上轨：{result['boll_upper']:.2f}")
    
    with col2:
        st.subheader("价格预测")
        st.write(f"看涨目标：{result['target_up']:.2f} (+{((result['target_up']/result['close'])-1)*100:.1f}%)")
        st.write(f"看跌目标：{result['target_down']:.2f} ({((result['target_down']/result['close'])-1)*100:.1f}%)")
        st.write(f"ATR风险：{result['atr_risk']:.3f}")
    
    # Fibonacci levels
    st.subheader("斐波那契回撤位")
    fib_cols = st.columns(len(result['fib_levels']))
    for i, (level, value) in enumerate(result['fib_levels'].items()):
        with fib_cols[i]:
            st.metric(level, f"{value:.2f}")
    
    st.write("---")
    
    # Detect Chan theory signals
    all_signals = detect_chan_signals(df, lookback=20)
    buy_signals = [s for s in all_signals if s["type"] == "BUY"]
    sell_signals = [s for s in all_signals if s["type"] == "SELL"]
    
    # Signal summary
    st.subheader("缠论买卖信号")
    col_b, col_s = st.columns(2)
    with col_b:
        st.success(f"**买入信号（近20根K线）：** {len(buy_signals)}")
        for s in buy_signals[:5]:
            st.write(f"  {s['date'].strftime('%Y-%m-%d')} — {s['price']:.2f}")
    with col_s:
        st.error(f"**卖出信号（近20根K线）：** {len(sell_signals)}")
        for s in sell_signals[:5]:
            st.write(f"  {s['date'].strftime('%Y-%m-%d')} — {s['price']:.2f}")
    
    st.write("---")
    
    # ============ Professional Charts Section ============
    st.subheader("专业K线图")
    
    # Main K-line chart
    st.write("**主图 - K线、均线、布林带与成交量**")
    fig_main = create_main_kline_chart(df, buy_signals, sell_signals)
    st.plotly_chart(fig_main, use_container_width=True)
    
    # Three charts in a row
    st.write("**技术指标**")
    col_macd, col_rsi, col_kdj = st.columns(3)
    
    with col_macd:
        fig_macd = create_macd_chart(df)
        st.plotly_chart(fig_macd, use_container_width=True)
    
    with col_rsi:
        fig_rsi = create_rsi_chart(df)
        st.plotly_chart(fig_rsi, use_container_width=True)
    
    with col_kdj:
        fig_kdj = create_kdj_chart(df)
        st.plotly_chart(fig_kdj, use_container_width=True)
    
    st.write("---")
    
    # Footer
    if is_demo:
        st.error("免责声明：以上所有数据均为演示（随机生成）数据，请勿据此做出交易决策。")
    else:
        st.caption("DragonX 量化分析系统 | 数据可能有延迟 | 仅供学习参考，不构成投资建议")


if __name__ == "__main__":
    main()
