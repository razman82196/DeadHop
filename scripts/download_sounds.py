from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print(
        "Playwright is not installed. Install with: python -m pip install playwright && python -m playwright install chromium",
        file=sys.stderr,
    )
    raise

AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}


def is_audio_href(href: str) -> bool:
    href = href.split("?")[0].split("#")[0]
    ext = Path(href).suffix.lower()
    return ext in AUDIO_EXTS


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def download(url: str, dest: Path, ua: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)") -> None:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def _try_click_more(page) -> None:
    candidates = [
        "text=Load more",
        "text=Show more",
        "text=More",
        "button:has-text('Load')",
        "button:has-text('More')",
        "button:has-text('Show more')",
    ]
    for sel in candidates:
        try:
            if page.is_visible(sel, timeout=500):
                page.click(sel, timeout=1000)
                page.wait_for_timeout(600)
        except Exception:
            pass


def _auto_scroll(page, rounds: int = 12, pause_ms: int = 350) -> None:
    for _ in range(rounds):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass
        page.wait_for_timeout(pause_ms)


def collect_audio_links(page_url: str, wait_ms: int = 2500) -> list[str]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        network_audio: set[str] = set()

        def on_response(resp):
            try:
                url = resp.url
                ct = resp.headers.get("content-type", "").lower()
                if is_audio_href(url) or ("audio/" in ct):
                    network_audio.add(url)
            except Exception:
                pass

        context.on("response", on_response)
        page = context.new_page()
        page.goto(page_url, wait_until="domcontentloaded")
        # Wait for network to settle, then a small extra delay for late JS
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(wait_ms / 1000.0)

        # Try to reveal lazy content
        _auto_scroll(page, rounds=15, pause_ms=300)
        _try_click_more(page)
        _auto_scroll(page, rounds=10, pause_ms=250)
        page.wait_for_timeout(wait_ms)

        # Try clicking obvious download anchors/buttons to trigger network requests
        click_selectors = [
            "a:has-text('Download')",
            "a.download",
            "button:has-text('Download')",
            "a[href*='/mp3/']",
            "a[href$='.mp3']",
            "a[href$='.wav']",
            "a[href$='.ogg']",
        ]
        for sel in click_selectors:
            try:
                els = page.query_selector_all(sel)
                for el in els:
                    try:
                        el.scroll_into_view_if_needed(timeout=500)
                        el.hover(timeout=500)
                        el.click(timeout=1000, button="middle")
                    except Exception:
                        # try normal click
                        try:
                            el.click(timeout=800)
                        except Exception:
                            pass
                page.wait_for_timeout(500)
            except Exception:
                pass

        # Collect <a href> links
        hrefs: list[str] = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.getAttribute('href'))",
        )
        base = page_url
        abs_links: set[str] = set()
        for h in hrefs:
            if not h:
                continue
            full = urljoin(base, h)
            if is_audio_href(full):
                abs_links.add(full)

        # Also check audio/source tags
        media_srcs = page.eval_on_selector_all(
            "audio[src], audio source[src]",
            "els => els.map(e => e.getAttribute('src'))",
        )
        # Some sites expose explicit download buttons with data-href or data-url
        data_links = page.eval_on_selector_all(
            "[data-href], [data-url]",
            "els => els.map(e => e.getAttribute('data-href') || e.getAttribute('data-url'))",
        )
        for s in media_srcs:
            if not s:
                continue
            full = urljoin(base, s)
            if is_audio_href(full):
                abs_links.add(full)
        for s in data_links:
            if not s:
                continue
            full = urljoin(base, s)
            if is_audio_href(full):
                abs_links.add(full)

        # Regex harvest from full HTML: capture any /mp3/*.mp3 references
        try:
            html = page.content()
        except Exception:
            html = ""
        if html:
            for m in re.findall(r"(https?://[^\"']*/mp3/[^\"']+?\.mp3)", html, flags=re.IGNORECASE):
                abs_links.add(m)
            for m in re.findall(r"(/mp3/[^\"']+?\.mp3)", html, flags=re.IGNORECASE):
                abs_links.add(urljoin(base, m))

        # Merge any audio discovered via network
        abs_links.update(network_audio)

        browser.close()
        return sorted(abs_links)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Download audio files from a JS-rendered page using Playwright"
    )
    ap.add_argument("--url", required=True, help="Page URL to scan")
    ap.add_argument("--out", required=True, help="Output directory for downloaded audio")
    ap.add_argument("--domain", default=None, help="Restrict downloads to this domain (optional)")
    ap.add_argument("--wait-ms", type=int, default=2500, help="Extra wait after network idle (ms)")
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()
    ensure_dir(out_dir)

    links = collect_audio_links(args.url, wait_ms=args.wait_ms)
    if args.domain:
        links = [u for u in links if urlparse(u).netloc.endswith(args.domain)]

    print(f"Found {len(links)} audio files.")
    count = 0
    for u in links:
        try:
            name = Path(urlparse(u).path).name or f"file_{count}.bin"
            dest = out_dir / name
            print(f"Downloading {u} -> {dest}")
            download(u, dest)
            count += 1
        except Exception as e:
            print(f"Failed {u}: {e}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
