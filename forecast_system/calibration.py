"""
calibration.py — 月度验真系统
================================
预测 vs 实际对比校准，自动输出偏差分析。

使用时机：每月初，当月实际数据回填后运行。
命令：python calibration.py 2026-07
"""

import os, sys, pandas as pd, numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
from sku_classifier import get_classification


class Calibrator:
    """月度验真器：预测 vs 实际"""

    def __init__(self, month_key):
        """
        month_key: '2026-07' 等
        """
        self.month_key = month_key
        self.month_num = int(month_key.split('-')[1])

    # ============================================================
    # 1. 加载数据
    # ============================================================
    def load_data(self):
        """加载该月的预测数据和实际数据"""
        # 读取预测
        df_pred = pd.read_excel(TEMPLATE_PATH, sheet_name=PREDICT_SHEET)
        sku_predictions = {}
        for _, r in df_pred.iterrows():
            sku = str(r['货品编码']).strip()
            v = r.get(self.month_key, 0)
            if pd.notna(v):
                sku_predictions[sku] = int(v)

        # 从源数据读取实际（匹配B列SKU）
        fname = f'26-{self.month_num}.xlsx' if self.month_num <= 12 else None
        if fname:
            fpath = os.path.join(DATA_DIR, fname)
            if os.path.exists(fpath):
                df = pd.read_excel(fpath)
                ito = df[df['店铺'] == CHANNEL_NAME]
                matched = ito[ito['货品编号'].isin(sku_predictions.keys())]

                sku_actuals = {}
                for _, r in matched.iterrows():
                    sku = r['货品编号']
                    qty = int(r['实际销售量'])
                    rev = float(r['实际销售额'])
                    if sku not in sku_actuals:
                        sku_actuals[sku] = {'qty': 0, 'rev': 0.0}
                    sku_actuals[sku]['qty'] += qty
                    sku_actuals[sku]['rev'] += rev

                self.sku_predictions = sku_predictions
                self.sku_actuals = sku_actuals
                self.has_data = True
                return sku_predictions, sku_actuals

        self.sku_predictions = sku_predictions
        self.sku_actuals = {}
        self.has_data = False
        return sku_predictions, {}

    # ============================================================
    # 2. 运行验真
    # ============================================================
    def run_verification(self):
        """
        运行全维度验真，返回验真报告

        返回: {
            'sku_level': [{sku, series, color, size, pred_qty, pred_rev, actual_qty, actual_rev, qty_dev, rev_dev}, ...],
            'series_level': [{series, pred_qty, actual_qty, pred_rev, actual_rev, qty_acc, rev_acc}, ...],
            'color_level': [{series, color, pred_qty, actual_qty, share_dev}, ...],
            'size_level': [{series, size, pred_qty, actual_qty, share_dev}, ...],
            'summary': {total_pred, total_actual, total_pred_rev, total_actual_rev, qty_accuracy, rev_accuracy}
        }
        """
        self.load_data()
        predictions = self.sku_predictions
        actuals = self.sku_actuals

        # --- SKU级验真 ---
        sku_level = []
        for sku, pred_qty in predictions.items():
            pred_rev = pred_qty * 1000  # 默认均价，后面用实际价格替换
            cls = get_classification(sku, '')
            act = actuals.get(sku, {'qty': 0, 'rev': 0.0})
            actual_qty = act['qty']
            actual_rev = act['rev']

            # 找均价
            price = 1000
            if actual_qty > 0:
                price = actual_rev / actual_qty
            elif hasattr(self, 'sku_prices') and sku in self.sku_prices:
                price = self.sku_prices[sku]
            pred_rev = pred_qty * price

            qty_dev = actual_qty - pred_qty
            rev_dev = actual_rev - pred_rev

            sku_level.append({
                'sku': sku,
                '系列': cls.get('series', ''),
                '颜色': cls.get('color', ''),
                '尺寸': cls.get('size', ''),
                '预测件数': pred_qty,
                '预测金额': round(pred_rev, 0),
                '实际件数': actual_qty,
                '实际金额': round(actual_rev, 0),
                '件数偏差': qty_dev,
                '金额偏差': round(rev_dev, 0),
                '件数准确率': round((1 - abs(qty_dev) / max(pred_qty, 1)) * 100, 1),
            })

        df_sku = pd.DataFrame(sku_level)

        # --- 系列级汇总 ---
        series_pred = df_sku.groupby('系列').agg(
            pred_qty=('预测件数', 'sum'),
            pred_rev=('预测金额', 'sum')
        ).reset_index()

        series_actual = df_sku.groupby('系列').agg(
            actual_qty=('实际件数', 'sum'),
            actual_rev=('实际金额', 'sum')
        ).reset_index()

        series_level = series_pred.merge(series_actual, on='系列')
        series_level['件数准确率'] = series_level.apply(
            lambda r: round((1 - abs(r['actual_qty'] - r['pred_qty']) / max(r['pred_qty'], 1)) * 100, 1), axis=1)
        series_level['金额准确率'] = series_level.apply(
            lambda r: round((1 - abs(r['actual_rev'] - r['pred_rev']) / max(r['pred_rev'], 1)) * 100, 1), axis=1)
        series_level = series_level.to_dict('records')

        # --- 颜色占比偏差 ---
        color_level = []
        for series_name in df_sku['系列'].unique():
            sub = df_sku[df_sku['系列'] == series_name]
            color_groups = sub.groupby('颜色').agg(
                pred_qty=('预测件数', 'sum'),
                actual_qty=('实际件数', 'sum')
            ).reset_index()
            total_pred = color_groups['pred_qty'].sum()
            total_act = color_groups['actual_qty'].sum()
            for _, r in color_groups.iterrows():
                color_level.append({
                    '系列': series_name,
                    '颜色': r['颜色'],
                    '预测件数': r['pred_qty'],
                    '预测占比': round(r['pred_qty'] / total_pred * 100, 1) if total_pred > 0 else 0,
                    '实际件数': r['actual_qty'],
                    '实际占比': round(r['actual_qty'] / total_act * 100, 1) if total_act > 0 else 0,
                    '占比偏差': round(r['actual_qty'] / total_act * 100 - r['pred_qty'] / total_pred * 100, 1) if total_pred > 0 and total_act > 0 else 0,
                })

        # --- 尺寸占比偏差（同上逻辑）---
        size_level = []
        for series_name in df_sku['系列'].unique():
            sub = df_sku[df_sku['系列'] == series_name]
            size_groups = sub.groupby('尺寸').agg(
                pred_qty=('预测件数', 'sum'),
                actual_qty=('实际件数', 'sum')
            ).reset_index()
            total_pred = size_groups['pred_qty'].sum()
            total_act = size_groups['actual_qty'].sum()
            for _, r in size_groups.iterrows():
                size_level.append({
                    '系列': series_name,
                    '尺寸': r['尺寸'],
                    '预测件数': r['pred_qty'],
                    '预测占比': round(r['pred_qty'] / total_pred * 100, 1) if total_pred > 0 else 0,
                    '实际件数': r['actual_qty'],
                    '实际占比': round(r['actual_qty'] / total_act * 100, 1) if total_act > 0 else 0,
                    '占比偏差': round(r['actual_qty'] / total_act * 100 - r['pred_qty'] / total_pred * 100, 1) if total_pred > 0 and total_act > 0 else 0,
                })

        # --- 汇总 ---
        total_pred = df_sku['预测件数'].sum()
        total_actual = df_sku['实际件数'].sum()
        total_pred_rev = df_sku['预测金额'].sum()
        total_actual_rev = df_sku['实际金额'].sum()
        qty_acc = round((1 - abs(total_actual - total_pred) / max(total_pred, 1)) * 100, 1)
        rev_acc = round((1 - abs(total_actual_rev - total_pred_rev) / max(total_pred_rev, 1)) * 100, 1)

        summary = {
            '月份': self.month_key,
            '预测总件数': total_pred,
            '实际总件数': total_actual,
            '件数偏差': total_actual - total_pred,
            '件数准确率': qty_acc,
            '预测总金额': round(total_pred_rev, 0),
            '实际总金额': round(total_actual_rev, 0),
            '金额偏差': round(total_actual_rev - total_pred_rev, 0),
            '金额准确率': rev_acc,
        }

        result = {
            'sku_level': df_sku.to_dict('records'),
            'series_level': series_level,
            'color_level': color_level,
            'size_level': size_level,
            'summary': summary
        }

        self.result = result
        return result

    # ============================================================
    # 3. 写入验真结果到Excel
    # ============================================================
    def write_to_excel(self):
        """将验真结果写入Excel"""
        if not hasattr(self, 'result'):
            self.run_verification()

        result = self.result
        sheet_name = f'验真_{self.month_key}'

        try:
            with pd.ExcelWriter(TEMPLATE_PATH, engine='openpyxl', mode='a',
                                if_sheet_exists='replace') as writer:
                # Summary
                df_summary = pd.DataFrame([result['summary']])
                df_summary.to_excel(writer, sheet_name=f'{sheet_name}_汇总', index=False)

                # Series level
                df_series = pd.DataFrame(result['series_level'])
                df_series.to_excel(writer, sheet_name=f'{sheet_name}_系列', index=False)

                # Color level
                df_color = pd.DataFrame(result['color_level'])
                df_color.to_excel(writer, sheet_name=f'{sheet_name}_颜色', index=False)

                # Size level
                df_size = pd.DataFrame(result['size_level'])
                df_size.to_excel(writer, sheet_name=f'{sheet_name}_尺寸', index=False)

                # SKU level
                df_sku = pd.DataFrame(result['sku_level'])
                df_sku.to_excel(writer, sheet_name=f'{sheet_name}_SKU', index=False)

            print(f'[验真] 结果已写入: {sheet_name}_* (5个子表)')
            return True
        except Exception as e:
            print(f'[验真] 写入失败: {e}')
            return False

    # ============================================================
    # 4. 输出报告
    # ============================================================
    def print_report(self):
        """打印验真摘要"""
        if not hasattr(self, 'result'):
            self.run_verification()

        r = self.result
        s = r['summary']

        print()
        print('=' * 60)
        print(f'  月度验真报告: {s["月份"]}')
        print('=' * 60)
        print()
        print(f'  总件数: 预测={s["预测总件数"]} | 实际={s["实际总件数"]} | 准确率={s["件数准确率"]}%')
        print(f'  总金额: 预测={s["预测总金额"]/10000:.0f}万 | 实际={s["实际总金额"]/10000:.0f}万 | 准确率={s["金额准确率"]}%')
        print()

        # 系列准确率排行
        print('  --- 系列准确率排行 ---')
        for sr in sorted(r['series_level'], key=lambda x: x['件数准确率']):
            print(f'    {sr["系列"]:30s} | 件数: {int(sr["pred_qty"])}->{int(sr["actual_qty"])} | 准确率: {sr["件数准确率"]}%')


# ============================================================
# 命令行入口
# ============================================================
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        month = sys.argv[1]
    else:
        # 默认验真最近一个有实际数据的月份
        month = '2026-06'

    print(f'[验真] 开始验证 {month}...')
    cal = Calibrator(month)
    cal.run_verification()
    cal.write_to_excel()
    cal.print_report()
