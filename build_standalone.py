# -*- coding: utf-8 -*-
"""build_standalone.py — 双击即可打开的独立看板HTML"""
import os, json, sys

web = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
html_path = os.path.join(web, 'index.html')
data_path = os.path.join(web, 'forecast_data.json')
out_path = os.path.join(web, 'fcst_dashboard.html')

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

with open(data_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 压缩JSON为单行
data_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

# 用JS模板字面量(backtick)包裹，只需转义反引号和${}
data_str = data_str.replace('`', '\\`').replace('${', '\\${')

old_func = """async function init() {
  try {
    const resp = await fetch('forecast_data.json');
    const raw = await resp.text();
    DATA = JSON.parse(raw);
  } catch(e) {
    console.warn('forecast_data.json 无法加载, 尝试读取 dashboard-data.json');
    const resp = await fetch('dashboard-data.json');
    DATA = await resp.json();
  }
"""

new_func = f"""const INLINE = `{data_str}`;

async function init() {{
  try {{
    DATA = JSON.parse(INLINE);
  }} catch(e) {{
    $('mainContent').innerHTML = '<div class="empty-state"><p>数据解析失败: ' + e.message + '</p></div>';
    return;
  }}
"""

if old_func in html:
    html = html.replace(old_func, new_func)
    print('[OK] 替换成功')
else:
    print('[WARN] 旧函数不匹配，尝试模糊匹配')
    # 找async function init的起止位置
    s = html.find('async function init() {')
    e = html.find('  }\n  \n  if (!DATA) {', s)
    if s > 0 and e > 0:
        html = html[:s] + new_func + html[e:]
        print(f'[OK] 模糊替换: {s}-{e}')
    else:
        print('[ERR] 无法找到init函数')
        sys.exit(1)

with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

size = len(html)//1024
print(f'[OK] 生成完成: fcst_dashboard.html ({size}KB)')
print('双击文件即可直接打开看板')
