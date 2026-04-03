# -*- coding: utf-8 -*-
"""
缠论智能选股分析系统 - DragonX Chan Theory v2
严格遵循缠中说禅理论：包含处理、分型、笔、线段、中枢、背驰、买卖点

v2 修复清单:
  P0-1/2/3: 数据范围绑定 — sidebar选择的数据范围严格约束所有缠论计算
  P0-4/5/6: 买卖点逻辑 — 一买<二买<三买时序保证，同时间戳去重，决策匹配最新信号
  P1-7:     背驰状态 — detect_beichi_status 替代硬编码 "待检测"
  P2-1:     中枢显示 — ZD-ZG 格式化输出
  P2-2:     决策说明 — reason 字段透传到 UI
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="DragonX 缠论分析系统 v2",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义 CSS
st.markdown("""
<style>
.stApp { background-color: #0e1117; }
.block-container { padding-top: 1rem; padding-bottom: 1rem; }
[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #2B2B43; }
h1, h2, h3, h4, h5, h6, p, label, span { color: #D1D4DC !important; }
.stMetric label, .stMetric .metric-value { color: #D1D4DC !important; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { background-color: #1e2530; border-radius: 4px 4px 0 0; padding: 8px 16px; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 数据获取模块
# ============================================================

def get_stock_data_baostock(code, period='d', days=365):
    """
    从 baostock 获取 A 股 K 线数据
    days: 实际天数（如30天、90天、180天、365天、730天）
    返回该时间范围内的所有K线
    """
    try:
        import baostock as bs
        if code.startswith('6'):
            bs_code = f"sh.{code}"
        elif code.startswith(('0', '3')):
            bs_code = f"sz.{code}"
        else:
            bs_code = code

        lg = bs.login()
        if lg.error_code != '0':
            return None

        freq_map = {'d': 'd', '60': '60', '30': '30', '15': '15', '5': '5'}
        freq = freq_map.get(period, 'd')

        # 根据实际天数计算开始日期
        # 对于分钟线，需要更多天数来获取足够的K线
        if freq == 'd':
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        else:
            # 分钟线需要更多天数（每天约4根60分钟K线）
            multiplier = {'60': 4, '30': 8, '15': 16, '5': 48}
            start_date = (datetime.now() - timedelta(days=days * multiplier.get(freq, 4))).strftime('%Y-%m-%d')

        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date=start_date,
            end_date=datetime.now().strftime('%Y-%m-%d'),
            frequency=freq,
            adjustflag='3'
        )

        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())

        bs.logout()

        if not data_list:
            return None

        df = pd.DataFrame(data_list, columns=['date', 'open', 'high', 'low', 'close', 'volume', 'amount'])
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df = df.dropna()

        # 严格过滤时间范围：只保留指定天数内的数据
        cutoff_date = datetime.now() - timedelta(days=days)
        df = df[df.index >= cutoff_date]

        return df

    except Exception:
        return None


def get_demo_data(days=730):
    """演示用模拟数据 - 模拟趋势行情，默认生成2年数据"""
    np.random.seed(42)
    # 确保生成足够的数据覆盖最大范围（2年）
    periods = max(days + 30, 760)  # 多生成30天作为缓冲
    dates = pd.date_range(end=datetime.now(), periods=periods, freq='D')

    trend = np.zeros(periods)
    trend[0] = 50
    for i in range(1, periods):
        trend[i] = trend[i - 1] + np.random.normal(0.05, 0.8)
        if i > 50:
            trend[i] += 0.1 * np.sin(i * 0.1)
        if i > 150:
            trend[i] -= 0.15 * np.sin((i - 150) * 0.08)
        if i > 220:
            trend[i] += 0.2 * np.cos((i - 220) * 0.15)

    base_price = trend
    volatility = 1.5

    data = {
        'open': base_price + np.random.normal(0, volatility, periods),
        'high': base_price + abs(np.random.normal(0.5, volatility, periods)),
        'low': base_price - abs(np.random.normal(0.5, volatility, periods)),
        'close': base_price + np.random.normal(0, volatility, periods),
        'volume': np.random.uniform(5e6, 20e6, periods) * (1 + 0.3 * np.sin(np.arange(periods) * 0.1)),
    }

    df = pd.DataFrame(data, index=dates)
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].clip(lower=1)
    df['volume'] = df['volume'].clip(lower=1e6)
    df['amount'] = df['close'] * df['volume']
    return df.tail(days)  # 只返回需要的天数


def get_stock_name_baostock(code):
    """获取股票名称"""
    try:
        import baostock as bs
        if code.startswith('6'):
            bs_code = f"sh.{code}"
        else:
            bs_code = f"sz.{code}"

        lg = bs.login()
        rs = bs.query_stock_basic(code=bs_code)
        bs.logout()

        if rs.error_code == '0' and rs.next():
            return rs.get_row_data()[1]
    except Exception:
        pass
    return code


# ============================================================
# 缠论核心算法
# ============================================================

def process_containment(df):
    """
    包含处理：处理相邻K线之间的包含关系
    向上趋势：取高高  向下趋势：取低低
    """
    if len(df) < 2:
        return df.copy()

    processed = []
    for idx, row in df.iterrows():
        if not processed:
            processed.append({
                'idx': idx, 'high': row['high'], 'low': row['low'],
                'open': row['open'], 'close': row['close']
            })
            continue

        prev = processed[-1]
        has_containment = (
            (row['high'] >= prev['high'] and row['low'] <= prev['low']) or
            (row['high'] <= prev['high'] and row['low'] >= prev['low'])
        )

        if has_containment:
            if len(processed) >= 2:
                prev2 = processed[-2]
                trend = 1 if prev['high'] > prev2['high'] else -1
            else:
                trend = 1

            if trend == 1:
                new_high = max(row['high'], prev['high'])
                new_low = max(row['low'], prev['low'])
            else:
                new_high = min(row['high'], prev['high'])
                new_low = min(row['low'], prev['low'])

            processed[-1] = {
                'idx': prev['idx'],
                'high': new_high,
                'low': new_low,
                'open': prev['open'],
                'close': row['close']
            }
        else:
            processed.append({
                'idx': idx, 'high': row['high'], 'low': row['low'],
                'open': row['open'], 'close': row['close']
            })

    result = pd.DataFrame(processed)
    result.set_index('idx', inplace=True)
    return result


def detect_fractals(df_processed):
    """
    分型检测：顶分型和底分型
    顶分型：中间K线高点最高，低点也最高
    底分型：中间K线低点最低，高点也最低
    """
    fractals = []
    for i in range(1, len(df_processed) - 1):
        prev = df_processed.iloc[i - 1]
        curr = df_processed.iloc[i]
        next_ = df_processed.iloc[i + 1]

        if (curr['high'] > prev['high'] and curr['high'] > next_['high'] and
                curr['low'] > prev['low'] and curr['low'] > next_['low']):
            fractals.append({
                'idx': i, 'date': curr.name,
                'type': 'top', 'price': curr['high']
            })
        elif (curr['low'] < prev['low'] and curr['low'] < next_['low'] and
              curr['high'] < prev['high'] and curr['high'] < next_['high']):
            fractals.append({
                'idx': i, 'date': curr.name,
                'type': 'bottom', 'price': curr['low']
            })

    return fractals


def detect_bi(fractals):
    """
    笔检测：连接相邻的分型
    条件：1. 顶底交替  2. 相邻分型之间至少5根K线
    """
    if len(fractals) < 2:
        return [], []

    bi_list = []
    valid_fractals = []

    for f in fractals:
        if not valid_fractals:
            valid_fractals.append(f)
            continue

        last = valid_fractals[-1]

        if f['type'] == last['type']:
            if f['type'] == 'top' and f['price'] > last['price']:
                valid_fractals[-1] = f
            elif f['type'] == 'bottom' and f['price'] < last['price']:
                valid_fractals[-1] = f
        else:
            k_count = abs(f['idx'] - last['idx']) + 1
            if k_count >= 5:
                valid_fractals.append(f)
                bi_list.append({
                    'start_date': last['date'],
                    'end_date': f['date'],
                    'start_price': last['price'],
                    'end_price': f['price'],
                    'direction': 'up' if f['type'] == 'top' else 'down',
                    'start_type': last['type'],
                    'end_type': f['type'],
                    'start_idx': last['idx'],
                    'end_idx': f['idx']
                })

    return bi_list, valid_fractals


def detect_zhongshu(bi_list):
    """
    中枢检测：至少3笔有重叠区域
    ZD: 中枢最低价  ZG: 中枢最高价  ZZ: 中枢中价
    同时检测本级中枢和次级别中枢（带合理性校验）
    """
    zhongshu_list = []
    sub_zhongshu_list = []

    # 本级中枢：3笔重叠
    for i in range(len(bi_list) - 2):
        b1, b2, b3 = bi_list[i], bi_list[i + 1], bi_list[i + 2]

        r1 = (min(b1['start_price'], b1['end_price']),
              max(b1['start_price'], b1['end_price']))
        r2 = (min(b2['start_price'], b2['end_price']),
              max(b2['start_price'], b2['end_price']))
        r3 = (min(b3['start_price'], b3['end_price']),
              max(b3['start_price'], b3['end_price']))

        ZD = max(r1[0], r2[0], r3[0])
        ZG = min(r1[1], r2[1], r3[1])

        if ZG > ZD:
            zhongshu_list.append({
                'start_date': b1['start_date'],
                'end_date': b3['end_date'],
                'ZD': ZD, 'ZG': ZG,
                'ZZ': (ZD + ZG) / 2,
                'bi_indices': [i, i + 1, i + 2],
                'bi_count': 3,
                'level': 'main'  # 本级中枢
            })

    # P1-修复：次级别中枢检测 — 基于笔内波动（非跨周期）
    # 在本级中枢区间内，检测笔内部的更小级别波动形成的次级别中枢
    for zs in zhongshu_list:
        # 搜索该中枢前后的笔，寻找在同一价格区间内的次级别中枢
        for j in range(max(0, zs['bi_indices'][0] - 1), min(len(bi_list) - 2, zs['bi_indices'][-1] + 3)):
            b1, b2, b3 = bi_list[j], bi_list[j + 1], bi_list[j + 2]

            r1 = (min(b1['start_price'], b1['end_price']),
                  max(b1['start_price'], b1['end_price']))
            r2 = (min(b2['start_price'], b2['end_price']),
                  max(b2['start_price'], b2['end_price']))
            r3 = (min(b3['start_price'], b3['end_price']),
                  max(b3['start_price'], b3['end_price']))

            sub_ZD = max(r1[0], r2[0], r3[0])
            sub_ZG = min(r1[1], r2[1], r3[1])

            if sub_ZG > sub_ZD:
                # P1-合理性校验：次级别中枢必须在本级中枢 ±15% 范围内
                lower_bound = zs['ZD'] * 0.85
                upper_bound = zs['ZG'] * 1.15
                
                # 校验1：价格范围必须在本级中枢附近
                if sub_ZD < lower_bound or sub_ZG > upper_bound:
                    # 记录警告日志（可选）
                    # print(f"[WARNING] 次级别中枢 {sub_ZD:.2f}-{sub_ZG:.2f} 超出本级中枢范围，已过滤")
                    continue
                
                # 校验2：次级别中枢不能与本级中枢相同
                if abs(sub_ZD - zs['ZD']) < 0.01 and abs(sub_ZG - zs['ZG']) < 0.01:
                    continue
                
                # 校验3：次级别中枢宽度应在合理范围（本级中枢宽度的20%-80%）
                sub_width = sub_ZG - sub_ZD
                main_width = zs['ZG'] - zs['ZD']
                if sub_width < main_width * 0.2 or sub_width > main_width * 0.8:
                    continue
                
                sub_zhongshu_list.append({
                    'start_date': b1['start_date'],
                    'end_date': b3['end_date'],
                    'ZD': sub_ZD, 'ZG': sub_ZG,
                    'ZZ': (sub_ZD + sub_ZG) / 2,
                    'bi_indices': [j, j + 1, j + 2],
                    'bi_count': 3,
                    'level': 'sub',
                    'parent_ZD': zs['ZD'],
                    'parent_ZG': zs['ZG']
                })

    return zhongshu_list, sub_zhongshu_list


def detect_xduan(bi_list, zhongshu_list):
    """
    线段检测：进入段和离开段的方向判断
    线段至少由三笔构成
    """
    xduan_list = []
    if len(bi_list) < 3:
        return xduan_list

    for i in range(len(bi_list) - 2):
        seg_bi = bi_list[i:i + 3]
        if all(b['direction'] == 'up' for b in seg_bi):
            xduan_list.append({
                'start_date': seg_bi[0]['start_date'],
                'end_date': seg_bi[-1]['end_date'],
                'direction': 'up',
                'start_price': seg_bi[0]['start_price'],
                'end_price': seg_bi[-1]['end_price']
            })
        elif all(b['direction'] == 'down' for b in seg_bi):
            xduan_list.append({
                'start_date': seg_bi[0]['start_date'],
                'end_date': seg_bi[-1]['end_date'],
                'direction': 'down',
                'start_price': seg_bi[0]['start_price'],
                'end_price': seg_bi[-1]['end_price']
            })

    return xduan_list


def detect_macd(df):
    """
    计算 MACD 指标
    DIF: 快线 EMA12 - EMA26
    DEA: 慢线 DIF的EMA9
    MACD: 2 * (DIF - DEA)
    """
    close = df['close'].copy()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd = 2 * (dif - dea)
    return dif, dea, macd


def detect_divergence(df, bi_list, dif, dea):
    """
    背驰检测：比较相邻同向笔对应的MACD面积
    底背驰：价格创新低，但MACD面积缩小
    顶背驰：价格创新高，但MACD面积缩小
    """
    divergences = []

    for i in range(1, len(bi_list)):
        curr_bi = bi_list[i]
        prev_bi = bi_list[i - 1]

        try:
            start_idx = df.index.get_loc(curr_bi['start_date'])
            end_idx = df.index.get_loc(curr_bi['end_date'])
            prev_start_idx = df.index.get_loc(prev_bi['start_date'])
            prev_end_idx = df.index.get_loc(prev_bi['end_date'])

            curr_macd = dif.iloc[start_idx:end_idx + 1]
            prev_macd = dif.iloc[prev_start_idx:prev_end_idx + 1]

            curr_area = abs(curr_macd.sum())
            prev_area = abs(prev_macd.sum())

            if curr_bi['direction'] == 'down' and curr_bi['end_price'] < prev_bi['end_price']:
                if prev_area > 0 and curr_area < prev_area * 0.8:
                    divergences.append({
                        'date': curr_bi['end_date'],
                        'price': curr_bi['end_price'],
                        'type': 'bottom_div',
                        'label': '底背离',
                        'area_ratio': curr_area / prev_area
                    })

            if curr_bi['direction'] == 'up' and curr_bi['end_price'] > prev_bi['end_price']:
                if prev_area > 0 and curr_area < prev_area * 0.8:
                    divergences.append({
                        'date': curr_bi['end_date'],
                        'price': curr_bi['end_price'],
                        'type': 'top_div',
                        'label': '顶背离',
                        'area_ratio': curr_area / prev_area
                    })

        except (KeyError, ValueError):
            continue

    return divergences


# ============================================================
# P0-4/5/6: FIXED buy/sell point detection
# ============================================================

def detect_buy_sell_points(bi_list, zhongshu_list, divergences):
    """
    买卖点检测 — 严格时序保证
    一买 < 二买 < 三买（时间顺序）
    同一时间戳只保留优先级最高的信号
    """
    signals = []

    for zs in zhongshu_list:
        post_bi = [b for b in bi_list if b['start_date'] >= zs['end_date']]

        # Track which types already found for this zhongshu
        found_buy_1 = found_buy_2 = found_buy_3 = False
        found_sell_1 = found_sell_2 = found_sell_3 = False

        # --- Buy signals (process in time order) ---
        for bi in post_bi:
            if found_buy_1 and found_buy_2 and found_buy_3:
                break

            # 一买: price falls below ZD with bottom divergence (first occurrence only)
            if not found_buy_1 and bi['direction'] == 'down' and bi['end_price'] < zs['ZD']:
                div = any(
                    d['date'] == bi['end_date'] and d['type'] == 'bottom_div'
                    for d in divergences
                )
                if div:
                    signals.append({
                        'date': bi['end_date'],
                        'price': bi['end_price'],
                        'type': '一买',
                        'reason': 'B1：中枢下方底背驰',
                        'side': 'buy',
                        'priority': 1,
                        'color': '#FF0000'
                    })
                    found_buy_1 = True
                    continue

            # 二买: after 一买, pullback to ZD area
            if found_buy_1 and not found_buy_2 and bi['direction'] == 'down':
                if zs['ZD'] * 0.98 <= bi['end_price'] <= zs['ZG'] * 1.02:
                    signals.append({
                        'date': bi['end_date'],
                        'price': bi['end_price'],
                        'type': '二买',
                        'reason': 'B2：回调至中枢区间',
                        'side': 'buy',
                        'priority': 2,
                        'color': '#FF6600'
                    })
                    found_buy_2 = True
                    continue

            # 三买: break above ZG, pullback not entering zhongshu
            if found_buy_2 and not found_buy_3 and bi['direction'] == 'up':
                if bi['start_price'] > zs['ZG'] and bi['end_price'] >= zs['ZG']:
                    signals.append({
                        'date': bi['end_date'],
                        'price': bi['end_price'],
                        'type': '三买',
                        'reason': 'B3：突破中枢后回踩不破ZG',
                        'side': 'buy',
                        'priority': 3,
                        'color': '#FFCC00'
                    })
                    found_buy_3 = True
                    continue

        # --- Sell signals (process in time order) ---
        for bi in post_bi:
            if found_sell_1 and found_sell_2 and found_sell_3:
                break

            # 一卖: price above ZG with top divergence
            if not found_sell_1 and bi['direction'] == 'up' and bi['end_price'] > zs['ZG']:
                div = any(
                    d['date'] == bi['end_date'] and d['type'] == 'top_div'
                    for d in divergences
                )
                if div:
                    signals.append({
                        'date': bi['end_date'],
                        'price': bi['end_price'],
                        'type': '一卖',
                        'reason': 'S1：中枢上方顶背驰',
                        'side': 'sell',
                        'priority': 1,
                        'color': '#00FF00'
                    })
                    found_sell_1 = True
                    continue

            # 二卖: after 一卖, rebound to ZD-ZG area
            if found_sell_1 and not found_sell_2 and bi['direction'] == 'up':
                if zs['ZD'] * 0.98 <= bi['end_price'] <= zs['ZG'] * 1.02:
                    signals.append({
                        'date': bi['end_date'],
                        'price': bi['end_price'],
                        'type': '二卖',
                        'reason': 'S2：反弹至中枢区间',
                        'side': 'sell',
                        'priority': 2,
                        'color': '#0088FF'
                    })
                    found_sell_2 = True
                    continue

            # 三卖: break below ZD, rebound not exceeding ZD
            if found_sell_2 and not found_sell_3 and bi['direction'] == 'down':
                if bi['start_price'] < zs['ZD'] and bi['end_price'] <= zs['ZD']:
                    signals.append({
                        'date': bi['end_date'],
                        'price': bi['end_price'],
                        'type': '三卖',
                        'reason': 'S3：跌破中枢后反弹不破ZD',
                        'side': 'sell',
                        'priority': 3,
                        'color': '#8800FF'
                    })
                    found_sell_3 = True
                    continue

    # Remove duplicates at same timestamp (keep highest priority = lowest number)
    seen = {}
    for s in sorted(signals, key=lambda x: x['priority']):
        key = str(s['date'])[:10]
        if key not in seen:
            seen[key] = s

    # P0-10: 时序校验 — 过滤不符合时间顺序的买卖点
    validated_signals = []
    
    # 分别处理买点和卖点
    buy_signals = sorted([s for s in seen.values() if s['side'] == 'buy'], key=lambda x: x['date'])
    sell_signals = sorted([s for s in seen.values() if s['side'] == 'sell'], key=lambda x: x['date'])
    
    # 买点时序校验：一买 < 二买 < 三买
    buy_1_date = buy_2_date = buy_3_date = None
    for s in buy_signals:
        is_valid = True
        if s['type'] == '一买':
            buy_1_date = s['date']
        elif s['type'] == '二买':
            if buy_1_date is None or s['date'] <= buy_1_date:
                is_valid = False  # 二买必须晚于一买
            else:
                buy_2_date = s['date']
        elif s['type'] == '三买':
            if buy_2_date is None or s['date'] <= buy_2_date:
                is_valid = False  # 三买必须晚于二买
            else:
                buy_3_date = s['date']
        
        if is_valid:
            validated_signals.append(s)
        else:
            # 标记为异常（灰色）
            s_invalid = s.copy()
            s_invalid['type'] = f"{s['type']}(异常)"
            s_invalid['color'] = '#888888'
            s_invalid['reason'] = f"{s['reason']} [时序错误]"
            validated_signals.append(s_invalid)
    
    # 卖点时序校验：一卖 < 二卖 < 三卖
    sell_1_date = sell_2_date = sell_3_date = None
    for s in sell_signals:
        is_valid = True
        if s['type'] == '一卖':
            sell_1_date = s['date']
        elif s['type'] == '二卖':
            if sell_1_date is None or s['date'] <= sell_1_date:
                is_valid = False  # 二卖必须晚于一卖
            else:
                sell_2_date = s['date']
        elif s['type'] == '三卖':
            if sell_2_date is None or s['date'] <= sell_2_date:
                is_valid = False  # 三卖必须晚于二卖
            else:
                sell_3_date = s['date']
        
        if is_valid:
            validated_signals.append(s)
        else:
            # 标记为异常（灰色）
            s_invalid = s.copy()
            s_invalid['type'] = f"{s['type']}(异常)"
            s_invalid['color'] = '#888888'
            s_invalid['reason'] = f"{s['reason']} [时序错误]"
            validated_signals.append(s_invalid)

    return validated_signals


# ============================================================
# P1-7: FIXED beichi status
# ============================================================

def detect_beichi_status(bi_list, divergences, zhongshu_list=None, period='d'):
    """
    Return clear beichi status with level annotation
    区分：无背驰 / 盘整背驰 / 趋势背驰
    """
    # 级别标注
    level_map = {'d': '日线', '60': '60分钟', '30': '30分钟', '15': '15分钟', '5': '5分钟'}
    level = level_map.get(period, '日线')

    if not divergences:
        return f"无背驰（{level}）"

    latest_div = max(divergences, key=lambda x: x['date'])

    # 判断背驰类型：盘整背驰 vs 趋势背驰
    is_trend_beichi = False

    if zhongshu_list:
        last_zs = zhongshu_list[-1]
        div_price = latest_div['price']

        # 趋势背驰：价格在中枢区间之外
        if latest_div['type'] == 'bottom_div' and div_price < last_zs['ZD']:
            is_trend_beichi = True  # 下跌趋势背驰
        elif latest_div['type'] == 'top_div' and div_price > last_zs['ZG']:
            is_trend_beichi = True  # 上涨趋势背驰

    if is_trend_beichi:
        if latest_div['type'] == 'bottom_div':
            return f"{level}趋势背驰（买点）"
        else:
            return f"{level}趋势背驰（卖点）"
    else:
        if latest_div['type'] == 'bottom_div':
            return f"{level}盘整背驰（买点）"
        else:
            return f"{level}盘整背驰（卖点）"


def analyze_trend(bi_list, zhongshu_list, signals=None):
    """
    分析当前趋势状态
    P0-任务D: 笔方向与买卖点信号强制一致
    """
    # P0-D: 如果有信号，根据最新信号强制确定笔方向
    if signals:
        latest_signal = max(signals, key=lambda x: x['date'])
        if latest_signal['side'] == 'buy':
            bi_direction = "向上"  # 一买/二买/三买 → 向上
        else:
            bi_direction = "向下"  # 一卖/二卖/三卖 → 向下
    elif bi_list:
        # 无信号时，按最后一笔方向
        last_bi = bi_list[-1]
        bi_direction = "向上" if last_bi['direction'] == 'up' else "向下"
    else:
        bi_direction = "待确认"

    if zhongshu_list:
        last_zs = zhongshu_list[-1]
        zs_range = f"{last_zs['ZD']:.2f}~{last_zs['ZG']:.2f}"
    else:
        zs_range = "无中枢"

    return bi_direction, zs_range


# ============================================================
# P1-TASK-F: 中枢位置关系智能提示（含信号冲突处理）
# ============================================================

def analyze_zhongshu_relation(zhongshu_list, sub_zhongshu_list, action=None):
    """
    判断本级中枢与次级别中枢的位置关系
    P0-TASK-J: 增加信号冲突处理
    Returns: (position_hint, hint_color) — 提示文本和颜色
    """
    if not zhongshu_list or not sub_zhongshu_list:
        return None, None
    
    main_zs = zhongshu_list[-1]
    sub_zs = sub_zhongshu_list[-1]
    
    main_ZD = main_zs['ZD']
    main_ZG = main_zs['ZG']
    sub_ZD = sub_zs['ZD']
    sub_ZG = sub_zs['ZG']
    
    # 判断基础位置关系
    relation = None
    # 情况1：次级别中枢完全在本级中枢内部
    if sub_ZD >= main_ZD and sub_ZG <= main_ZG:
        relation = "internal"
    # 情况2：次级别中枢完全在本级中枢上方
    elif sub_ZD > main_ZG:
        relation = "above"
    # 情况3：次级别中枢完全在本级中枢下方
    elif sub_ZG < main_ZD:
        relation = "below"
    # 情况4：部分重叠
    else:
        relation = "overlap"
    
    # P0-TASK-J: 信号冲突处理
    sell_actions = ['卖出', '减仓', '反弹卖出', '观望']
    buy_actions = ['买入', '加仓', '持有']
    
    # 如果操作建议是卖出类，不显示"关注三买/三卖"
    if action in sell_actions:
        if relation == "above":
            # 结构上接近三买区域，但卖出信号优先
            return "⚠️ 信号冲突：结构接近三买，但卖出信号优先，建议等待", "#FFD700"
        elif relation == "below":
            return "⚠️ 价格已离开本级中枢，卖出信号确认", "#FF4444"
        elif relation == "internal":
            return "本级中枢内运行", "#888888"
        else:
            return "中枢震荡中", "#888888"
    
    # 买入类操作，正常显示
    if relation == "internal":
        return "本级中枢内运行", "#888888"
    elif relation == "above":
        return "⚠️ 价格已离开本级中枢，关注三买", "#FFCC00"
    elif relation == "below":
        return "⚠️ 价格跌破本级中枢，关注三卖", "#FF4444"
    else:
        return "中枢震荡，关注突破方向", "#00BFFF"


# ============================================================
# P0-6: FIXED decision logic
# ============================================================

def generate_decision(df, bi_list, zhongshu_list, signals, last_price):
    """
    生成交易决策 — MUST match latest signal
    Returns: (action, position_pct, position_text, stop_loss, target1, target2, reason)
    """
    if df is None or len(df) < 30:
        return "观望", 50, "数据不足", None, None, None, "数据不足"

    # Get latest signal
    if signals:
        latest_signal = max(signals, key=lambda x: x['date'])

        if latest_signal['side'] == 'buy':
            # P3-修改：仓位按买点类型分级
            if latest_signal['type'] == '一买':
                action, position_pct, position_text = "买入", 30, "三成仓"  # 试探性建仓
            elif latest_signal['type'] == '二买':
                action, position_pct, position_text = "加仓", 50, "五成仓"  # 确认加仓
            else:  # 三买
                action, position_pct, position_text = "持有", 70, "七成仓"  # 趋势加速
            reason = f"最近信号：{latest_signal['type']} ({latest_signal['date'].strftime('%m-%d')})"

        else:  # sell
            if latest_signal['type'] == '一卖':
                action, position_pct, position_text = "卖出", 10, "清仓"
                reason = f"最近信号：一卖 ({latest_signal['date'].strftime('%m-%d')})"
            elif latest_signal['type'] == '二卖':
                action, position_pct, position_text = "减仓", 30, "三成仓"
                reason = f"最近信号：二卖 ({latest_signal['date'].strftime('%m-%d')})"
            else:  # 三卖 — P0-TASK-E: 细化处理
                # 计算三卖出现后经过的K线数量
                signal_date = latest_signal['date']
                signal_price = latest_signal['price']
                
                try:
                    # 找到信号日期在df中的位置
                    signal_idx = df.index.get_loc(signal_date)
                    current_idx = len(df) - 1
                    bars_passed = current_idx - signal_idx
                    
                    # P0-E: 三卖后操作建议明确化
                    if bars_passed <= 3:
                        # 三卖出现后 3根K线内 → 卖出
                        action, position_pct, position_text = "卖出", 10, "清仓"
                        reason = f"三卖({signal_date.strftime('%m-%d')})，{bars_passed+1}日内，建议卖出"
                    else:
                        # 三卖出现超过 3根K线
                        if last_price < signal_price:
                            # 当前价低于三卖价格 → 观望
                            action, position_pct, position_text = "观望", 20, "轻仓"
                            reason = f"三卖({signal_date.strftime('%m-%d')})，已过{bars_passed}日且价格更低，观望"
                        else:
                            # 当前价高于三卖价格 → 反弹卖出
                            action, position_pct, position_text = "反弹卖出", 30, "三成仓"
                            reason = f"三卖({signal_date.strftime('%m-%d')})，已过{bars_passed}日但价格反弹，建议卖出"
                except (KeyError, ValueError):
                    # 无法定位信号日期，使用默认
                    action, position_pct, position_text = "卖出", 10, "清仓"
                    reason = f"最近信号：三卖 ({signal_date.strftime('%m-%d')})"
    else:
        action, position_pct, position_text = "观望", 20, "二成仓"  # P3-修改：无信号默认20%
        reason = "无明确买卖点信号"

    # Calculate stop loss / targets based on latest zhongshu or bi
    if zhongshu_list:
        last_zs = zhongshu_list[-1]
        if bi_list:
            last_bi = bi_list[-1]
            stop_loss = last_zs['ZD'] if last_bi['direction'] == 'up' else last_zs['ZG']
            target1 = last_zs['ZG'] * 1.05 if last_bi['direction'] == 'up' else last_zs['ZD'] * 0.95
            target2 = last_zs['ZG'] * 1.10 if last_bi['direction'] == 'up' else last_zs['ZD'] * 0.90
        else:
            stop_loss = last_zs['ZD']
            target1 = last_zs['ZG']
            target2 = last_zs['ZG'] * 1.05
    elif bi_list:
        last_bi = bi_list[-1]
        stop_loss = last_bi['end_price'] * 0.97 if last_bi['direction'] == 'up' else last_bi['end_price'] * 1.03
        target1 = last_bi['end_price'] * 1.05 if last_bi['direction'] == 'up' else last_bi['end_price'] * 0.95
        target2 = last_bi['end_price'] * 1.10 if last_bi['direction'] == 'up' else last_bi['end_price'] * 0.90
    else:
        stop_loss = last_price * 0.95
        target1 = last_price * 1.05
        target2 = last_price * 1.10

    return action, position_pct, position_text, stop_loss, target1, target2, reason


# ============================================================
# 图表绘制
# ============================================================

def plot_charts(df, bi_list, zhongshu_list, xduan_list, signals, divergences, dif, dea, macd, sub_zhongshu_list=None, period='d'):
    """绘制缠论分析图表"""
    if sub_zhongshu_list is None:
        sub_zhongshu_list = []
    if df is None or len(df) < 5:
        return None

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.55, 0.25, 0.20],
        vertical_spacing=0.03,
        subplot_titles=('', 'MACD指标', '成交量')
    )

    # === Row 1: K线图 ===
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        increasing_line_color='#FF4444',
        increasing_fillcolor='#FF4444',
        decreasing_line_color='#00CC00',
        decreasing_fillcolor='#00CC00',
        name='K线',
        legendgroup='kline'
    ), row=1, col=1)

    # 均线
    ma_configs = [(5, '#FFD700'), (10, '#00FFFF'), (20, '#FF00FF'), (60, '#FFFFFF')]
    for period, color in ma_configs:
        if len(df) >= period:
            ma = df['close'].rolling(period).mean()
            fig.add_trace(go.Scatter(
                x=df.index, y=ma,
                name=f'MA{period}',
                line=dict(color=color, width=1),
                legendgroup='ma'
            ), row=1, col=1)

    # 笔
    for bi in bi_list:
        color = '#00FF88' if bi['direction'] == 'up' else '#FF4444'
        try:
            df.index.get_loc(bi['start_date'])
            df.index.get_loc(bi['end_date'])
        except KeyError:
            continue
        fig.add_trace(go.Scatter(
            x=[bi['start_date'], bi['end_date']],
            y=[bi['start_price'], bi['end_price']],
            mode='lines+markers',
            line=dict(color=color, width=2.5),
            marker=dict(size=6, symbol='circle'),
            showlegend=False,
            hoverinfo='skip',
            legendgroup='bi'
        ), row=1, col=1)

    # 中枢
    for zs in zhongshu_list:
        fig.add_shape(
            type='rect',
            x0=zs['start_date'], x1=zs['end_date'],
            y0=zs['ZD'], y1=zs['ZG'],
            fillcolor='rgba(128,128,128,0.15)',
            line=dict(color='rgba(200,200,200,0.6)', width=1.5),
            layer='below',
            row=1, col=1
        )
        fig.add_hline(
            y=zs['ZZ'],
            line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'),
            annotation_text=f"中枢中价 {zs['ZZ']:.2f}",
            annotation_position="right",
            row=1, col=1
        )

    # === 次级别中枢（用更浅的颜色）===
    for sub_zs in sub_zhongshu_list:
        fig.add_shape(
            type='rect',
            x0=sub_zs['start_date'], x1=sub_zs['end_date'],
            y0=sub_zs['ZD'], y1=sub_zs['ZG'],
            fillcolor='rgba(100,100,200,0.12)',
            line=dict(color='rgba(120,120,220,0.5)', width=1, dash='dot'),
            layer='below',
            row=1, col=1
        )

    # === Color-coded buy signals ===
    buy_sigs = [s for s in signals if s['side'] == 'buy']
    if buy_sigs:
        buy_x, buy_y, buy_texts, buy_colors, buy_reasons = [], [], [], [], []
        for s in buy_sigs:
            try:
                y_val = df.loc[s['date'], 'low'] * 0.995
            except KeyError:
                y_val = s['price'] * 0.995
            buy_x.append(s['date'])
            buy_y.append(y_val)
            buy_texts.append(s['type'])
            buy_colors.append(s.get('color', '#FF0000'))
            buy_reasons.append([s['reason']])

        fig.add_trace(go.Scatter(
            x=buy_x, y=buy_y,
            mode='markers+text',
            marker=dict(symbol='triangle-up', size=18,
                        color=buy_colors,
                        line=dict(color='#FFF', width=1)),
            text=buy_texts,
            textposition='bottom center',
            textfont=dict(color=buy_colors, size=11, family='Arial Black'),
            customdata=buy_reasons,
            hovertemplate='<b>%{text}</b><br>%{customdata[0]}<extra></extra>',
            name='买点',
            legendgroup='buy'
        ), row=1, col=1)

    # === Color-coded sell signals ===
    sell_sigs = [s for s in signals if s['side'] == 'sell']
    if sell_sigs:
        sell_x, sell_y, sell_texts, sell_colors, sell_reasons = [], [], [], [], []
        for s in sell_sigs:
            try:
                y_val = df.loc[s['date'], 'high'] * 1.005
            except KeyError:
                y_val = s['price'] * 1.005
            sell_x.append(s['date'])
            sell_y.append(y_val)
            sell_texts.append(s['type'])
            sell_colors.append(s.get('color', '#00FF00'))
            sell_reasons.append([s['reason']])

        fig.add_trace(go.Scatter(
            x=sell_x, y=sell_y,
            mode='markers+text',
            marker=dict(symbol='triangle-down', size=18,
                        color=sell_colors,
                        line=dict(color='#FFF', width=1)),
            text=sell_texts,
            textposition='top center',
            textfont=dict(color=sell_colors, size=11, family='Arial Black'),
            customdata=sell_reasons,
            hovertemplate='<b>%{text}</b><br>%{customdata[0]}<extra></extra>',
            name='卖点',
            legendgroup='sell'
        ), row=1, col=1)

    # === Row 2: MACD ===
    fig.add_trace(go.Scatter(
        x=df.index, y=dif,
        name='DIF',
        line=dict(color='#00BFFF', width=1.5),
        legendgroup='macd'
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=dea,
        name='DEA',
        line=dict(color='#FFA500', width=1.5),
        legendgroup='macd'
    ), row=2, col=1)

    macd_colors = ['#FF4444' if v >= 0 else '#00CC00' for v in macd]
    fig.add_trace(go.Bar(
        x=df.index, y=macd,
        marker_color=macd_colors,
        name='MACD柱',
        legendgroup='macd'
    ), row=2, col=1)

    # 金叉死叉
    golden, dead = [], []
    for i in range(1, len(dif)):
        if (pd.notna(dif.iloc[i]) and pd.notna(dea.iloc[i]) and
                pd.notna(dif.iloc[i - 1]) and pd.notna(dea.iloc[i - 1])):
            if dif.iloc[i] > dea.iloc[i] and dif.iloc[i - 1] <= dea.iloc[i - 1]:
                golden.append((df.index[i], dif.iloc[i]))
            elif dif.iloc[i] < dea.iloc[i] and dif.iloc[i - 1] >= dea.iloc[i - 1]:
                dead.append((df.index[i], dif.iloc[i]))

    if golden:
        fig.add_trace(go.Scatter(
            x=[g[0] for g in golden], y=[g[1] for g in golden],
            mode='markers+text',
            marker=dict(symbol='triangle-up', size=10, color='#00FF00'),
            text=['金叉'] * len(golden),
            textposition='bottom center',
            textfont=dict(color='#00FF00', size=9),
            showlegend=False
        ), row=2, col=1)

    if dead:
        fig.add_trace(go.Scatter(
            x=[d[0] for d in dead], y=[d[1] for d in dead],
            mode='markers+text',
            marker=dict(symbol='triangle-down', size=10, color='#FF0000'),
            text=['死叉'] * len(dead),
            textposition='top center',
            textfont=dict(color='#FF0000', size=9),
            showlegend=False
        ), row=2, col=1)

    # P0-11: 背驰段标注 — 在MACD柱状图上用箭头标出
    level_map = {'d': '日线', '60': '60分钟', '30': '30分钟', '15': '15分钟', '5': '5分钟'}
    level = level_map.get(period, '日线')
    
    for div in divergences:
        div_color = '#00FF00' if 'bottom' in div['type'] else '#FF0000'
        div_label = f"{level}{'趋势' if 'trend' in div.get('type', '') else '盘整'}背驰段"
        
        try:
            # 找到背驰段对应的MACD柱位置
            div_y = macd.iloc[df.index.get_loc(div['date'])] if div['date'] in df.index else 0
            div_y = div_y if pd.notna(div_y) else 0
        except (KeyError, ValueError):
            div_y = 0

        # 添加箭头标记
        fig.add_trace(go.Scatter(
            x=[div['date']],
            y=[div_y],
            mode='markers',
            marker=dict(
                symbol='triangle-up' if 'bottom' in div['type'] else 'triangle-down',
                size=14,
                color=div_color,
                line=dict(color='#FFFFFF', width=1)
            ),
            customdata=[[div_label]],
            hovertemplate=f'<b>{div_label}</b><br>%{{customdata[0]}}<extra></extra>',
            showlegend=False
        ), row=2, col=1)
        
        # 添加文字标注
        fig.add_annotation(
            x=div['date'], y=div_y,
            text=f"<b>{div['label']}</b>",
            showarrow=True,
            arrowhead=2,
            arrowcolor=div_color,
            font=dict(color=div_color, size=11),
            row=2, col=1
        )

    # === Row 3: 成交量 ===
    vol_ma5 = df['volume'].rolling(5).mean()
    vol_colors = []
    for i in range(len(df)):
        is_up = df['close'].iloc[i] >= df['open'].iloc[i]
        is_huge = (df['volume'].iloc[i] > vol_ma5.iloc[i] * 1.5
                   if pd.notna(vol_ma5.iloc[i]) else False)
        if is_up:
            c = '#FFFF00' if is_huge else '#FF4444'
        else:
            c = '#FFFF00' if is_huge else '#00CC00'
        vol_colors.append(c)

    fig.add_trace(go.Bar(
        x=df.index, y=df['volume'],
        marker_color=vol_colors,
        name='成交量',
        legendgroup='vol'
    ), row=3, col=1)

    # === 布局设置 ===
    fig.update_layout(
        paper_bgcolor='#131722',
        plot_bgcolor='#131722',
        font=dict(color='#D1D4DC', size=11),
        height=900,
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        legend=dict(
            bgcolor='rgba(0,0,0,0)',
            font=dict(size=10, color='#D1D4DC'),
            orientation='h',
            x=0.5, y=1.02, xanchor='center'
        ),
        margin=dict(t=60, b=40),
        showlegend=True
    )

    for i in range(1, 4):
        fig.update_xaxes(gridcolor='#2B2B43', showgrid=True, zeroline=False, row=i, col=1)
        fig.update_yaxes(gridcolor='#2B2B43', showgrid=True, zeroline=False, row=i, col=1)

    return fig


# ============================================================
# 主程序入口 — P0-1/2/3: data range binding
# ============================================================

def main():
    # --- 侧边栏 ---
    st.sidebar.title("DragonX 缠论系统 v2")
    st.sidebar.markdown("---")

    # 自选股
    DEFAULT_WATCHLIST = [
        ("000001", "平安银行"), ("600519", "贵州茅台"),
        ("601899", "紫金矿业"), ("000858", "五粮液"),
        ("300750", "宁德时代"),
    ]

    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = DEFAULT_WATCHLIST.copy()

    st.sidebar.subheader("自选股")
    options = [f"{c} {n}" for c, n in st.session_state.watchlist]
    selected = st.sidebar.radio("选择", options, key="stock_select")
    code_input = selected.split()[0]

    # 周期选择
    st.sidebar.markdown("---")
    st.sidebar.subheader("K线周期")
    PERIOD_MAP = {"日线": "d", "60分钟": "60", "30分钟": "30", "15分钟": "15", "5分钟": "5"}
    period_label = st.sidebar.selectbox("周期", list(PERIOD_MAP.keys()), key="period_select")
    period = PERIOD_MAP[period_label]

    # P0-9: 数据范围 — 严格按天数计算
    st.sidebar.subheader("数据范围")
    RANGE_MAP = {"1个月": 30, "3个月": 90, "半年": 180, "1年": 365, "2年": 730}
    range_label = st.sidebar.selectbox("范围", list(RANGE_MAP.keys()), key="range_select")
    days = RANGE_MAP[range_label]  # 实际天数

    # 添加股票
    st.sidebar.markdown("---")
    new_code = st.sidebar.text_input("添加股票代码", key="new_code_input")
    if st.sidebar.button("添加", key="add_stock_btn"):
        if new_code.strip():
            st.session_state.watchlist.append((new_code.strip(), new_code.strip()))
            st.rerun()

    # --- 主区域 ---
    st.title("DragonX 缠论智能分析 v2")

    # P0-9: 获取数据 — 严格按时间范围
    with st.spinner("正在获取数据..."):
        df = get_stock_data_baostock(code_input, period, days)  # 传入实际天数
        is_demo = df is None
        if is_demo:
            df = get_demo_data(days)  # 传入需要的天数
            st.warning("使用演示数据（真实数据获取失败）")

    if df is None or len(df) < 10:
        st.error("数据获取失败")
        return

    # P2-TASK-G: 检查数据是否满足要求的天数
    if not is_demo and len(df) > 0:
        actual_days = (df.index[-1] - df.index[0]).days
        expected_days = days
        # 日线：约260个交易日 = 1年
        # 对于日线，检查交易日数量
        if period == 'd':
            expected_trading_days = int(days * 260 / 365)  # 预估交易日数量
            actual_trading_days = len(df)
            if actual_trading_days < expected_trading_days * 0.9:  # 允许10%误差
                st.warning(f"⚠️ 仅获取到约{actual_trading_days}个交易日数据（预期约{expected_trading_days}个），可能因停牌或数据源限制")
        else:
            # 分钟线：检查天数覆盖
            if actual_days < expected_days * 0.9:
                st.warning(f"⚠️ 仅获取到约{actual_days}天数据（不足{range_label}）")

    # 显示股票信息
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        name = get_stock_name_baostock(code_input) if not is_demo else "演示股票"
        st.metric("股票名称", name)
    with col2:
        st.metric("股票代码", code_input)
    with col3:
        st.metric("最新价", f"{df['close'].iloc[-1]:.2f}")
    with col4:
        pct = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
        st.metric("涨跌", f"{pct:+.2f}%")

    st.markdown("---")

    # ============================================================
    # P0-1/2/3: ALL calculations operate ONLY on the range-selected df
    # ============================================================
    with st.spinner("正在分析缠论结构..."):
        df_proc = process_containment(df)        # Process only selected range
        fractals = detect_fractals(df_proc)      # Detect within range
        bi_list, valid_fractals = detect_bi(fractals)     # Bi within range
        zhongshu_list, sub_zhongshu_list = detect_zhongshu(bi_list)  # Main and sub zhongshu
        xduan_list = detect_xduan(bi_list, zhongshu_list)
        dif, dea, macd = detect_macd(df)
        divergences = detect_divergence(df, bi_list, dif, dea)
        signals = detect_buy_sell_points(bi_list, zhongshu_list, divergences)

        # P0-D: 笔方向与信号强制一致
        bi_direction, zs_range = analyze_trend(bi_list, zhongshu_list, signals)

        # P1-7: Fixed beichi status with level annotation
        beichi_status = detect_beichi_status(bi_list, divergences, zhongshu_list, period)

        # P0-6: Fixed decision with reason
        last_price = df['close'].iloc[-1]
        (action, position_pct, position_text,
         stop_loss, target1, target2, decision_reason) = generate_decision(
            df, bi_list, zhongshu_list, signals, last_price
        )
        
        # P1-TASK-F + P0-TASK-J: 中枢位置关系智能提示（含信号冲突处理）
        zs_position_hint, zs_hint_color = analyze_zhongshu_relation(zhongshu_list, sub_zhongshu_list, action)

    # 布局：图表 + 决策面板
    col_chart, col_decision = st.columns([3, 1])

    with col_chart:
        fig = plot_charts(df, bi_list, zhongshu_list, xduan_list,
                          signals, divergences, dif, dea, macd, sub_zhongshu_list, period)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("图表生成失败")

    with col_decision:
        # P2-TASK-L: 折叠/展开功能
        if 'panel_expanded' not in st.session_state:
            st.session_state.panel_expanded = True
        
        col_toggle, col_title = st.columns([1, 4])
        with col_toggle:
            if st.button("◀" if st.session_state.panel_expanded else "▶", 
                        key="toggle_panel_btn", help="折叠/展开面板"):
                st.session_state.panel_expanded = not st.session_state.panel_expanded
        
        # P2-TASK-M: 操作建议视觉强化（颜色+图标+背景）
        action_config = {
            '买入': {'color': '#00C853', 'icon': '↑', 'bg': 'rgba(0,200,83,0.15)'},
            '加仓': {'color': '#00C853', 'icon': '↑', 'bg': 'rgba(0,200,83,0.15)'},
            '卖出': {'color': '#FF3B30', 'icon': '↓', 'bg': 'rgba(255,59,48,0.15)'},
            '减仓': {'color': '#FF3B30', 'icon': '↓', 'bg': 'rgba(255,59,48,0.15)'},
            '反弹卖出': {'color': '#FF3B30', 'icon': '↓', 'bg': 'rgba(255,59,48,0.15)'},
            '持有': {'color': '#2196F3', 'icon': '●', 'bg': 'rgba(33,150,243,0.15)'},
            '观望': {'color': '#9E9E9E', 'icon': '—', 'bg': 'rgba(158,158,158,0.15)'}
        }
        config = action_config.get(action, {'color': '#888888', 'icon': '—', 'bg': 'rgba(136,136,136,0.15)'})
        
        st.markdown(f"""
        <div style="text-align:center;padding:15px;border:3px solid {config['color']};border-radius:10px;margin-bottom:10px;background:{config['bg']}">
            <div style="font-size:1rem;color:#888">操作建议</div>
            <div style="font-size:2.5rem;font-weight:bold;color:{config['color']}">{config['icon']} {action}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.panel_expanded:
            # 完整面板内容
            st.markdown(f"**决策依据：** {decision_reason}")
            
            # P3-TASK-O: 动态操作提醒
            action_reminders = {
                '买入': f"📌 关注：是否形成二买信号 / 止损位 {stop_loss:.2f}" if stop_loss else "📌 关注：是否形成二买信号",
                '加仓': f"📌 关注：趋势确认中 / 止损位 {stop_loss:.2f}" if stop_loss else "📌 关注：趋势确认中",
                '持有': "📌 关注：是否出现顶背驰 / 三买区域突破",
                '卖出': "📌 关注：是否回到中枢内 / 次级别背驰",
                '减仓': "📌 关注：下跌力度 / 支撑位测试",
                '反弹卖出': "📌 关注：中枢上沿压力 / 是否形成三卖",
                '观望': "⏳ 等待：一买或三买信号出现"
            }
            reminder = action_reminders.get(action, "⏳ 等待明确信号")
            st.caption(reminder)

            # P0-TASK-I: 仓位与操作建议联动（风控）
            position_limits = {
                '买入': 80, '加仓': 80, '持有': 60,
                '观望': 30, '减仓': 20,
                '卖出': 10, '反弹卖出': 10
            }
            position_limit = position_limits.get(action, 30)
            
            if position_pct > position_limit:
                position_pct = position_limit
            
            if 'system_position' not in st.session_state:
                st.session_state.system_position = position_pct
            else:
                st.session_state.system_position = position_pct
            
            st.markdown("**建议仓位**")
            st.progress(position_pct / 100)
            st.write(f"系统建议：{position_text} ({position_pct}%)")
            st.caption(f"⚠️ 当前建议[{action}]，仓位上限 {position_limit}%")
            
            # 用户手动覆盖仓位（P2-TASK-N: 内嵌滑块）
            user_position = st.slider("手动调整仓位", 0, 100, position_pct, 5, key="user_position_slider")
            
            col_reset_info, col_reset_btn = st.columns([3, 1])
            with col_reset_btn:
                reset_clicked = st.button("重置", key="reset_position_btn", help="恢复为系统建议仓位")
            
            if 'position_history' not in st.session_state:
                st.session_state.position_history = []
            if 'override_confirmed' not in st.session_state:
                st.session_state.override_confirmed = False
            
            if reset_clicked:
                st.session_state.user_position_slider = position_limit
                st.session_state.override_confirmed = False
                user_position = position_limit
            
            # 超限警告
            if user_position > position_limit and user_position != position_pct:
                st.warning(f"⚠️ 当前建议[{action}]，仓位建议不超过{position_limit}%，确认继续吗？")
                col_confirm, col_cancel = st.columns(2)
                with col_confirm:
                    if st.button("确认覆盖", key="confirm_override_btn"):
                        st.session_state.override_confirmed = True
                with col_cancel:
                    if st.button("取消", key="cancel_override_btn"):
                        st.session_state.user_position_slider = position_limit
                        st.session_state.override_confirmed = False
                        user_position = position_limit
            
            # 显示状态
            if user_position != position_pct:
                if user_position > position_limit:
                    status_color = '#FF4444' if st.session_state.override_confirmed else '#FFD700'
                    status_text = '用户自定义（超限）' if st.session_state.override_confirmed else '用户自定义（待确认）'
                else:
                    status_color = '#FFD700'
                    status_text = '用户自定义'
                st.markdown(f"<span style='color:{status_color}'>{status_text}：{user_position}%</span>", unsafe_allow_html=True)
                position_pct = user_position
            else:
                st.markdown("<span style='color:#888888'>使用系统建议</span>", unsafe_allow_html=True)
            
            if st.session_state.position_history:
                with st.expander("修改历史", expanded=False):
                    for record in st.session_state.position_history[-3:]:
                        st.write(record)
            
            st.markdown("---")
            
            # 关键价位
            st.markdown("**关键价位**")
            if stop_loss:
                st.markdown(f"<span style='color:#FF4444'>止损: {stop_loss:.2f}</span>", unsafe_allow_html=True)
            if target1:
                st.markdown(f"<span style='color:#00FF88'>目标1: {target1:.2f}</span>", unsafe_allow_html=True)
            if target2:
                st.markdown(f"<span style='color:#00CC66'>目标2: {target2:.2f}</span>", unsafe_allow_html=True)
            
            st.markdown("---")
            
            # 缠论状态
            st.markdown("**缠论状态**")
            st.write(f"笔方向: {bi_direction}")
            
            if zhongshu_list:
                last_zs = zhongshu_list[-1]
                st.write(f"**本级中枢**：{last_zs['ZD']:.2f}–{last_zs['ZG']:.2f}")
            else:
                st.write("**本级中枢**：无中枢")
            
            if sub_zhongshu_list:
                last_sub_zs = sub_zhongshu_list[-1]
                st.write(f"**次级别中枢**：{last_sub_zs['ZD']:.2f}–{last_sub_zs['ZG']:.2f}")
            
            if zs_position_hint:
                st.markdown(f"<div style='background:rgba(255,255,255,0.1);padding:8px;border-radius:4px;margin:5px 0'><span style='color:{zs_hint_color};font-weight:bold'>{zs_position_hint}</span></div>", unsafe_allow_html=True)
            
            st.write(f"背驰: {beichi_status}")
            
            st.markdown("---")
            
            # 分析基准
            range_text = {
                "1个月": "1个月", "3个月": "3个月",
                "半年": "6个月", "1年": "12个月", "2年": "24个月"
            }[range_label]
            st.write(f"**分析基准**：近{range_text}")
            
            st.markdown("---")
            
            # 买卖点列表
            st.markdown("**最近买卖点**")
            if signals:
                recent = sorted(signals, key=lambda x: x['date'], reverse=True)[:max(3, len(signals))]
                highlight_type = None
                if decision_reason and '：' in decision_reason:
                    parts = decision_reason.split('：')
                    if len(parts) >= 2:
                        signal_part = parts[1].split()[0] if ' ' in parts[1] else parts[1].split('(')[0]
                        highlight_type = signal_part.strip()
                
                for s in recent:
                    date_str = s['date'].strftime('%m-%d') if hasattr(s['date'], 'strftime') else str(s['date'])[:5]
                    sig_color = s.get('color', '#FF4444' if s['side'] == 'buy' else '#00CC00')
                    is_highlight = highlight_type and (highlight_type in s['type'] or s['type'] in highlight_type)
                    if is_highlight:
                        st.markdown(
                            f"<div style='background:rgba(255,200,0,0.2);padding:5px;border-radius:4px;border-left:3px solid #FFD700'><b style='color:{sig_color}'>{date_str} {s['type']} {s['price']:.2f}</b><span style='color:#FFD700;font-size:0.75em'> ◀ 决策依据</span></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(f"<span style='color:{sig_color}'>{date_str} {s['type']} {s['price']:.2f}</span>", unsafe_allow_html=True)
            else:
                st.info("暂无历史买卖点，请扩大数据范围或等待信号生成")
        else:
            # 折叠状态：只显示简略信息
            st.caption(f"点击 ◀ 展开详情 | {action} | 仓位 {position_pct}%")

        # P0-TASK-I: 仓位与操作建议联动（风控）
        # 根据操作建议确定仓位上限
        position_limits = {
            '买入': 80, '加仓': 80, '持有': 60,
            '观望': 30, '减仓': 20,
            '卖出': 10, '反弹卖出': 10
        }
        position_limit = position_limits.get(action, 30)
        
        # 系统建议仓位不能超过上限
        if position_pct > position_limit:
            position_pct = position_limit
        
        # 保存系统建议值到 session_state
        if 'system_position' not in st.session_state:
            st.session_state.system_position = position_pct
        else:
            st.session_state.system_position = position_pct
        
        st.markdown("**建议仓位**")
        st.progress(position_pct / 100)
        st.write(f"系统建议：{position_text} ({position_pct}%)")
        st.caption(f"⚠️ 当前建议[{action}]，仓位上限 {position_limit}%")
        
        # 用户手动覆盖仓位（折叠状态）
        col_slider, col_reset = st.columns([4, 1])
        with col_slider:
            user_position = st.slider("手动调整仓位", 0, 100, position_pct, key="user_position_slider_collapsed")
        
        with col_reset:
            reset_clicked = st.button("重置", key="reset_position_btn_collapsed", help="恢复为系统建议仓位")
        
        # 初始化仓位历史记录和超限确认状态
        if 'position_history' not in st.session_state:
            st.session_state.position_history = []
        if 'override_confirmed' not in st.session_state:
            st.session_state.override_confirmed = False
        
        # 处理重置按钮
        if reset_clicked:
            st.session_state.user_position_slider_collapsed = position_limit
            st.session_state.override_confirmed = False
            user_position = position_limit
            st.session_state.position_history.append(
                f"[{datetime.now().strftime('%H:%M')}] 用户重置仓位为系统建议 {position_limit}%"
            )
        
        # P0-TASK-I: 检测超限并弹出警告确认框（折叠状态）
        if user_position > position_limit and user_position != position_pct:
            st.warning(f"⚠️ 当前建议[{action}]，仓位建议不超过{position_limit}%，确认继续吗？")
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                if st.button("确认覆盖", key="confirm_override_btn_collapsed"):
                    st.session_state.override_confirmed = True
                    st.session_state.position_history.append(
                        f"[{datetime.now().strftime('%H:%M')}] 用户确认超限：仓位调整为 {user_position}%"
                    )
            with col_cancel:
                if st.button("取消", key="cancel_override_btn_collapsed"):
                    st.session_state.user_position_slider_collapsed = position_limit
                    st.session_state.override_confirmed = False
                    user_position = position_limit
        
        # 显示当前仓位状态
        if user_position != position_pct:
            if user_position > position_limit and st.session_state.override_confirmed:
                st.markdown(f"<span style='color:#FF4444'>用户自定义（超限）：{user_position}%</span>", unsafe_allow_html=True)
            elif user_position > position_limit:
                st.markdown(f"<span style='color:#FFD700'>用户自定义：{user_position}%（待确认）</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"<span style='color:#FFD700'>用户自定义：{user_position}%</span>", unsafe_allow_html=True)
            position_pct = user_position
            
            # 记录修改历史
            if (not st.session_state.position_history or 
                not st.session_state.position_history[-1].endswith(f"{user_position}%")):
                st.session_state.position_history.append(
                    f"[{datetime.now().strftime('%H:%M')}] 用户将仓位调整为 {user_position}%"
                )
        else:
            st.markdown(f"<span style='color:#888888'>使用系统建议</span>", unsafe_allow_html=True)
        
        # 显示最近3条修改历史（折叠显示）
        if st.session_state.position_history:
            with st.expander("修改历史", expanded=False):
                for record in st.session_state.position_history[-3:]:
                    st.write(record)

        st.markdown("---")

        # 关键价位
        st.markdown("**关键价位**")
        if stop_loss:
            st.markdown(f"<span style='color:#FF4444'>止损: {stop_loss:.2f}</span>", unsafe_allow_html=True)
        if target1:
            st.markdown(f"<span style='color:#00FF88'>目标1: {target1:.2f}</span>", unsafe_allow_html=True)
        if target2:
            st.markdown(f"<span style='color:#00CC66'>目标2: {target2:.2f}</span>", unsafe_allow_html=True)

        st.markdown("---")

        # 缠论状态
        st.markdown("**缠论状态**")
        st.write(f"笔方向: {bi_direction}")

        # P2-1/6: Zhongshu display - separate main and sub level
        if zhongshu_list:
            last_zs = zhongshu_list[-1]
            st.write(f"**本级中枢**：{last_zs['ZD']:.2f}–{last_zs['ZG']:.2f}")
        else:
            st.write("**本级中枢**：无中枢")

        # 显示次级别中枢（如果有）
        if sub_zhongshu_list:
            last_sub_zs = sub_zhongshu_list[-1]
            st.write(f"**次级别中枢**：{last_sub_zs['ZD']:.2f}–{last_sub_zs['ZG']:.2f}")

        # P1-TASK-F: 显示中枢位置关系提示
        if zs_position_hint:
            st.markdown(f"<div style='background:rgba(255,255,255,0.1);padding:8px;border-radius:4px;margin:5px 0'><span style='color:{zs_hint_color};font-weight:bold'>{zs_position_hint}</span></div>", unsafe_allow_html=True)

        st.write(f"背驰: {beichi_status}")

        st.markdown("---")

        # P0-1/2/3: Show analysis range
        range_text = {
            "1个月": "1个月", "3个月": "3个月",
            "半年": "6个月", "1年": "12个月", "2年": "24个月"
        }[range_label]
        st.write(f"**分析基准**：近{range_text}")

        st.markdown("---")

        # P2-修改：买卖点列表 — 显示至少3个并高亮决策依据
        st.markdown("**最近买卖点**")
        if signals:
            # 按时间倒序排列，取至少3个
            recent = sorted(signals, key=lambda x: x['date'], reverse=True)[:max(3, len(signals))]
            
            # 从决策依据中提取高亮类型（如"一买"）
            highlight_type = None
            if decision_reason and '：' in decision_reason:
                # 格式：最近信号：一买 (03-09) 或 三卖(03-02)，3日内，建议卖出
                parts = decision_reason.split('：')
                if len(parts) >= 2:
                    # 提取类型（去掉括号中的日期）
                    signal_part = parts[1].split()[0] if ' ' in parts[1] else parts[1].split('(')[0]
                    highlight_type = signal_part.strip()
            
            for s in recent:
                date_str = (s['date'].strftime('%m-%d')
                            if hasattr(s['date'], 'strftime')
                            else str(s['date'])[:5])
                sig_color = s.get('color', '#FF4444' if s['side'] == 'buy' else '#00CC00')
                
                # P2-高亮：决策依据中的买卖点用加粗+背景色
                is_highlight = highlight_type and (highlight_type in s['type'] or s['type'] in highlight_type)
                if is_highlight:
                    st.markdown(
                        f"<div style='background:rgba(255,200,0,0.2);padding:5px;border-radius:4px;border-left:3px solid #FFD700'>"
                        f"<b style='color:{sig_color}'>{date_str} {s['type']} {s['price']:.2f}</b>"
                        f" <span style='color:#FFD700;font-size:0.75em'>◀ 决策依据</span></div>",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f"<span style='color:{sig_color}'>{date_str} {s['type']} {s['price']:.2f}</span>",
                        unsafe_allow_html=True
                    )
        else:
            st.info("暂无历史买卖点，请扩大数据范围或等待信号生成")


if __name__ == "__main__":
    main()
