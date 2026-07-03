# -*- coding: utf-8 -*-
"""
run_forecast.py — FCST预测系统 主入口 v3.0
三步走：加载数据 → 三层预测 → 写Excel
"""
import os, sys, pandas as pd
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import *
from data_loader import build_monthly_matrix
from forecast_engine import ForecastEngine
from sku_classifier import get_all_classifications
from output_writer import backup_template, write_predictions


def main():
    print('=' * 50)
    print('  FCST 销量预测系统 v3.0')
    print(f'  时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  渠道: {CHANNEL_NAME}')
    print('=' * 50)

    # === Step 1: 读取SKU列表 ===
    print('\n[1] 读取SKU列表...')
    df_actual = pd.read_excel(TEMPLATE_PATH, sheet_name=ACTUAL_SHEET)
    sku_list = df_actual['货品编码'].str.strip().tolist()
    print(f'  共 {len(sku_list)} 个SKU')

    # === Step 2: 加载历史数据 ===
    print('\n[2] 加载历史销售数据...')
    load_months = [f'2025-{m:02d}' for m in range(1,13)] + [f'2026-{m:02d}' for m in range(1,13)]
    matrix, seasonal = build_monthly_matrix(DATA_DIR, CHANNEL_NAME, sku_list, load_months)

    # 同步实际数据sheet中的1-6月值
    for _, row in df_actual.iterrows():
        sku = str(row['货品编码']).strip()
        for m in ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06']:
            v = row.get(m)
            if pd.notna(v) and m in matrix.columns:
                matrix.loc[sku, m] = int(v)

    # 打印季节性因子
    print(f'  季节性: {seasonal}')

    # === Step 3: 构建系列分组 ===
    print('\n[3] 构建SKU分类...')
    classifications = get_all_classifications(TEMPLATE_PATH)
    series_groups = {}
    for sku, cls in classifications.items():
        s = cls.get('series', '其他')
        if s not in series_groups:
            series_groups[s] = []
        series_groups[s].append(sku)
    print(f'  共 {len(series_groups)} 个系列')

    # === Step 4: 预测 ===
    print('\n[4] 运行三层预测引擎...')
    engine = ForecastEngine(matrix, seasonal)
    engine.series_groups = series_groups
    predictions = engine.run()

    # 统计
    total = 0
    for sku, p in predictions.items():
        total += sum(p.values())
    print(f'  7-11月预测总销量: {total} 件')

    # === Step 5: 写Excel ===
    print('\n[5] 写入预测结果...')
    backup_template(TEMPLATE_PATH)
    write_predictions(TEMPLATE_PATH, PREDICT_SHEET, predictions)

    # 摘要
    print(f'\n  达成: {int(total)} 件')

    # === Step 6: 导出JSON（供Web看板使用）===
    print('\n[6] 导出Web看板数据...')
    from export_web_json import export as export_json
    export_json(predictions=predictions)
    print('  [完成]')


if __name__ == '__main__':
    main()
