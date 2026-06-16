#!/usr/bin/env python3
"""Search-grounded Gemini query via the AI proxy — a hand-run review helper.

Grounding (web search) is NOT available on the proxy's OpenAI-compat
`/chat/completions` surface; it lives only on the *native* Gemini endpoint
(`…:generateContent` with the `google_search` tool). This wraps that call and
prints the answer plus its real grounding sources, so a `data-review` pass can
check a scraped field against the live web instead of trusting the store.

This is a dev/enrichment tool. NEVER call it from `scrape()` or CI — it is
network-bound and non-deterministic, which would break hashing and offline
tests (see AGENTS.md, "LLM access").

    export AI_PROXY_URL=$(gh variable get AI_PROXY_URL)
    python3 .claude/skills/data-review/ground.py "Does <provider> require a video for its 2026 summer intensive?"
    echo "long prompt…" | python3 .claude/skills/data-review/ground.py --json

Env: AI_PROXY_URL (token is baked into the path; no bearer needed).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# The proxy is Cloudflare-fronted and answers 403 (error 1010 "browser banned")
# to a non-browser User-Agent — a default urllib/httpx UA is rejected. Send a
# normal Chrome UA so the request is let through.
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def ground(prompt: str, model: str = "gemini-2.5-flash", timeout: float = 90.0) -> dict:
    """Return {text, queries, sources:[{title,uri}]} for a search-grounded query."""
    base = os.environ.get("AI_PROXY_URL", "").rstrip("/")
    if not base:
        raise SystemExit(
            "AI_PROXY_URL is not set (export AI_PROXY_URL=$(gh variable get AI_PROXY_URL))."
        )
    url = f"{base}/v1beta/models/{model}:generateContent"
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"AI proxy HTTP {exc.code}: {exc.read()[:400].decode(errors='replace')}")

    candidates = data.get("candidates") or []
    if not candidates:
        raise SystemExit(f"No candidates in response: {json.dumps(data)[:400]}")
    cand = candidates[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    meta = cand.get("groundingMetadata", {})
    sources = [
        {"title": c.get("web", {}).get("title", ""), "uri": c.get("web", {}).get("uri", "")}
        for c in meta.get("groundingChunks", [])
        if c.get("web")
    ]
    return {"text": text, "queries": meta.get("webSearchQueries", []), "sources": sources}


def main() -> int:
    ap = argparse.ArgumentParser(description="Search-grounded Gemini query via the AI proxy.")
    ap.add_argument("prompt", nargs="?", help="Prompt (or pipe it on stdin).")
    ap.add_argument("--model", default="gemini-2.5-flash", help="Grounding-capable model id.")
    ap.add_argument("--json", action="store_true", help="Emit raw JSON instead of formatted text.")
    args = ap.parse_args()

    prompt = args.prompt or sys.stdin.read().strip()
    if not prompt:
        ap.error("no prompt (pass an argument or pipe one on stdin)")

    result = ground(prompt, model=args.model)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(result["text"].strip())
    if result["queries"]:
        print("\n— searches:", "; ".join(result["queries"]))
    if result["sources"]:
        print("— sources:")
        for s in result["sources"]:
            print(f"  • {s['title'] or '(untitled)'} — {s['uri']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
