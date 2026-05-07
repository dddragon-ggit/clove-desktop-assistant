"""Simple HTTP server for testing the PWA locally.

Usage:
    python mobile/serve.py
    Then open http://localhost:8080 on your phone (same WiFi network).
"""
import http.server
import os
import socket

PORT = 8080


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


os.chdir(os.path.dirname(os.path.abspath(__file__)))
handler = http.server.SimpleHTTPRequestHandler
handler.extensions_map.update({".js": "application/javascript", ".json": "application/json"})

ip = get_local_ip()
print(f"Serving PWA at:")
print(f"  Local:   http://localhost:{PORT}")
print(f"  Network: http://{ip}:{PORT}")
print(f"Open the Network URL on your phone browser.")

http.server.HTTPServer(("0.0.0.0", PORT), handler).serve_forever()
