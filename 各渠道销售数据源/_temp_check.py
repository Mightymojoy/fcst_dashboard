import pandas as pd
df = pd.read_excel('26-5.xlsx')
stores = df['店铺'].unique()
print('=== Stores ===')
for s in sorted(stores):
    print(f'  {s}')
print(f'Total: {len(stores)}')
print()
groups = df['店铺分组'].dropna().unique()
print('=== Groups ===')
for g in sorted(groups, key=lambda x: str(x)):
    print(f'  {g}')
print()
print(f'Date range: {df["日期"].min()} to {df["日期"].max()}')
print(f'Date unique count: {df["日期"].nunique()}')
print()
print('=== Monthly data sizes ===')
import glob, os
files = sorted(glob.glob('*.xlsx'))
for f in files:
    s = os.path.getsize(f)
    print(f'  {f}: {s/1024:.0f} KB')
