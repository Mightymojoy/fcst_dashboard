# -*- coding: utf-8 -*-
import pandas as pd
import os
os.chdir(r"e:\FCST渠道预测看板系统")

# 读取商品匹配表
df = pd.read_excel("天猫预测-2026年销量预测.xlsx", sheet_name="商品匹配表")
print("=== 商品匹配表 ===")
print(f"总行数: {len(df)}")
print(f"列名: {list(df.columns)}")
print("系列唯一值:", df["系列"].dropna().unique().tolist())
print("颜色唯一值:", df["颜色"].dropna().unique().tolist())
print("尺寸唯一值:", df["尺寸"].dropna().unique().tolist())
print()

# 读取预测数据
df2 = pd.read_excel("天猫预测-2026年销量预测.xlsx", sheet_name="直销_伊稻_电商_天猫ITO旗舰店-预测数据")
print("=== 预测数据 ===")
print(f"总行数: {len(df2)}")
print(f"列名: {list(df2.columns)}")
month_cols = [c for c in df2.columns if str(c).startswith("202")]
print(f"月份列: {month_cols}")
print("前3行:")
print(df2[["货品编码","商品名称"] + month_cols].head(3).to_string())
print()

# 读取实际数据
df3 = pd.read_excel("天猫预测-2026年销量预测.xlsx", sheet_name="直销_伊稻_电商_天猫ITO旗舰店-实际数据")
print("=== 实际数据 ===")
print(f"总行数: {len(df3)}")
print(f"列名: {list(df3.columns)}")
actual_month_cols = [c for c in df3.columns if str(c).startswith("202")]
print(f"月份列: {actual_month_cols}")
print("前3行:")
print(df3[["货品编码","商品名称"] + actual_month_cols].head(3).to_string())
print()

# 读取日级源数据 - 26-1 ITO
df4 = pd.read_excel("各渠道销售数据源/26-1.xlsx")
ito = df4[df4["店铺"]=="直销_伊稻_电商_天猫ITO旗舰店"]
print("=== 26-1 ITO日级数据 (前5行) ===")
cols9 = ["日期","货品编号","货品名称","实际销售量","实际销售额"]
print(ito[cols9].head(5).to_string())
print(f"日期范围: {ito['日期'].min()} ~ {ito['日期'].max()}")
print(f"总行数: {len(ito)}")
