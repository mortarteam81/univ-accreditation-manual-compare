"""Phase 3 대시보드용 로컬 HTTP 서버.

브라우저에서 file:// 로 열면 `fetch("data/nodes.json")` 가 CORS 로 막히므로
표준 라이브러리 기반의 간단한 정적 서버를 제공한다.

사용:
    python serve.py                 # 기본: http://127.0.0.1:8000/dashboard.html
    python serve.py --port 9000
    python serve.py --no-open       # 브라우저 자동 실행 끔
"""
from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import sys
import threading
import webbrowser


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """로컬 개발용: 캐시 비활성화."""

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, format, *args):  # noqa: A002
        sys.stderr.write("[serve] %s - %s\n" % (self.address_string(), format % args))


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 3 대시보드 로컬 서버")
    ap.add_argument("--host", default="127.0.0.1", help="바인드 주소 (기본: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8000, help="포트 (기본: 8000)")
    ap.add_argument("--no-open", action="store_true", help="브라우저 자동 실행 끄기")
    args = ap.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)
    if not os.path.exists(os.path.join(root, "dashboard.html")):
        sys.exit(f"[ERROR] dashboard.html 이 {root} 에 없습니다.")
    if not os.path.exists(os.path.join(root, "data", "nodes.json")):
        sys.exit(f"[ERROR] data/nodes.json 이 없습니다. phase2 산출물을 data/ 에 복사해 주세요.")

    url = f"http://{args.host}:{args.port}/dashboard.html"
    print(f"[serve] root  = {root}")
    print(f"[serve] serving at {url}")
    print("[serve] Ctrl+C 로 종료")

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer((args.host, args.port), NoCacheHandler) as httpd:
        if not args.no_open:
            # 서버 기동 후 약간 지연한 뒤 브라우저 오픈
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[serve] 종료")


if __name__ == "__main__":
    main()
