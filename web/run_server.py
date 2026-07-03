import os, http.server, socketserver
os.chdir(os.path.dirname(os.path.abspath(__file__)))
with socketserver.TCPServer(('localhost', 8090), http.server.SimpleHTTPRequestHandler) as httpd:
    httpd.serve_forever()
