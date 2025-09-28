#!/usr/bin/env python3
"""
Minimal TTS cache proxy for OpenAI's /v1/audio/speech

- Pure standard library (no external deps)
- Caches responses (mp3) on disk by a stable hash of the request JSON
- Supports CORS so it can be called from a browser app
- Uses incoming Authorization: Bearer ... header if present,
  otherwise falls back to OPENAI_API_KEY env var.

Usage:
  python3 tts_cache_proxy.py [--host 127.0.0.1] [--port 22999]

Then point your client to:
  fetch('http://127.0.0.1:22999/v1/audio/speech', { ... same body & headers ... })

Notes:
- Only implements the specific endpoint used by your app: POST /v1/audio/speech
- Response format is audio/mpeg (mp3) when response_format == 'mp3'
- For any other method/path, returns 404
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import os
import sys
import json
import hashlib
import time
from pathlib import Path
from argparse import ArgumentParser

UPSTREAM_URL = 'https://api.openai.com/v1/audio/speech'
CACHE_DIR = Path(os.environ.get('TTS_CACHE_DIR', './tts_cache')).resolve()
DEFAULT_HOST = os.environ.get('TTS_PROXY_HOST', '127.0.0.1')
DEFAULT_PORT = int(os.environ.get('TTS_PROXY_PORT', '22999'))
ALLOW_ORIGIN = os.environ.get('TTS_PROXY_CORS', '*')  # set to specific origin if needed

CACHE_DIR.mkdir(parents=True, exist_ok=True)


def stable_cache_key(payload: dict) -> str:
    """Create a stable hash for the request payload relevant to audio output."""
    # Normalize JSON (sort keys, remove insignificant whitespace)
    norm = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if length <= 0:
            return {}
        data = handler.rfile.read(length)
        return json.loads(data.decode('utf-8'))
    except json.JSONDecodeError:
        handler.send_error(400, 'Invalid JSON')
        raise


def put_cors_headers(handler: BaseHTTPRequestHandler):
    handler.send_header('Access-Control-Allow-Origin', ALLOW_ORIGIN)
    handler.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, X-Preferred-Cache-Key')
    handler.send_header('Access-Control-Max-Age', '600')


class TTSProxyHandler(BaseHTTPRequestHandler):
    server_version = 'TTSCacheProxy/0.1'

    def log(self, msg: str):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        sys.stdout.write(f'[{ts}] {self.client_address[0]} {msg}\n')
        sys.stdout.flush()

    def do_OPTIONS(self):
        if self.path == '/v1/audio/speech':
            self.send_response(204)
            put_cors_headers(self)
            self.end_headers()
        else:
            self.send_response(404)
            put_cors_headers(self)
            self.end_headers()

    def do_POST(self):
        if self.path != '/v1/audio/speech':
            self.send_response(404)
            put_cors_headers(self)
            self.end_headers()
            return

        try:
            payload = read_json_body(self)
        except Exception:
            return  # error already sent

        # Basic validation
        response_format = payload.get('response_format', 'mp3')
        if response_format != 'mp3':
            self.send_response(400)
            put_cors_headers(self)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Only response_format=mp3 is supported by this proxy'}).encode('utf-8'))
            return

        # Resolve API key: prefer incoming Authorization header, else env
        auth = self.headers.get('Authorization')
        if not auth:
            env_key = os.environ.get('OPENAI_API_KEY')
            if env_key:
                auth = f'Bearer {env_key}'
        if not auth:
            self.send_response(401)
            put_cors_headers(self)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Missing Authorization header and OPENAI_API_KEY env'}).encode('utf-8'))
            return

        # Compute cache key from payload
        key = stable_cache_key(payload)

        # Use X-Preferred-Cache-Key header if provided (for readable filenames)
        preferred_key = self.headers.get('X-Preferred-Cache-Key')
        if preferred_key:
            safe_key = ''.join(c for c in preferred_key if c.isalnum() or c in ('-', '_'))
            safe_key = safe_key.strip('-_. ')  # trim edge chars
            safe_key = safe_key[:64]  # limit length
            if safe_key:
                key = safe_key

        mp3_path = CACHE_DIR / f'{key}.mp3'

        # Serve from cache if exists
        if mp3_path.exists():
            self.log(f'CACHE HIT {key} ({mp3_path.name})')
            try:
                data = mp3_path.read_bytes()
                self.send_response(200)
                put_cors_headers(self)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('X-Cache', 'HIT')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.log(f'Error reading cache: {e}')
                self.send_error(500, 'Failed to read cache')
            return

        # Otherwise, forward to OpenAI
        self.log(f'CACHE MISS {key} → forwarding to OpenAI')
        upstream_body = json.dumps(payload).encode('utf-8')
        req = Request(
            UPSTREAM_URL,
            data=upstream_body,
            headers={
                'Authorization': auth,
                'Content-Type': 'application/json',
                'Accept': 'audio/mpeg',
            },
            method='POST',
        )

        try:
            with urlopen(req, timeout=120) as resp:
                status = resp.getcode()
                data = resp.read()
                ctype = resp.headers.get('Content-Type', 'audio/mpeg')
        except HTTPError as e:
            # Relay upstream error
            err_body = e.read() or b''
            self.send_response(e.code)
            put_cors_headers(self)
            ctype = e.headers.get('Content-Type', 'text/plain; charset=utf-8') if e.headers else 'text/plain; charset=utf-8'
            self.send_header('Content-Type', ctype)
            self.end_headers()
            self.wfile.write(err_body)
            self.log(f'Upstream HTTPError {e.code}: {err_body[:200]!r}')
            return
        except URLError as e:
            self.send_response(502)
            put_cors_headers(self)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'error': f'Upstream connection failed: {e}'}).encode('utf-8'))
            self.log(f'Upstream URLError: {e}')
            return
        except Exception as e:
            self.send_response(500)
            put_cors_headers(self)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'error': f'Unexpected error: {e}'}).encode('utf-8'))
            self.log(f'Unexpected error: {e}')
            return

        # Only cache successful mp3 responses
        if status == 200 and (ctype.startswith('audio/mpeg') or ctype.startswith('audio/')):
            try:
                tmp_path = mp3_path.with_suffix('.mp3.part')
                tmp_path.write_bytes(data)
                os.replace(tmp_path, mp3_path)
            except Exception as e:
                self.log(f'Failed to write cache: {e}')

        # Relay downstream
        self.send_response(status)
        put_cors_headers(self)
        self.send_header('Content-Type', 'audio/mpeg')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Cache', 'MISS')
        self.end_headers()
        self.wfile.write(data)

    # Suppress overly verbose default logging
    def log_message(self, format, *args):
        pass


def main():
    ap = ArgumentParser(description='Minimal OpenAI TTS cache proxy')
    ap.add_argument('--host', default=DEFAULT_HOST, help=f'Bind host (default {DEFAULT_HOST})')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Bind port (default {DEFAULT_PORT})')
    args = ap.parse_args()

    server = HTTPServer((args.host, args.port), TTSProxyHandler)
    print(f'TTS cache proxy listening on http://{args.host}:{args.port}\nCache dir: {CACHE_DIR}\nUpstream: {UPSTREAM_URL}\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
