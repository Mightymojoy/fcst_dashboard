"""
data_loader.py — FCST销量预测系统 数据加载器
=======================
从各渠道数据源加载历史销售数据，聚合为月度SKU×月矩阵。
自动计算季节性指数。
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
from config import *


def discover_source_files(data_dir):
    """扫描数据源目录，发现所有可用历史文件。"""
    all_files = sorted([f for f in os.listdir(data_dir) if f.endswith('.xlsx')])
    return all_files


def load_channel_data(filepath, channel_name):
    """加载单个xlsx文件，筛选指定渠道的数据。"""
    try:
        df = pd.read_excel(filepath)
        channel_col = '店铺'
        if channel_col not in df.columns:
            return None, False
        channel_df = df[df[channel_col] == channel_name].copy()
        if len(channel_df) == 0:
            return None, False
        channel_df['日期'] = pd.to_datetime(channel_df['日期'], errors='coerce')
        channel_df = channel_df.dropna(subset=['日期'])
        return channel_df, True
    except Exception as e:
        return None, False


def build_monthly_matrix(data_dir, channel_name, sku_list, year_months):
    """构建SKU×月份的销量矩阵。"""
    files = discover_source_files(data_dir)
    print(f'[数据加载] 发现 {len(files)} 个源文件')

    matrix = pd.DataFrame(index=sku_list, columns=year_months).fillna(0)

    for f in files:
        fpath = os.path.join(data_dir, f)
        channel_df, ok = load_channel_data(fpath, channel_name)
        if not ok or len(channel_df) == 0:
            continue
        channel_df['年月'] = channel_df['日期'].dt.strftime('%Y-%m')
        for ym, group in channel_df.groupby('年月'):
            if ym in year_months:
                for _, row in group.iterrows():
                    sku = str(row['货品编号']).strip()
                    if sku in sku_list:
                        sales = row.get('实际销售量', 0)
                        if pd.notna(sales) and sales > 0:
                            try: matrix.loc[sku, ym] += int(sales)
                            except: pass

    print(f'[数据加载] 有数据的SKU数: {(matrix>0).any(axis=1).sum()}')
    return matrix, compute_seasonal_factors(data_dir, channel_name, sku_list)


def compute_seasonal_factors(data_dir, channel_name, sku_list=None):
    """基于2024-2025年数据计算季节性指数（仅限指定SKU列表）"""
    monthly_sales = {}
    files = discover_source_files(data_dir)
    sku_set = set(sku_list) if sku_list else None

    for f in files:
        fpath = os.path.join(data_dir, f)
        channel_df, ok = load_channel_data(fpath, channel_name)
        if not ok or len(channel_df) == 0:
            continue
        channel_df['年份'] = channel_df['日期'].dt.year
        channel_df = channel_df[channel_df['年份'].isin([2024, 2025])]
        if len(channel_df) == 0:
            continue
        # 如果指定了SKU列表，只统计匹配的SKU
        if sku_set:
            channel_df = channel_df[channel_df['货品编号'].isin(sku_set)]
        if len(channel_df) == 0:
            continue
        channel_df['年月'] = channel_df['日期'].dt.strftime('%Y-%m')
        for _, row in channel_df.iterrows():
            ym = row['年月']
            if ym not in monthly_sales:
                monthly_sales[ym] = 0
            monthly_sales[ym] += row.get('实际销售量', 0)

    if len(monthly_sales) < 12:
        return DEFAULT_SEASONAL_FACTORS.copy()

    month_sales = {}
    month_counts = {}
    for ym, total in monthly_sales.items():
        m = int(ym.split('-')[1])
        month_sales[m] = month_sales.get(m, 0) + total
        month_counts[m] = month_counts.get(m, 0) + 1

    # 计算各月均值
    month_avgs = {}
    for m in range(1, 13):
        if m in month_sales and month_counts[m] > 0:
            month_avgs[m] = month_sales[m] / month_counts[m]

    if not month_avgs:
        return DEFAULT_SEASONAL_FACTORS.copy()

    # 基准 = 12个月均值的平均值
    baseline = np.mean(list(month_avgs.values()))

    factors = {}
    for m in range(1, 13):
        if m in month_avgs and baseline > 0:
            factors[m] = round(month_avgs[m] / baseline, 4)
        else:
            factors[m] = DEFAULT_SEASONAL_FACTORS.get(m, 1.0)

    return factors


def classify_skus(sku_avgs, sku_list):
    """基于月均销量对SKU分T1/T2/T3层。"""
    tier1, tier2, tier3 = [], [], []
    for sku in sku_list:
        avg = sku_avgs.get(sku, 0)
        if avg >= TIER1_THRESHOLD: tier1.append(sku)
        elif avg >= TIER2_THRESHOLD: tier2.append(sku)
        else: tier3.append(sku)
    return tier1, tier2, tier3
