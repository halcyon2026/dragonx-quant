"""
DragonX V3 - Professional Stock Analysis App
K-line chart as the SOUL with Chan Theory analysis
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import ast

# Try imports for real data
try:
    import baostock as bs
    BAOSTOCK_OK = True
except:
    BAOSTOCK_OK = False

try:
    import yfinance as yf
    YF_OK = True
except:
    YF_OK = False

# ============== Page Config ==============
st.set_page_config(
    page_title="DragonX V3 - 缠论分析",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============== Default Watchlist ==============
DEFAULT_WATCHLIST = [
    ("000001", "平安银行"),
    ("600519", "贵州茅台"),
    ("601899", "紫金矿业"),
    ("000858", "五粮液"),
    ("300750", "宁德时代"),
]

# ============== Session State Init ==============
if "watchlist" not in st.session_state:
    st.session_state.watchlist = DEFAULT_WATCHLIST.copy()

# ============== Market Detection ==============
def mkt(code):
    """Detect market type from stock code"""
    code = str(code).strip()
    if code.startswith("6"):
        return "A_sh"
    elif code.startswith("0") or code.startswith("3"):
        return "A_sz"
    elif code.startswith("4") or code.startswith("8"):
        return "A_bj"
    else:
        return "US"

# ============== Demo Data Generator ==============
def demo_data(code, days=120):
    """Generate realistic demo OHLCV data"""
    np.random.seed(hash(code) % 2**32)
    
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    
    # Base price based on code
    base = 10 + (hash(code) % 100)
    prices = [base]
    
    for i in range(days - 1):
        change = np.random.randn() * 0.02 * prices[-1]
        prices.append(max(prices[-1] + change, 1))
    
    close = np.array(prices)
    open_p = close + np.random.randn(days) * 0.01 * close
    high = np.maximum(close, open_p) + np.abs(np.random.randn(days)) * 0.015 * close
    low = np.minimum(close, open_p) - np.abs(np.random.randn(days)) * 0.015 * close
    volume = np.random.randint(1000000, 10000000, days)
    
    df = pd.DataFrame({
        "date": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    })
    df.set_index("date", inplace=True)
    
    return df

# ============== A-Share Data Fetcher ==============
def fetch_a_share(code, period="d"):
    """Fetch A-share data using baostock"""
    if not BAOSTOCK_OK:
        return None, "baostock未安装", True
    
    try:
        lg = bs.login()
        if lg.error_code != "0":
            return None, f"登录失败: {lg.error_msg}", True
        
        market = "sh" if code.startswith("6") else "sz"
        bs_code = f"{market}.{code}"
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        
        freq_map = {"d": "d", "w": "w", "m": "m"}
        bs_freq = freq_map.get(period, "d")
        
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,code,open,high,low,close,volume",
            start_date=start_date,
            end_date=end_date,
            frequency=bs_freq,
            adjustflag="3"
        )
        
        if rs.error_code != "0":
            bs.logout()
            return None, f"查询失败: {rs.error_msg}", True
        
        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())
        
        bs.logout()
        
        if not data_list:
            return None, "无数据返回", True
        
        df = pd.DataFrame(data_list, columns=rs.fields)
        df["date"] = pd.to_datetime(df["date"])
        df["open"] = pd.to_numeric(df["open"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        df.dropna(inplace=True)
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        
        return df, "baostock", False
        
    except Exception as e:
        return None, f"错误: {str(e)}", True

# ============== US Stock Data Fetcher ==============
def fetch_us(code, period="d"):
    """Fetch US stock data using yfinance"""
    if not YF_OK:
        return None, "yfinance未安装", True
    
    try:
        ticker = yf.Ticker(code)
        period_map = {"d": "1y", "w": "2y", "m": "5y"}
        yf_period = period_map.get(period, "1y")
        
        df = ticker.history(period=yf_period)
        
        if df.empty:
            return None, "无数据", True
        
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index.name = "date"
        
        return df, "yfinance", False
        
    except Exception as e:
        return None, f"错误: {str(e)}", True

# ============== Unified Data Fetcher ==============
def fetch(code, period="d"):
    """Unified data fetching interface"""
    market = mkt(code)
    
    if market in ["A_sh", "A_sz"]:
        df, source, is_demo = fetch_a_share(code, period)
        if df is not None:
            return df, source, is_demo
    
    if market == "US" and YF_OK:
        df, source, is_demo = fetch_us(code, period)
        if df is not None:
            return df, source, is_demo
    
    # Fallback to demo data
    return demo_data(code), "演示数据", True

# ============== Technical Indicators ==============
def calc_macd(df, fast=12, slow=26, signal=9):
    """Calculate MACD indicator"""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calc_atr(df, period=14):
    """Calculate ATR for stop loss"""
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close)
    tr3 = abs(low - close)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    return atr

def calc_sma(df, periods=[5, 10, 20, 50]):
    """Calculate Simple Moving Averages"""
    sma = {}
    for p in periods:
        sma[p] = df["close"].rolling(p).mean()
    return sma

# ============== Fractal Detection ==============
def detect_fractals(df):
    """Detect top and bottom fractals (分型)"""
    df = df.copy()
    df["fx_peak"] = False
    df["fx_trough"] = False
    
    for i in range(1, len(df) - 1):
        # Top fractal: high[i] > high[i-1] and high[i] > high[i+1]
        if df["high"].iloc[i] > df["high"].iloc[i-1] and df["high"].iloc[i] > df["high"].iloc[i+1]:
            df.iloc[i, df.columns.get_loc("fx_peak")] = True
        # Bottom fractal: low[i] < low[i-1] and low[i] < low[i+1]
        if df["low"].iloc[i] < df["low"].iloc[i-1] and df["low"].iloc[i] < df["low"].iloc[i+1]:
            df.iloc[i, df.columns.get_loc("fx_trough")] = True
    
    return df

# ============== Zhongshu (中枢) Detection ==============
def detect_zhongshu(df):
    """Detect Zhongshu (中枢) from fractals"""
    zhongshu_list = []
    
    peaks = df[df["fx_peak"] == True]
    troughs = df[df["fx_trough"] == True]
    
    if len(peaks) < 2 or len(troughs) < 2:
        return zhongshu_list
    
    # Simple zhongshu detection: overlapping ranges
    fractal_dates = sorted(set(peaks.index.tolist() + troughs.index.tolist()))
    
    for i in range(len(fractal_dates) - 3):
        try:
            d1, d2, d3, d4 = fractal_dates[i:i+4]
            
            # Get high/low for each segment
            seg1 = df.loc[d1:d2]
            seg2 = df.loc[d2:d3]
            seg3 = df.loc[d3:d4]
            
            if len(seg1) == 0 or len(seg2) == 0 or len(seg3) == 0:
                continue
            
            # Zhongshu bounds
            ZG = min(seg1["high"].max(), seg2["high"].max(), seg3["high"].max())
            ZD = max(seg1["low"].min(), seg2["low"].min(), seg3["low"].min())
            
            if ZG > ZD:  # Valid zhongshu
                zhongshu_list.append({
                    "start": d1,
                    "end": d4,
                    "ZG": ZG,
                    "ZD": ZD,
                    "mid": (ZG + ZD) / 2
                })
        except:
            continue
    
    return zhongshu_list

# ============== Buy/Sell Signal Detection ==============
def detect_signals(df, macd_line, signal_line):
    """Detect buy and sell signals based on MACD and fractals"""
    buy_signals = []
    sell_signals = []
    
    # MACD golden cross (金叉)
    golden_crosses = []
    dead_crosses = []
    
    for i in range(1, len(df)):
        if macd_line.iloc[i-1] < signal_line.iloc[i-1] and macd_line.iloc[i] > signal_line.iloc[i]:
            golden_crosses.append({
                "date": df.index[i],
                "value": macd_line.iloc[i]
            })
            # Buy signal
            buy_signals.append({
                "date": df.index[i],
                "price": df["close"].iloc[i],
                "type": "买",
                "reason": f"MACD金叉 | 价格: {df['close'].iloc[i]:.2f}"
            })
        
        if macd_line.iloc[i-1] > signal_line.iloc[i-1] and macd_line.iloc[i] < signal_line.iloc[i]:
            dead_crosses.append({
                "date": df.index[i],
                "value": macd_line.iloc[i]
            })
            # Sell signal
            sell_signals.append({
                "date": df.index[i],
                "price": df["close"].iloc[i],
                "type": "卖",
                "reason": f"MACD死叉 | 价格: {df['close'].iloc[i]:.2f}"
            })
    
    return buy_signals, sell_signals, golden_crosses, dead_crosses

# ============== Decision Analysis ==============
def analyze_decision(df, buy_signals, sell_signals, zhongshu_list, atr):
    """Generate trading decision based on analysis"""
    latest_close = df["close"].iloc[-1]
    
    # Determine signal
    recent_buys = [s for s in buy_signals if s["date"] >= df.index[-10]]
    recent_sells = [s for s in sell_signals if s["date"] >= df.index[-10]]
    
    if len(recent_buys) > len(recent_sells):
        signal = "买入"
        signal_color = "#00FF00"
    elif len(recent_sells) > len(recent_buys):
        signal = "卖出"
        signal_color = "#FF0000"
    else:
        signal = "观望"
        signal_color = "#FFD700"
    
    # Position suggestion
    if signal == "买入":
        position_text = "建议加仓"
        position_pct = 70
    elif signal == "卖出":
        position_text = "建议减仓"
        position_pct = 30
    else:
        position_text = "保持仓位"
        position_pct = 50
    
    # Stop loss and targets
    atr_val = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else latest_close * 0.02
    recent_low = df["low"].iloc[-20:].min()
    stop_loss = recent_low - 1.5 * atr_val
    target1 = latest_close + 1 * atr_val
    target2 = latest_close + 2 * atr_val
    
    # Chan theory status
    bi_direction = "向上笔" if df["close"].iloc[-1] > df["close"].iloc[-5] else "向下笔"
    
    if zhongshu_list:
        last_zs = zhongshu_list[-1]
        if latest_close > last_zs["ZG"]:
            zs_status = "向上突破"
        elif latest_close < last_zs["ZD"]:
            zs_status = "向下突破"
        else:
            zs_status = "中枢震荡"
    else:
        zs_status = "无中枢"
    
    # Divergence check (simplified)
    macd_hist = df["close"].diff().iloc[-5:]
    if all(macd_hist.iloc[i] < macd_hist.iloc[i-1] for i in range(1, len(macd_hist))):
        beichi_status = "可能背驰"
    else:
        beichi_status = "无明显背驰"
    
    return {
        "signal": signal,
        "signal_color": signal_color,
        "position_text": position_text,
        "position_pct": position_pct,
        "stop_loss": stop_loss,
        "target1": target1,
        "target2": target2,
        "bi_direction": bi_direction,
        "zs_status": zs_status,
        "beichi_status": beichi_status
    }

# ============== K-Line Chart Builder ==============
def build_kline_chart(df, macd_line, signal_line, histogram, 
                       buy_signals, sell_signals, 
                       golden_crosses, dead_crosses,
                       zhongshu_list, sma_dict):
    """Build the complete K-line chart with all annotations"""
    
    # Create subplots
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=("K线图", "MACD", "成交量")
    )
    
    # ===== Row 1: Candlestick =====
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color="#FF3333",
        increasing_fillcolor="#FF3333",
        decreasing_line_color="#00AA00",
        decreasing_fillcolor="#00AA00",
        name="K线",
        showlegend=True
    ), row=1, col=1)
    
    # SMA lines
    if 20 in sma_dict:
        fig.add_trace(go.Scatter(
            x=df.index, y=sma_dict[20],
            name="MA20",
            line=dict(color="#FFD700", width=1),
            showlegend=True
        ), row=1, col=1)
    
    if 50 in sma_dict:
        fig.add_trace(go.Scatter(
            x=df.index, y=sma_dict[50],
            name="MA50",
            line=dict(color="#00BFFF", width=1),
            showlegend=True
        ), row=1, col=1)
    
    # Fractal markers
    peaks = df[df["fx_peak"] == True]
    troughs = df[df["fx_trough"] == True]
    
    if len(peaks) > 0:
        fig.add_trace(go.Scatter(
            x=peaks.index, y=peaks["high"],
            mode="markers+text",
            marker=dict(symbol="triangle-down", size=12, color="#FF3333"),
            text=["▼"] * len(peaks),
            textposition="top center",
            name="顶分型",
            hovertemplate="顶分型<br>价格: %{y:.2f}<extra></extra>",
            showlegend=True
        ), row=1, col=1)
    
    if len(troughs) > 0:
        fig.add_trace(go.Scatter(
            x=troughs.index, y=troughs["low"],
            mode="markers+text",
            marker=dict(symbol="triangle-up", size=12, color="#00AA00"),
            text=["▲"] * len(troughs),
            textposition="bottom center",
            name="底分型",
            hovertemplate="底分型<br>价格: %{y:.2f}<extra></extra>",
            showlegend=True
        ), row=1, col=1)
    
    # Buy signals
    for sig in buy_signals[-10:]:  # Last 10 signals
        fig.add_trace(go.Scatter(
            x=[sig["date"]], y=[sig["price"]],
            mode="markers+text",
            marker=dict(symbol="triangle-up", size=18, color="#00FF00"),
            text=[sig["type"]],
            textposition="bottom center",
            customdata=[[sig["reason"]]],
            hovertemplate="%{customdata[0]}<extra></extra>",
            showlegend=False
        ), row=1, col=1)
    
    # Sell signals
    for sig in sell_signals[-10:]:
        fig.add_trace(go.Scatter(
            x=[sig["date"]], y=[sig["price"]],
            mode="markers+text",
            marker=dict(symbol="triangle-down", size=18, color="#FF0000"),
            text=[sig["type"]],
            textposition="top center",
            customdata=[[sig["reason"]]],
            hovertemplate="%{customdata[0]}<extra></extra>",
            showlegend=False
        ), row=1, col=1)
    
    # Zhongshu rectangles
    for zs in zhongshu_list[-5:]:  # Last 5 zhongshu
        fig.add_shape(
            type="rect",
            x0=zs["start"], x1=zs["end"],
            y0=zs["ZD"], y1=zs["ZG"],
            fillcolor="rgba(255,200,0,0.15)",
            line=dict(color="rgba(255,200,0,0.6)", width=1),
            row=1, col=1
        )
    
    # ===== Row 2: MACD =====
    fig.add_trace(go.Scatter(
        x=df.index, y=macd_line,
        name="MACD",
        line=dict(color="#00BFFF", width=1.5),
        showlegend=True
    ), row=2, col=1)
    
    fig.add_trace(go.Scatter(
        x=df.index, y=signal_line,
        name="Signal",
        line=dict(color="#FFD700", width=1.5),
        showlegend=True
    ), row=2, col=1)
    
    # MACD histogram
    colors = ["#FF3333" if v >= 0 else "#00AA00" for v in histogram]
    fig.add_trace(go.Bar(
        x=df.index, y=histogram,
        marker_color=colors,
        name="Histogram",
        opacity=0.6,
        showlegend=True
    ), row=2, col=1)
    
    # Golden cross markers
    for gc in golden_crosses[-5:]:
        fig.add_trace(go.Scatter(
            x=[gc["date"]], y=[gc["value"]],
            mode="markers+text",
            marker=dict(symbol="triangle-up", size=10, color="#00FF00"),
            text=["金叉"],
            textposition="bottom center",
            showlegend=False
        ), row=2, col=1)
    
    # Dead cross markers
    for dc in dead_crosses[-5:]:
        fig.add_trace(go.Scatter(
            x=[dc["date"]], y=[dc["value"]],
            mode="markers+text",
            marker=dict(symbol="triangle-down", size=10, color="#FF0000"),
            text=["死叉"],
            textposition="top center",
            showlegend=False
        ), row=2, col=1)
    
    # ===== Row 3: Volume =====
    vol_colors = ["#FF3333" if df["close"].iloc[i] >= df["open"].iloc[i] else "#00AA00" 
                  for i in range(len(df))]
    fig.add_trace(go.Bar(
        x=df.index, y=df["volume"],
        marker_color=vol_colors,
        name="成交量",
        opacity=0.7,
        showlegend=True
    ), row=3, col=1)
    
    # ===== Layout Update =====
    fig.update_layout(
        template=None,
        paper_bgcolor="#131722",
        plot_bgcolor="#131722",
        font=dict(color="#D1D4DC", size=11),
        height=800,
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=10)
        )
    )
    
    # Update axes
    for row in [1, 2, 3]:
        fig.update_xaxes(
            gridcolor="#2B2B43",
            rangeslider_visible=False,
            row=row, col=1
        )
        fig.update_yaxes(
            gridcolor="#2B2B43",
            row=row, col=1
        )
    
    return fig

# ============== Main App ==============
def main():
    # Title
    st.title("🐉 DragonX V3 - 缠论分析系统")
    st.markdown("---")
    
    # ===== Sidebar =====
    st.sidebar.subheader("📊 自选股")
    
    # Watchlist selection
    watchlist_display = [f"{code} {name}" for code, name in st.session_state.watchlist]
    selected = st.sidebar.radio("选择股票", watchlist_display, key="stock_select")
    code_input = selected.split()[0]
    
    # Custom stock input
    st.sidebar.markdown("---")
    new_code = st.sidebar.text_input("添加股票代码", key="new_code")
    if st.sidebar.button("添加到自选股"):
        if new_code and new_code not in [c for c, n in st.session_state.watchlist]:
            st.session_state.watchlist.append((new_code, f"股票{new_code}"))
            st.success(f"已添加 {new_code}")
            st.rerun()
    
    # Period selector
    st.sidebar.markdown("---")
    period_display = st.sidebar.selectbox(
        "K线周期",
        ["日线", "60分钟", "30分钟", "15分钟", "5分钟"],
        key="period_select"
    )
    period_map = {"日线": "d", "60分钟": "60m", "30分钟": "30m", "15分钟": "15m", "5分钟": "5m"}
    period = period_map[period_display]
    
    # ===== Fetch Data =====
    with st.spinner("正在获取数据..."):
        df, data_source, is_demo = fetch(code_input, period)
    
    # Data status
    st.sidebar.markdown("---")
    st.sidebar.caption(f"数据来源: {data_source}")
    if not is_demo and len(df) > 0:
        st.sidebar.caption(f"最后更新: {df.index[-1].strftime('%Y-%m-%d %H:%M')}")
    else:
        st.sidebar.caption("最后更新: 模拟数据")
    
    # ===== Check Data =====
    if df is None or len(df) == 0:
        st.error("无法获取数据，请检查股票代码或网络连接")
        return
    
    # ===== Calculate Indicators =====
    # MACD
    macd_line, signal_line, histogram = calc_macd(df)
    
    # ATR
    atr = calc_atr(df)
    
    # SMA
    sma_dict = calc_sma(df, [5, 10, 20, 50])
    
    # Fractals
    df = detect_fractals(df)
    
    # Zhongshu
    zhongshu_list = detect_zhongshu(df)
    
    # Signals
    buy_signals, sell_signals, golden_crosses, dead_crosses = detect_signals(df, macd_line, signal_line)
    
    # Decision
    decision = analyze_decision(df, buy_signals, sell_signals, zhongshu_list, atr)
    
    # ===== Layout =====
    col_chart, col_decision = st.columns([0.7, 0.3])
    
    # ===== Main Chart =====
    with col_chart:
        st.subheader(f"📈 {code_input} - {period_display}")
        
        fig = build_kline_chart(
            df, macd_line, signal_line, histogram,
            buy_signals, sell_signals,
            golden_crosses, dead_crosses,
            zhongshu_list, sma_dict
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # ===== Decision Panel =====
    with col_decision:
        # Signal
        st.subheader("🎯 操作建议")
        signal_html = f'<div style="font-size:2rem;color:{decision["signal_color"]};font-weight:bold;text-align:center;padding:10px;border-radius:8px;background:rgba(0,0,0,0.3)">{decision["signal"]}</div>'
        st.markdown(signal_html, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Position
        st.subheader("📊 建议仓位")
        st.progress(decision["position_pct"] / 100)
        st.write(f"{decision['position_text']} ({decision['position_pct']}%)")
        
        st.markdown("---")
        
        # Key levels
        st.subheader("💰 关键价位")
        latest_close = df["close"].iloc[-1]
        st.write(f"当前价: **{latest_close:.2f}**")
        st.write(f"止损位: **{decision['stop_loss']:.2f}**")
        st.write(f"目标1: **{decision['target1']:.2f}**")
        st.write(f"目标2: **{decision['target2']:.2f}**")
        
        st.markdown("---")
        
        # Chan theory status
        st.subheader("🌀 缠论状态")
        st.write(f"当前笔: **{decision['bi_direction']}**")
        st.write(f"中枢: **{decision['zs_status']}**")
        st.write(f"背驰: **{decision['beichi_status']}**")
        
        st.markdown("---")
        
        # Recent signals
        st.subheader("📋 最近买卖点")
        all_signals = sorted(buy_signals + sell_signals, key=lambda x: x["date"], reverse=True)
        for s in all_signals[:5]:
            date_str = s["date"].strftime("%m-%d")
            st.write(f"{date_str} {s['type']} {s['price']:.2f}")
        
        if not all_signals:
            st.write("暂无信号")
        
        st.markdown("---")
        
        # Statistics
        st.subheader("📈 统计信息")
        st.write(f"数据天数: **{len(df)}**")
        st.write(f"顶分型: **{df['fx_peak'].sum()}**")
        st.write(f"底分型: **{df['fx_trough'].sum()}**")
        st.write(f"中枢数: **{len(zhongshu_list)}**")

# ============== Entry Point ==============
if __name__ == "__main__":
    main()
