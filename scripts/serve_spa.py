#!/usr/bin/env python3
"""Serve a built single-page application with history-API fallback.

Text assets are gzip-compressed on the fly when the client advertises
``Accept-Encoding: gzip``. Every real static host or CDN serves the built
bundle compressed; without it a benchmark measures multi-megabyte uncompressed
transfers that never happen in production and unfairly penalises the app. This
keeps local Lighthouse/performance measurements representative.
"""
import argparse
import gzip
import io
import http.server
import os
from pathlib import Path

COMPRESSIBLE = {".js", ".css", ".html", ".json", ".svg", ".txt", ".map", ".xml", ".webmanifest"}


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    # Keep-alive so a browser reuses one connection for the many hashed chunk
    # requests instead of opening (and sometimes resetting) a fresh connection
    # each time — Firefox in particular reports those resets as ChunkLoadError.
    # Every response below sets an explicit Content-Length, which HTTP/1.1
    # keep-alive requires.
    protocol_version = "HTTP/1.1"

    def send_head(self):
        raw = self.path.split("?", 1)[0]
        path = Path(self.translate_path(raw))
        if not path.exists() or path.is_dir():
            self.path = "/index.html"
            path = Path(self.translate_path("/index.html"))

        accepts_gzip = "gzip" in self.headers.get("Accept-Encoding", "")
        if accepts_gzip and path.is_file() and path.suffix.lower() in COMPRESSIBLE:
            try:
                data = path.read_bytes()
            except OSError:
                return super().send_head()
            body = gzip.compress(data, compresslevel=6)
            ctype = self.guess_type(str(path))
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(body)))
            # Hashed asset filenames make long caching safe; index.html must not
            # be cached so deploys are picked up.
            if path.name == "index.html":
                self.send_header("Cache-Control", "no-cache")
            else:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            return io.BytesIO(body)
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
