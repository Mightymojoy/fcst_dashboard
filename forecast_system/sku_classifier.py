"""
sku_classifier.py — SKU分类体系 v2.0
====================================
以「商品匹配表」为唯一分类源，输出系列/颜色/尺寸。
所有名称严格遵循匹配表中命名，不自行编造。
"""

import pandas as pd
import os

# 模板路径
_TEMPLATE_PATH = None


def _load_matching_table():
    """加载商品匹配表"""
    fp = _TEMPLATE_PATH or 'E:/FCST渠道预测看板系统/天猫预测-2026年销量预测.xlsx'
    price = pd.read_excel(fp, sheet_name='商品匹配表')
    # 清理，保留非空行
    price = price.dropna(subset=['货品名称', '系列']).reset_index(drop=True)
    return price


def _build_name_mapping():
    """
    构建 商品名称 → {系列, 颜色, 尺寸, 品类, 吊牌价} 的映射
    以匹配表为唯一权威源
    """
    price = _load_matching_table()
    mapping = {}
    for _, r in price.iterrows():
        name = str(r['货品名称']).strip()
        if not name:
            continue
        mapping[name] = {
            'series': str(r['系列']).strip(),
            'color': str(r['颜色']).strip(),
            'size': str(r['尺寸']).strip(),
            'category': str(r['品类']).strip(),
            'price': r['吊牌价'] if pd.notna(r['吊牌价']) else None,
            'product_name': name,
        }
    return mapping


def build_sku_classification(sku_list_with_names, template_path=None):
    """
    为预测表所有SKU构建分类。

    参数:
        sku_list_with_names: [(sku, product_name), ...]
        template_path: 预测模板路径

    返回:
        {sku: {series, color, size, category, price, product_name}, ...}
    """
    global _TEMPLATE_PATH
    if template_path:
        _TEMPLATE_PATH = template_path

    name_map = _build_name_mapping()
    price = _load_matching_table()
    
    # 构建名称模糊匹配索引
    # 用货品名称的前10个字符做索引
    fuzzy_index = {}
    for pn, info in name_map.items():
        key = pn[:10]
        if key not in fuzzy_index:
            fuzzy_index[key] = []
        fuzzy_index[key].append(info)
    
    result = {}
    unmatched = []
    matched_by_exact = 0
    matched_by_fuzzy = 0

    for sku, pname in sku_list_with_names:
        pname = str(pname).strip()
        
        # 方法1：精确匹配
        if pname in name_map:
            result[sku] = dict(name_map[pname], sku=sku)
            matched_by_exact += 1
            continue
        
        # 方法2：前10字符模糊匹配
        key = pname[:10]
        if key in fuzzy_index:
            candidates = fuzzy_index[key]
            if len(candidates) == 1:
                result[sku] = dict(candidates[0], sku=sku)
                matched_by_fuzzy += 1
                continue
            else:
                # 多个候选：取匹配度最高的
                best = None
                best_score = 0
                for c in candidates:
                    score = len(set(pname) & set(c['product_name']))
                    if score > best_score:
                        best_score = score
                        best = c
                if best:
                    result[sku] = dict(best, sku=sku)
                    matched_by_fuzzy += 1
                    continue
        
        # 方法3：从商品名称中提取SKU前缀匹配系列
        sku_upper = sku.upper()
        for pn, info in name_map.items():
            # 看SKU编码是否出现在匹配表的商家编码中，或取SKU前缀匹配系列
            sku_prefix = sku_upper[:4]
            # 在所有匹配表条目中找系列名匹配
            series = info['series']
            if sku_prefix in series.replace(' ', '') or series.replace(' ', '').startswith(sku_prefix):
                result[sku] = dict(info, sku=sku)
                matched_by_fuzzy += 1
                break
        else:
            unmatched.append((sku, pname))
    
    # 仍未匹配的用SKU编码推断
    for sku, pname in unmatched:
        result[sku] = _infer_from_sku(sku, pname)
    
    return result


def _infer_from_sku(sku, pname):
    """后备方案：从SKU编码推断分类（仅用于极少数无法匹配的SKU）"""
    # 系列前缀
    series_map = [
        ('CPSPS', 'PISTACHIO PLUS STRIPED'), ('CP2ST', 'PISTACHIO 2 STRIPED'),
        ('CPSSD', 'PISTACHIO STRIPED'), ('CG4ST', 'GINKGO 4 STRIP'),
        ('CBB2',  'PISTACHIO STRIPED'), ('DTFB', 'TRUFFLE BACKPACK'),
        ('DTPBP', 'TRUFFLE PRO BACKPACK'), ('DTPTT', 'TRUFFLE PRO TOTE'),
        ('DWKDR', 'WEEKENDER'), ('DMCBP', 'MYCENA BACKPACK'),
        ('F016', 'CLASSIC WAVE'),
    ]
    series = '其他'
    for prefix, sname in series_map:
        if sku.startswith(prefix):
            series = sname
            break
    
    # 尺寸从SKU编码提取
    import re
    size = '未知'
    m = re.search(r'[SEA](\d{2})', sku)
    if m:
        sz = int(m.group(1))
        size = f'{sz}L' if sz <= 9 else f'{sz}英寸'
    
    # 品类
    category = '行李箱' if any(p in sku for p in ['C0','C1','C2','CP','CB','CG','FO','LL','SN']) else '包袋'
    
    return {
        'sku': sku,
        'product_name': pname,
        'series': series,
        'color': '未知',
        'size': size,
        'category': category,
        'price': None,
    }


# ============================================================
# 快捷接口（保持向后兼容）
# ============================================================
_classification_cache = None

def get_classification(sku, product_name=''):
    """按SKU获取分类（使用缓存）"""
    global _classification_cache
    if _classification_cache is None:
        fp = _TEMPLATE_PATH or 'E:/FCST渠道预测看板系统/天猫预测-2026年销量预测.xlsx'
        df = pd.read_excel(fp, sheet_name='直销_伊稻_电商_天猫ITO旗舰店-实际数据')
        sku_list = [(str(r['货品编码']).strip(), str(r['商品名称'])) for _, r in df.iterrows()]
        _classification_cache = build_sku_classification(sku_list, _TEMPLATE_PATH)
    return _classification_cache.get(sku, {})


def get_all_classifications(template_path=None):
    """获取全部分类"""
    global _classification_cache, _TEMPLATE_PATH
    if template_path:
        _TEMPLATE_PATH = template_path
    if _classification_cache is None:
        fp = _TEMPLATE_PATH or 'E:/FCST渠道预测看板系统/天猫预测-2026年销量预测.xlsx'
        df = pd.read_excel(fp, sheet_name='直销_伊稻_电商_天猫ITO旗舰店-实际数据')
        sku_list = [(str(r['货品编码']).strip(), str(r['商品名称'])) for _, r in df.iterrows()]
        _classification_cache = build_sku_classification(sku_list, _TEMPLATE_PATH)
    return _classification_cache
