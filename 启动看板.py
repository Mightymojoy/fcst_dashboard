# -*- coding: utf-8 -*-
"""启动看板.py — 一键启动FCST在线看板"""
import os, sys, http.server, socket, time

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
os.chdir(WEB_DIR)
HOST, PORT = 'localhost', 8090
# 如果8090被占用，自动尝试8091
import socket as _sock
_s = _sock.socket()
try: _s.bind((HOST, PORT)); _s.close()
except:
    PORT = 8091
    print(f'端口8090被占用，改用{PORT}')


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == '/': self.path = '/index.html'
        return super().do_GET()

# 尝试绑定端口
for attempt in range(3):
    try:
        httpd = http.server.HTTPServer((HOST, PORT), Handler)
        break
    except OSError:
        if attempt < 2:
            time.sleep(2)
        else:
            print(f'端口 {PORT} 被占用，请稍后重试')
            sys.exit(1)

URL = f'http://{HOST}:{PORT}'
print('=' * 50)
print('  ITO FCST ')
print(f'  {URL}')
print('  Ctrl+C 停止服务')
print('=' * 50)

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    httpd.server_close()
