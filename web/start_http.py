import os, http.server
os.chdir(r'e:\FCST渠道预测看板系统\web')
httpd = http.server.HTTPServer(('localhost', 8091), http.server.SimpleHTTPRequestHandler)
httpd.serve_forever()
