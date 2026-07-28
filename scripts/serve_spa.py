#!/usr/bin/env python3
"""Serve a built single-page application with history-API fallback."""
import argparse
import http.server
import os
from pathlib import Path


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        path = Path(self.translate_path(self.path.split("?", 1)[0]))
        if not path.exists() or path.is_dir():
            self.path = "/index.html"
        return super().send_head()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--port", type=int, default=3101)
    args = parser.parse_args()
    os.chdir(args.directory)
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), SPAHandler).serve_forever()


if __name__ == "__main__":
    main()
