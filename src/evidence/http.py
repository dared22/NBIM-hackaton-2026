"""HTTP transport for SEC evidence and hosted model assessments."""

import gzip
import json
import time
import urllib.error
import urllib.request

USER_AGENT = "Hackathon 2026 student <iftikhar.amiri@nmbu.no>"


def get(url, tries=5):
    """GET with the SEC's required User-Agent, gzip to keep downloads small. Returns (status, bytes)."""
    for attempt in range(tries):
        time.sleep(0.5)  # 5 workers x 0.5 s keeps us at or under 10 requests a second
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return 200, raw
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, b""
            if attempt == tries - 1:
                return e.code, b""
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == tries - 1:
                return 0, b""
        time.sleep(2.0 * (attempt + 1))


URL = "https://openrouter.ai/api/v1/chat/completions"


def call_model(body, key, tries=4, *, url=URL, timeout=180, delay=2.0, retry_408=True):
    data = json.dumps(body).encode("utf-8")
    for attempt in range(tries):
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if (
                e.code not in ((408,) if retry_408 else ()) + (429, 500, 502, 503, 524, 529)
                or attempt == tries - 1
            ):
                raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8')[:300]}")
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == tries - 1:
                raise
        time.sleep(delay * (attempt + 1))
