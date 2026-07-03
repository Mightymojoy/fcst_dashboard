import http.server, socketserver, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
http.server.HTTPServer(('localhost', 8090), http.server.SimpleHTTPRequestHandler).serve_forever()
