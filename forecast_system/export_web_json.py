# -*- coding: utf-8 -*-
"""
export_web_json.py — FCST看板数据导出引擎 v3.1
从Excel读取全量数据，聚合输出为前端可直接消费的JSON结构。
v3.1: 改用SKU明细sheet作为预测数据源，金额按已发生取实际/未发生取预估。
"""
import os, json, pandas as pd
import numpy as np
from datetime import datetime
from config import TEMPLATE_PATH, CHANNEL_NAME, ACTUAL_SHEET, PREDICT_SHEET, DATA_DIR

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'web')
MONTHS_LABEL = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
MONTHS_2026 = ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06',
               '2026-07','2026-08','2026-09','2026-10','2026-11','2026-12']
QTY_COLS = ['1月件数','2月件数','3月件数','4月件数','5月件数','6月件数','7月件数','8月件数','9月件数','10月件数','11月件数','12月件数']
QTY_MONTHS = ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06',
              '2026-07','2026-08','2026-09','2026-10','2026-11','2026-12']
# 12月SKU级数据已补充到Excel，直接读取
DEC_RATIO = 1.0


def load_source_data():
    """从各渠道销售数据源读取ITO所有日级数据（2024-2026）"""
    all_daily = []
    if not os.path.isdir(DATA_DIR):
        return pd.DataFrame()
    files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.xlsx') and f[0].isdigit()])
    for fname in files:
        try:
            fpath = os.path.join(DATA_DIR, fname)
            df = pd.read_excel(fpath)
            if '店铺' not in df.columns or '货品编号' not in df.columns:
                continue
            ito = df[df['店铺'] == CHANNEL_NAME].copy()
            if len(ito) == 0: continue
            ito['日期obj'] = pd.to_datetime(ito['日期'], errors='coerce')
            ito = ito.dropna(subset=['日期obj'])
            ito['年月'] = ito['日期obj'].dt.strftime('%Y-%m')
            ito['年'] = ito['日期obj'].dt.year
            ito['月'] = ito['日期obj'].dt.month
            all_daily.append(ito)
        except:
            continue
    if not all_daily:
        return pd.DataFrame()
    return pd.concat(all_daily, ignore_index=True)


def load_category_map():
    """加载品类映射表，行李箱+旅行箱→行李箱，包袋→包袋，其他→配件"""
    try:
        cat_df = pd.read_excel(TEMPLATE_PATH, sheet_name='商品匹配表')
        cat_df = cat_df.dropna(subset=['货品名称', '品类']).reset_index(drop=True)
        n2c = {}
        for _, r in cat_df.iterrows():
            name = str(r['货品名称']).strip()
            if name:
                c = str(r['品类']).strip()
                if c in ('旅行箱','行李箱','小型箱'): n2c[name] = '行李箱'
                elif c == '包袋': n2c[name] = '包袋'
                else: n2c[name] = '配件'
        return n2c
    except: return {}

def compute_sku_info(sku_detail_df, daily_df, pred_janmay=None):
    """从SKU明细sheet构建SKU详情，金额：已发生取实际/未发生取预估
       pred_janmay: {sku: {month_key: qty}} 1-5月预测数据"""
    name_to_cat = load_category_map()
    # 从日级数据计算各SKU各月的实际销量和销售额
    actual_qty_by_sku = {}  # {sku: {年月: 件数}}
    actual_amt_by_sku = {}  # {sku: {年月: 销售额}}
    if not daily_df.empty:
        for _, r in daily_df.iterrows():
            sku = str(r['货品编号']).strip()
            ym = r['年月']
            qty = int(r['实际销售量']) if pd.notna(r.get('实际销售量', 0)) else 0
            rev = float(r['实际销售额']) if pd.notna(r.get('实际销售额', 0)) else 0
            if sku not in actual_qty_by_sku:
                actual_qty_by_sku[sku] = {}
                actual_amt_by_sku[sku] = {}
            actual_qty_by_sku[sku][ym] = actual_qty_by_sku[sku].get(ym, 0) + qty
            actual_amt_by_sku[sku][ym] = actual_amt_by_sku[sku].get(ym, 0) + rev

    sku_list = []
    for _, r in sku_detail_df.iterrows():
        sku = str(r['SKU编码']).strip()
        pname = str(r['商品名称']).strip() if pd.notna(r['商品名称']) else ''
        series = str(r['系列']).strip() if pd.notna(r['系列']) else '其他'
        color = str(r['颜色']).strip() if pd.notna(r['颜色']) else ''
        size = str(r['尺寸']).strip() if pd.notna(r['尺寸']) else ''
        price = float(r['吊牌价']) if pd.notna(r['吊牌价']) else 0
        
        # 品类匹配
        category = ''
        if pname and pname in name_to_cat:
            category = name_to_cat[pname]
        if not category and pname:
            key = pname[:12]
            for n, c in name_to_cat.items():
                if n.startswith(key) or key in n:
                    category = c
                    break
        if not category:
            category = '行李箱'  # 默认

        monthly_pred = {}
        monthly_amt = {}
        monthly_actual = {}
        monthly_actual_amt = {}
        for mi, mk in enumerate(MONTHS_2026):
            # 预测件数：1-5月从pred_janmay读取，6-12月从SKU明细直接读取
            if mi < 5 and pred_janmay and sku in pred_janmay:
                qty = pred_janmay[sku].get(mk, 0)
            else:
                qty_col = QTY_COLS[mi]
                sv = r.get(qty_col, 0)
                qty = int(round(float(sv))) if pd.notna(sv) and float(sv) > 0 else 0
            monthly_pred[mk] = qty

            # 实际件数（从日级数据）
            actual_qty = actual_qty_by_sku.get(sku, {}).get(mk, 0)
            monthly_actual[mk] = actual_qty

            # 实际销售额
            actual_amt = actual_amt_by_sku.get(sku, {}).get(mk, 0)
            monthly_actual_amt[mk] = round(actual_amt, 2)

            # 展示金额：已发生取实际，未发生取 qty * price
            if actual_amt > 0:
                monthly_amt[mk] = round(actual_amt, 2)
            elif qty > 0 and price > 0:
                monthly_amt[mk] = round(qty * price, 2)
            else:
                monthly_amt[mk] = 0.0

        total_pred = sum(monthly_pred.values())

        sku_list.append({
            'sku': sku, 'name': pname, 'series': series,
            'color': color, 'size': size, 'category': category,
            'price': price,
            'pred_by_month': monthly_pred,
            'actual_by_month': monthly_actual,
            'actual_amt_by_month': monthly_actual_amt,
            'amt_by_month': monthly_amt,
            'total_pred': total_pred,
            'total_actual': sum(monthly_actual.values()),
            'total_amt': round(sum(monthly_amt.values()), 2),
        })
    return sku_list


def compute_series_summary(sku_list):
    """从SKU列表聚合系列级汇总（金额用已计算好的amt按万元显示）"""
    series_map = {}
    for sk in sku_list:
        s = sk['series']
        if s not in series_map:
            series_map[s] = {'qty': [0]*12, 'amt_raw': [0.0]*12}
        for mi, mk in enumerate(MONTHS_2026):
            q = sk['pred_by_month'].get(mk, 0)
            series_map[s]['qty'][mi] += q
            a = sk['amt_by_month'].get(mk, 0.0)
            series_map[s]['amt_raw'][mi] += a

    series_list = []
    for sname, data in series_map.items():
        amt_wan = [round(v / 10000, 1) for v in data['amt_raw']]
        series_list.append({
            'name': sname,
            'qty_by_month': data['qty'],
            'amt_by_month': amt_wan,
            'total_qty': sum(data['qty']),
            'total_amt': round(sum(data['amt_raw']) / 10000, 1),
        })
    series_list.sort(key=lambda s: s['total_qty'], reverse=True)
    return series_list


def compute_daily_actual(daily_df, sku_list):
    """从日级数据按天聚合"""
    if daily_df.empty:
        return []
    valid_skus = set(sk['sku'] for sk in sku_list)
    mask = daily_df['货品编号'].astype(str).isin(valid_skus)
    filtered = daily_df[mask].copy()
    daily = filtered.groupby('日期obj').agg(
        qty=('实际销售量', 'sum'), rev=('实际销售额', 'sum')
    ).reset_index()
    daily['date_str'] = daily['日期obj'].dt.strftime('%Y-%m-%d')
    daily = daily.sort_values('date_str')
    return [{'date': r['date_str'], 'qty': int(r['qty']), 'rev': round(float(r['rev']), 2)}
            for _, r in daily.iterrows()]


def compute_historical_compare(daily_df, sku_list):
    """计算同环比"""
    if daily_df.empty:
        return {'yoy': {}, 'mom': {}, 'yoy_by_month': [], 'mom_by_month': []}
    valid_skus = set(sk['sku'] for sk in sku_list)
    filtered = daily_df[daily_df['货品编号'].astype(str).isin(valid_skus)].copy()
    monthly = filtered.groupby(['年', '月']).agg(
        qty=('实际销售量', 'sum'), rev=('实际销售额', 'sum')
    ).reset_index()

    yoy_by_month = []
    for m in range(1, 13):
        v2026 = monthly[(monthly['年']==2026) & (monthly['月']==m)]['qty'].sum()
        v2025 = monthly[(monthly['年']==2025) & (monthly['月']==m)]['qty'].sum()
        rate = round((v2026 - v2025) / v2025 * 100, 1) if v2025 > 0 else None
        yoy_by_month.append({
            'month': f'{m}月', 'current': int(v2026), 'last_year': int(v2025), 'rate': rate
        })

    mom_by_month = []
    prev_qty = None
    for m in range(1, 13):
        v = monthly[(monthly['年']==2026) & (monthly['月']==m)]['qty'].sum()
        rate = round((v - prev_qty) / prev_qty * 100, 1) if prev_qty and prev_qty > 0 else None
        mom_by_month.append({
            'month': f'{m}月', 'current': int(v), 'prev': int(prev_qty or 0), 'rate': rate
        })
        prev_qty = int(v) if v > 0 else prev_qty

    return {'yoy_by_month': yoy_by_month, 'mom_by_month': mom_by_month}


def compute_color_size_analysis(sku_list, daily_df):
    """计算颜色/尺寸/颜色×尺寸占比分析"""
    valid_skus = set(sk['sku'] for sk in sku_list)
    series_color_qty = {}
    series_size_qty = {}
    cross_qty = {}
    if not daily_df.empty:
        filtered = daily_df[daily_df['货品编号'].astype(str).isin(valid_skus)]
        sku_cls = {sk['sku']: (sk['series'], sk['color'], sk['size']) for sk in sku_list}
        for _, r in filtered.iterrows():
            sku = str(r['货品编号']).strip()
            if sku not in sku_cls: continue
            s, c, sz = sku_cls[sku]
            qty = int(r['实际销售量']) if pd.notna(r['实际销售量']) else 0
            if s not in series_color_qty: series_color_qty[s] = {}
            if s not in series_size_qty: series_size_qty[s] = {}
            if s not in cross_qty: cross_qty[s] = {}
            series_color_qty[s][c] = series_color_qty[s].get(c, 0) + qty
            series_size_qty[s][sz] = series_size_qty[s].get(sz, 0) + qty
            cross_qty[s][f"{c}|{sz}"] = cross_qty[s].get(f"{c}|{sz}", 0) + qty

    series_color_pred = {}
    series_size_pred = {}
    cross_pred = {}
    for sk in sku_list:
        s, c, sz = sk['series'], sk['color'], sk['size']
        tp = sk['total_pred']
        if not s: continue
        if s not in series_color_pred: series_color_pred[s] = {}
        if s not in series_size_pred: series_size_pred[s] = {}
        if s not in cross_pred: cross_pred[s] = {}
        series_color_pred[s][c] = series_color_pred[s].get(c, 0) + tp
        series_size_pred[s][sz] = series_size_pred[s].get(sz, 0) + tp
        cross_pred[s][f"{c}|{sz}"] = cross_pred[s].get(f"{c}|{sz}", 0) + tp

    all_series = set(list(series_color_qty.keys()) + list(series_color_pred.keys()))
    color_analysis = []
    size_analysis = []
    cross_analysis = []
    for s in all_series:
        color_analysis.append({
            'series': s,
            'colors': list(set(list(series_color_qty.get(s, {}).keys()) + list(series_color_pred.get(s, {}).keys()))),
            'actual': series_color_qty.get(s, {}),
            'pred': series_color_pred.get(s, {}),
        })
        size_analysis.append({
            'series': s,
            'sizes': list(set(list(series_size_qty.get(s, {}).keys()) + list(series_size_pred.get(s, {}).keys()))),
            'actual': series_size_qty.get(s, {}),
            'pred': series_size_pred.get(s, {}),
        })
        cross_analysis.append({
            'series': s,
            'items': list(set(list(cross_qty.get(s, {}).keys()) + list(cross_pred.get(s, {}).keys()))),
            'actual': cross_qty.get(s, {}),
            'pred': cross_pred.get(s, {}),
        })
    return color_analysis, size_analysis, cross_analysis


def compute_calibration(sku_list, daily_df):
    """验真数据：按月/系列/颜色计算预测vs实际偏差（精简版，不输出SKU级明细）"""
    valid_skus = set(sk['sku'] for sk in sku_list)
    monthly_actual = {}
    if not daily_df.empty:
        filtered = daily_df[daily_df['货品编号'].astype(str).isin(valid_skus)]
        for _, r in filtered.iterrows():
            sku = str(r['货品编号']).strip()
            ym = r['年月']
            qty = int(r['实际销售量']) if pd.notna(r['实际销售量']) else 0
            if sku not in monthly_actual:
                monthly_actual[sku] = {}
            monthly_actual[sku][ym] = monthly_actual[sku].get(ym, 0) + qty

    calibration = {
        'months': [], 'series_level': [], 'color_level': [], 'size_level': [],
        'sku_level': [], 'date_range': {'min': '', 'max': ''},
    }
    if not daily_df.empty:
        calibration['date_range'] = {
            'min': daily_df['日期obj'].min().strftime('%Y-%m-%d'),
            'max': daily_df['日期obj'].max().strftime('%Y-%m-%d'),
        }

    EXCLUDE = {'PISTACHIO 2 秋冬限定色-25', 'CHANTERELLE DUFFLE BAG 2'}
    series_names = sorted(set(sk['series'] for sk in sku_list if sk['series'] not in EXCLUDE))

    for mi, mk in enumerate(MONTHS_2026):
        # 验真只计算未被排除的系列
        cal_skus = [sk for sk in sku_list if sk['series'] not in EXCLUDE]
        total_pred = sum(sk['pred_by_month'].get(mk, 0) for sk in cal_skus)
        if total_pred == 0:
            continue
        total_actual = sum(monthly_actual.get(sk['sku'], {}).get(mk, 0) for sk in cal_skus)
        dev = total_actual - total_pred
        acc = round((1 - abs(dev) / max(total_pred, 1)) * 100, 1)
        calibration['months'].append({
            'month': MONTHS_LABEL[mi], 'month_key': mk,
            'pred_qty': total_pred, 'actual_qty': total_actual,
            'deviation': dev, 'accuracy': acc,
        })

        # SKU级明细
        for sk in cal_skus:
            sp = sk['pred_by_month'].get(mk, 0)
            sa = monthly_actual.get(sk['sku'], {}).get(mk, 0)
            if sp > 0 or sa > 0:
                calibration['sku_level'].append({
                    'month': MONTHS_LABEL[mi], 'month_key': mk,
                    'sku': sk['sku'], 'name': sk['name'],
                    'series': sk['series'], 'color': sk['color'], 'size': sk['size'],
                    'category': sk.get('category', ''),
                    'pred_qty': sp, 'actual_qty': sa,
                    'deviation': sa - sp,
                    'accuracy': round((1 - abs(sa - sp) / max(sp, 1)) * 100, 1),
                })

        for sname in series_names:
            s_skus = [sk for sk in cal_skus if sk['series'] == sname]
            sp = sum(sk['pred_by_month'].get(mk, 0) for sk in s_skus)
            sa = sum(monthly_actual.get(sk['sku'], {}).get(mk, 0) for sk in s_skus)
            if sp > 0 or sa > 0:
                calibration['series_level'].append({
                    'month': MONTHS_LABEL[mi], 'month_key': mk,
                    'series': sname, 'category': '',
                    'pred_qty': sp, 'actual_qty': sa,
                    'deviation': sa - sp,
                    'accuracy': round((1 - abs(sa - sp) / max(sp, 1)) * 100, 1),
                })

            for cname in sorted(set(sk['color'] for sk in s_skus if sk['color'])):
                c_skus = [sk for sk in s_skus if sk['color'] == cname]
                sp = sum(sk['pred_by_month'].get(mk, 0) for sk in c_skus)
                sa = sum(monthly_actual.get(sk['sku'], {}).get(mk, 0) for sk in c_skus)
                if sp > 0 or sa > 0:
                    calibration['color_level'].append({
                        'month': MONTHS_LABEL[mi], 'month_key': mk,
                        'series': sname, 'color': cname,
                        'pred_qty': sp, 'actual_qty': sa,
                        'deviation': sa - sp,
                        'accuracy': round((1 - abs(sa - sp) / max(sp, 1)) * 100, 1),
                    })

            for szname in sorted(set(sk['size'] for sk in s_skus if sk['size'])):
                sz_skus = [sk for sk in s_skus if sk['size'] == szname]
                sp = sum(sk['pred_by_month'].get(mk, 0) for sk in sz_skus)
                sa = sum(monthly_actual.get(sk['sku'], {}).get(mk, 0) for sk in sz_skus)
                if sp > 0 or sa > 0:
                    calibration['size_level'].append({
                        'month': MONTHS_LABEL[mi], 'month_key': mk,
                        'series': sname, 'size': szname,
                        'pred_qty': sp, 'actual_qty': sa,
                        'deviation': sa - sp,
                        'accuracy': round((1 - abs(sa - sp) / max(sp, 1)) * 100, 1),
                    })

    return calibration


def export(engine_predictions=None):
    print('[导出] 开始加载数据...')

    # 1. 加载日级数据（用于实际金额和同环比）
    daily_df = load_source_data()
    print(f'[导出] 日级数据: {len(daily_df)}条')

    # 2. 读取SKU明细
    df_sku_detail = pd.read_excel(TEMPLATE_PATH, sheet_name='SKU明细')
    print(f'[导出] SKU明细: {len(df_sku_detail)}条')

    # 3. 加载1-5月预测数据
    pred_janmay = {}
    pred_file = os.path.join(os.path.dirname(TEMPLATE_PATH), '26年1-5月预测数据.xlsx')
    if os.path.exists(pred_file):
        try:
            df_p5 = pd.read_excel(pred_file, sheet_name='Sheet1')
            for _, row in df_p5.iterrows():
                sku_code = str(row.iloc[0]).strip()
                if not sku_code: continue
                pred_janmay[sku_code] = {}
                for mi, mk in enumerate(MONTHS_2026[:5]):
                    v = row.iloc[mi+2] if mi+2 < len(row) else 0
                    pred_janmay[sku_code][mk] = int(round(float(v))) if pd.notna(v) and float(v) > 0 else 0
            print(f'[导出] 1-5月预测: {len(pred_janmay)}个SKU')
        except Exception as e:
            print(f'[警告] 26年1-5月预测数据.xlsx读取失败: {e}')

    # 4. 构建SKU详情（1-5月预测从26年1-5月预测数据.xlsx，6-11月从SKU明细）
    sku_list = compute_sku_info(df_sku_detail, daily_df, pred_janmay)
    print(f'[导出] SKU明细: {len(sku_list)}个')

    # 剔除异常系列（5月起预测归零）
    EXCLUDE_SERIES = ['PISTACHIO 2 秋冬限定色-25', 'CHANTERELLE DUFFLE BAG 2']
    EXCLUDE_FROM = 4
    exc = 0
    for sk in sku_list:
        if sk['series'] in EXCLUDE_SERIES:
            exc += 1
            for mi, mk in enumerate(MONTHS_2026):
                if mi >= EXCLUDE_FROM:
                    sk['pred_by_month'][mk] = 0
                    sk['amt_by_month'][mk] = 0.0
            sk['total_pred'] = sum(sk['pred_by_month'].values())
    if exc:
        print(f'[导出] 已剔除异常系列{exc}个SKU(5月起归零)')

    # 4. 系列级汇总
    series_list = compute_series_summary(sku_list)
    print(f'[导出] 系列: {len(series_list)}个')

    # 5. 日级实际聚合
    daily_actual = compute_daily_actual(daily_df, sku_list)
    print(f'[导出] 日级: {len(daily_actual)}天')

    # 6. 同环比
    historical = compute_historical_compare(daily_df, sku_list)

    # 7. 颜色/尺寸分析
    color_analysis, size_analysis, cross_analysis = compute_color_size_analysis(sku_list, daily_df)
    print(f'[导出] 颜色分析: {len(color_analysis)}系列')

    # 8. 验真
    calibration = compute_calibration(sku_list, daily_df)
    print(f'[导出] 验真: {len(calibration["months"])}月, 系列级 {len(calibration["series_level"])}条')

    # 9. 汇总统计
    total_pred_qty = sum(sk['total_pred'] for sk in sku_list)

    # 汇总（金额用已计算好的amt累加后一次转万元）
    pred_qty = [0]*12
    pred_amt_raw = [0.0]*12
    actual_qty = [0]*12
    for sk in sku_list:
        for mi, mk in enumerate(MONTHS_2026):
            pred_qty[mi] += sk['pred_by_month'].get(mk, 0)
            pred_amt_raw[mi] += sk['amt_by_month'].get(mk, 0.0)
            actual_qty[mi] += sk['actual_by_month'].get(mk, 0)

    pred_amt = [round(v / 10000, 1) for v in pred_amt_raw]

    # 预测目标：1-5月从26年1-5月预测数据.xlsx，6-12月从SKU明细(件数×单价)
    pred_target_amt_raw = [0.0] * 12
    # 1-5月：从用户上传的预测文件读取（预测数量×单价）
    pred_file = os.path.join(os.path.dirname(TEMPLATE_PATH), '26年1-5月预测数据.xlsx')
    if os.path.exists(pred_file):
        try:
            df_p5 = pd.read_excel(pred_file, sheet_name='Sheet1')
            sku_price = {sk['sku']: sk['price'] for sk in sku_list}
            for _, row in df_p5.iterrows():
                sku_code = str(row.iloc[0]).strip()
                p = sku_price.get(sku_code, 0)
                if p <= 0: continue
                for mi in range(5):
                    v = row.iloc[mi+2]
                    if pd.notna(v) and float(v) > 0:
                        pred_target_amt_raw[mi] += float(v) * p
        except Exception as e:
            print(f'[警告] 26年1-5月预测数据.xlsx读取失败: {e}')
    # 6-12月：从SKU明细的amt_by_month（已是件数×单价，未发生月份取预估）
    for sk in sku_list:
        for mi in range(5, 12):
            mk = MONTHS_2026[mi]
            pred_target_amt_raw[mi] += sk['amt_by_month'].get(mk, 0.0)
    # 转万元
    pred_target_amt = [round(v / 10000, 1) for v in pred_target_amt_raw]

    # 实际销售金额（从各渠道日级数据的实际销售额）
    actual_amt_raw = [0.0]*12
    for sk in sku_list:
        for mi, mk in enumerate(MONTHS_2026):
            actual_amt_raw[mi] += sk['actual_amt_by_month'].get(mk, 0.0)
    actual_amt_wan = [round(v / 10000, 1) for v in actual_amt_raw]

    # 达成率 = 实际销售 / 预测目标
    achievement = []
    for i in range(12):
        if pred_target_amt[i] > 0:
            ach = round(actual_amt_wan[i] / pred_target_amt[i] * 100, 1)
        else:
            ach = 0
        achievement.append(ach)

    total_pred_target = sum(pred_target_amt)
    total_actual = sum(actual_amt_wan)
    total_achievement = round(total_actual / total_pred_target * 100, 1) if total_pred_target > 0 else 0

    output = {
        'meta': {
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'channel': CHANNEL_NAME,
            'sku_count': len(sku_list),
            'series_count': len(series_list),
        },
        'summary': {
            'months': MONTHS_LABEL, 'months_key': MONTHS_2026,
            'actual_qty': actual_qty, 'pred_qty': pred_qty,
            'pred_amt': pred_amt,
            'actual_amt': actual_amt_wan,
            'pred_target_amt': pred_target_amt,
            'achievement': achievement,
            'total_pred_qty': total_pred_qty,
            'total_pred_amt': round(sum(pred_amt), 1),
            'total_actual_amt': round(total_actual, 1),
            'total_achievement': total_achievement,
        },
        'series': series_list,
        'sku_details': sku_list,
        'daily_actual': daily_actual,
        'historical': historical,
        'color_analysis': color_analysis,
        'size_analysis': size_analysis,
        'cross_analysis': cross_analysis,
        'calibration': calibration,
    }

    os.makedirs(WEB_DIR, exist_ok=True)
    out_path = os.path.join(WEB_DIR, 'forecast_data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=None, separators=(',', ':'))

    json_size = len(json.dumps(output, ensure_ascii=False, separators=(',', ':'))) // 1024
    print(f'[导出] 完成! 文件大小: {json_size}KB')
    print(f'  - SKU: {len(sku_list)} | 系列: {len(series_list)} | 日级: {len(daily_actual)}天')
    print(f'  - 验真: {len(calibration["months"])}月 / 系列级 {len(calibration["series_level"])}条')
    return output


if __name__ == '__main__':
    export()
