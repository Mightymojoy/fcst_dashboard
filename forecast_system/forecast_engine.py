"""
forecast_engine.py — 三层预测引擎 v3.0
T1(逐个时间序列) → T2(系列分组) → T3(聚合分配)
"""

import numpy as np
import pandas as pd
from config import *


class ForecastEngine:
    def __init__(self, matrix, seasonal):
        self.matrix = matrix
        self.seasonal = seasonal
        self.hist_months = sorted(c for c in matrix.columns if c < '2026-07')
        self.pred_months = PREDICT_MONTHS
        self.series_groups = {}  # {series: [sku, ...]} 由外部设置

    def run(self):
        """主入口：对所有SKU执行预测"""
        results = {}
        for sku in self.matrix.index:
            results[sku] = self._predict(sku)
        return results

    def _predict(self, sku):
        """判断SKU类型并调用对应方法"""
        if sku in DISCONTINUED_SKUS:
            return {m: 0 for m in self.pred_months}
        if sku in NEW_JUNE15_SKUS:
            return self._new_ramp(sku, NEW_JUNE15_SKUS[sku])
        if sku in UPGRADE_NEW_SKUS:
            return self._upgrade_new(sku)
        if sku in OLD_DISCONTINUING_SKUS:
            return self._old_to_zero(sku)
        return self._normal(sku)

    # ================================================================
    # T1层：逐个SKU时间序列 — 加权平均×季节×趋势
    # formula: weighted_avg × seasonal × (1 + trend)
    # ================================================================
    def _tier1(self, sku, vals):
        n = len(vals)
        recent = vals[-6:] if n >= 6 else vals
        w = RECENT_WEIGHTS[-len(recent):]
        weighted_avg = sum(v * w_ for v, w_ in zip(recent, w)) / sum(w)

        if n >= 6:
            r3 = np.mean(vals[-3:])
            p3 = np.mean(vals[-6:-3])
            trend = (r3 - p3) / p3 if p3 > 0 else 0
            trend = max(-0.3, min(0.3, trend))
        else:
            trend = 0

        result = {}
        for m in self.pred_months:
            mn = int(m.split('-')[1])
            s = self.seasonal.get(mn, 1.0)
            pred = weighted_avg * s * (1 + trend)
            result[m] = max(0, int(round(pred)))
        return result

    # ================================================================
    # T2层：系列分组预测 → 按历史比例分配
    # ================================================================
    def _tier2(self, sku, vals, series_name):
        # 找同系列所有T2+T1 SKU的历史总量
        group_skus = self.series_groups.get(series_name, [])
        group_vals = {}
        for gs in group_skus:
            gv = []
            for m in self.hist_months:
                v = self.matrix.loc[gs, m] if gs in self.matrix.index else 0
                if pd.notna(v) and v > 0:
                    gv.append(v)
            if gv:
                group_vals[gs] = gv

        if not group_vals:
            return self._tier3(sku, vals)

        # 预测系列总量（用T1方法）
        all_vals = []
        for gv in group_vals.values():
            all_vals.extend(gv)
        group_avg = np.mean(all_vals) if all_vals else np.mean(vals)

        result = {}
        for m in self.pred_months:
            mn = int(m.split('-')[1])
            s = self.seasonal.get(mn, 1.0)
            group_pred = group_avg * s

            # 该SKU在系列中的历史占比
            sku_avg = np.mean(vals)
            ratio = sku_avg / group_avg if group_avg > 0 else 1.0 / len(group_vals)
            pred = group_pred * ratio
            result[m] = max(0, int(round(pred)))
        return result

    # ================================================================
    # T3层：低销量SKU — 均值×季节
    # ================================================================
    def _tier3(self, sku, vals):
        avg = np.mean(vals)
        if avg < 5:
            base = max(1, int(round(avg)))
            return {m: base for m in self.pred_months}
        result = {}
        for m in self.pred_months:
            mn = int(m.split('-')[1])
            s = self.seasonal.get(mn, 1.0)
            pred = avg * s
            result[m] = max(1, int(round(pred)))
        return result

    # ================================================================
    # 正常在售 → 自动分发到T1/T2/T3
    # ================================================================
    def _normal(self, sku):
        vals = []
        for m in self.hist_months:
            v = self.matrix.loc[sku, m]
            if pd.notna(v) and v >= 0:
                vals.append(v)
        if len(vals) < MIN_HISTORY:
            avg = np.mean(vals) if vals else 0
            return {m: max(0, int(round(avg))) for m in self.pred_months}

        avg = np.mean(vals)

        # 找系列名
        series_name = '其他'
        for sn, gs in self.series_groups.items():
            if sku in gs:
                series_name = sn
                break

        if avg >= TIER1_THRESHOLD:
            return self._tier1(sku, vals)
        elif avg >= TIER2_THRESHOLD:
            return self._tier2(sku, vals, series_name)
        else:
            return self._tier3(sku, vals)

    # ================================================================
    # 新品Ramp-up（6月15日上市）
    # ================================================================
    def _new_ramp(self, sku, info):
        analog_sku = info.get('analog_sku')
        base = info.get('conservative_estimate', 5)

        if analog_sku and analog_sku in self.matrix.index:
            vals = []
            for m in self.hist_months[-6:]:
                v = self.matrix.loc[analog_sku, m]
                if pd.notna(v) and v > 0:
                    vals.append(v)
            if vals:
                base = np.mean(vals)

        pr = info.get('price_ratio', 1.0)
        if pr > 1.0:
            if pr >= 1.5: base *= 0.6
            elif pr >= 1.2: base *= 0.75
            else: base *= 0.9

        base = max(3, int(round(base)))
        result = {}
        for m in self.pred_months:
            mn = int(m.split('-')[1])
            ramp = RAMPUP.get(mn, 0.5)
            s = self.seasonal.get(mn, 1.0)
            pred = base * ramp * s
            result[m] = max(1, int(round(pred)))
        return result

    # ================================================================
    # 升级新品（CPSSD2604 2026版）
    # ================================================================
    def _upgrade_new(self, sku):
        return self._new_ramp(sku, {'analog_sku': None, 'conservative_estimate': 10})

    # ================================================================
    # 老款退市（10月起=0）
    # ================================================================
    def _old_to_zero(self, sku):
        vals = []
        for m in self.hist_months:
            v = self.matrix.loc[sku, m]
            if pd.notna(v) and v >= 0:
                vals.append(v)
        avg = np.mean(vals) if vals else 0
        result = {}
        for m in self.pred_months:
            mn = int(m.split('-')[1])
            if mn >= 10:
                result[m] = 0
            else:
                s = self.seasonal.get(mn, 1.0)
                result[m] = max(0, int(round(avg * s)))
        return result
