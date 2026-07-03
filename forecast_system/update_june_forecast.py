# -*- coding: utf-8 -*-
"""
更新SKU明细sheet：
1. 用26-6.xlsx实际数据更新6月件数/6月金额
2. 按6月实际颜色/尺寸权重，重新分配7-12月预测件数
"""
import os
import pandas as pd
import numpy as np

TEMPLATE_PATH = r'e:\FCST渠道预测看板系统\天猫预测-2026年销量预测.xlsx'
DATA_DIR = r'e:\FCST渠道预测看板系统\各渠道销售数据源'
CHANNEL_NAME = '直销_伊稻_电商_天猫ITO旗舰店'
MONTHS_LABEL = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']

# 加载6月日级数据
df_daily = pd.read_excel(os.path.join(DATA_DIR, '26-6.xlsx'))
ito = df_daily[df_daily['店铺'] == CHANNEL_NAME].copy()
ito['货品编号'] = ito['货品编号'].astype(str).str.strip()

# 按SKU汇总6月实际
actual_qty = ito.groupby('货品编号')['实际销售量'].sum().to_dict()
actual_amt = ito.groupby('货品编号')['实际销售额'].sum().to_dict()

# 读取SKU明细
df_sku = pd.read_excel(TEMPLATE_PATH, sheet_name='SKU明细')
df_sku['SKU编码'] = df_sku['SKU编码'].astype(str).str.strip()

# 确保件数/金额列为数值型
for col in df_sku.columns:
    if '件数' in col:
        df_sku[col] = df_sku[col].fillna(0).astype(float)
    if '金额' in col:
        df_sku[col] = df_sku[col].fillna(0).astype(float)

# 1. 更新6月件数/金额
print('=== 更新6月实际数据 ===')
for idx, r in df_sku.iterrows():
    sku = r['SKU编码']
    if sku in actual_qty:
        df_sku.at[idx, '6月件数'] = int(actual_qty[sku])
        df_sku.at[idx, '6月金额'] = round(actual_amt.get(sku, 0), 2)

# 显示几个新品变化
for ser in ['PISTACHIO PLUS STRIPED', 'PISTACHIO PLUS STRIPED TRUNK', 'PISTACHIO STRIPED TRUNK']:
    rows = df_sku[df_sku['系列'] == ser]
    print(f'\n=== {ser} 6月实际 ===')
    for _, r in rows.iterrows():
        print(f"  {r['SKU编码']} | {r['颜色']} {r['尺寸']} | 件数:{r['6月件数']} | 金额:{r['6月金额']:.0f}")

# 2. 按6月颜色/尺寸权重重新分配7-12月预测
def redistribute_forecast(series_rows):
    """对同一系列的SKU，按6月颜色/尺寸权重重新分配7-12月预测"""
    rows = series_rows.copy()
    colors = rows['颜色'].unique()
    sizes = rows['尺寸'].unique()
    
    # 计算6月颜色权重
    color_qty = rows.groupby('颜色')['6月件数'].sum()
    color_total = color_qty.sum()
    if color_total > 0:
        color_weight = (color_qty / color_total).to_dict()
    else:
        color_weight = {c: 1/len(colors) for c in colors}
    
    # 计算6月尺寸权重
    size_qty = rows.groupby('尺寸')['6月件数'].sum()
    size_total = size_qty.sum()
    if size_total > 0:
        size_weight = (size_qty / size_total).to_dict()
    else:
        size_weight = {s: 1/len(sizes) for s in sizes}
    
    # 保底权重：避免某些组合为0
    min_color_w = 0.1 / len(colors) if len(colors) > 0 else 0
    min_size_w = 0.1 / len(sizes) if len(sizes) > 0 else 0
    color_weight = {c: max(w, min_color_w) for c, w in color_weight.items()}
    size_weight = {s: max(w, min_size_w) for s, w in size_weight.items()}
    
    # 归一化
    cw_sum = sum(color_weight.values())
    sw_sum = sum(size_weight.values())
    color_weight = {c: w/cw_sum for c, w in color_weight.items()}
    size_weight = {s: w/sw_sum for s, w in size_weight.items()}
    
    # 对每个SKU计算联合权重
    sku_weight = {}
    for _, r in rows.iterrows():
        sku = r['SKU编码']
        sku_weight[sku] = color_weight.get(r['颜色'], 1/len(colors)) * size_weight.get(r['尺寸'], 1/len(sizes))
    
    # 重新分配7-11月（12月在SKU明细中不存在，保持export_web_json.py的推算逻辑）
    for month_idx in range(6, 11):  # 7-11月
        qty_col = f'{MONTHS_LABEL[month_idx]}件数'
        amt_col = f'{MONTHS_LABEL[month_idx]}金额'
        total_qty = rows[qty_col].sum()
        if total_qty <= 0:
            continue
        
        # 按权重分配，保留整数
        weights = np.array([sku_weight.get(r['SKU编码'], 0) for _, r in rows.iterrows()])
        weights = weights / weights.sum()
        new_qtys = np.round(total_qty * weights).astype(int)
        # 处理四舍五入误差
        diff = total_qty - new_qtys.sum()
        if diff != 0:
            # 加到权重最大的SKU
            max_idx = np.argmax(weights)
            new_qtys[max_idx] += diff
        
        for i, (idx, r) in enumerate(rows.iterrows()):
            sku = r['SKU编码']
            q = int(new_qtys[i])
            df_sku.at[idx, qty_col] = q
            # 金额 = 件数 × 吊牌价
            price = r['吊牌价'] if pd.notna(r['吊牌价']) else 0
            df_sku.at[idx, amt_col] = round(q * price, 2) if q > 0 and price > 0 else 0.0

print('\n=== 重新分配7-12月预测 ===')
for ser in df_sku['系列'].unique():
    rows = df_sku[df_sku['系列'] == ser]
    if len(rows) > 1:  # 只有多SKU的系列才需要重分配
        redistribute_forecast(rows)

# 显示新品重分配后的结果
for ser in ['PISTACHIO PLUS STRIPED', 'PISTACHIO PLUS STRIPED TRUNK', 'PISTACHIO STRIPED TRUNK']:
    rows = df_sku[df_sku['系列'] == ser]
    print(f'\n=== {ser} 7月预测（重分配后） ===')
    for _, r in rows.iterrows():
        print(f"  {r['颜色']} {r['尺寸']} | 7月件数:{r['7月件数']} | 7月金额:{r['7月金额']:.0f}")

# 写回Excel
with pd.ExcelWriter(TEMPLATE_PATH, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
    df_sku.to_excel(writer, sheet_name='SKU明细', index=False)

print('\n[完成] SKU明细sheet已更新保存')
