#!/usr/bin/env python3
"""
deploy-v0.py — Generate and deploy a web app from a prompt
Usage: python3 deploy-v0.py "build me a climate dashboard"

Deployment options (in priority order):
  1. VERCEL_TOKEN env var  → Vercel REST API
  2. vercel CLI authed     → vercel CLI
  3. Fallback              → save to /tmp/app.html
"""
import sys, os, json, time, subprocess, tempfile, shutil
from urllib.request import Request, urlopen
from urllib.error import HTTPError

NVIDIA_KEY  = os.environ.get("NVIDIA_API_KEY",
    "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")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN", "")
NVIDIA_BASE  = "https://integrate.api.nvidia.com/v1"

SYSTEM_PROMPT = """You are an expert web developer. Generate a complete, beautiful, self-contained HTML file for the requested app.

Requirements:
- Single HTML file with embedded CSS and JavaScript — NO external files
- Use Tailwind CSS via CDN: <script src="https://cdn.tailwindcss.com"></script>
- Use Chart.js via CDN for charts: <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
- Dark theme, professional look (dark background like #0f172a or #111827)
- Include realistic sample/simulated data — no real APIs needed
- Fully interactive (charts update, buttons work, animations run)
- Must work by opening directly in a browser — no server needed
- Return ONLY the raw HTML starting with <!DOCTYPE html>, no explanation, no markdown fences"""


def generate_app(prompt: str) -> str:
    """Use Nemotron-Super to generate a complete single-file HTML app."""
    print(f"  → Calling NVIDIA Nemotron-Super...")
    payload = {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Build this app: {prompt}"}
        ],
        "max_tokens": 4096,
        "temperature": 0.3,
        "top_p": 0.95,
    }
    req = Request(
        f"{NVIDIA_BASE}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {NVIDIA_KEY}"
        }
    )
    try:
        with urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
    except HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"NVIDIA API error {e.code}: {body}")

    html = data["choices"][0]["message"].get("content") or \
           data["choices"][0]["message"].get("reasoning_content") or ""
    html = html.strip()

    # Strip markdown code fences if present
    if html.startswith("```"):
        lines = html.split("\n")
        # remove first line (```html or ```) and last line (```)
        html = "\n".join(lines[1:])
        if html.rstrip().endswith("```"):
            html = "\n".join(html.rstrip().split("\n")[:-1])

    # Ensure it starts with a valid HTML tag
    if not html.lstrip().startswith("<!"):
        idx = html.find("<!DOCTYPE")
        if idx == -1:
            idx = html.find("<html")
        if idx >= 0:
            html = html[idx:]

    return html


def deploy_vercel_api(html_content: str, name: str) -> str:
    """Deploy via Vercel REST API (needs VERCEL_TOKEN)."""
    slug = name.lower().replace(" ", "-")[:40] + f"-{int(time.time())}"
    print(f"  → Deploying to Vercel (REST API) as '{slug}'...")
    payload = {
        "name": slug,
        "files": [
            {"file": "index.html", "data": html_content},
        ],
        "projectSettings": {"framework": None},
        "target": "production",
    }
    req = Request(
        "https://api.vercel.com/v13/deployments",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {VERCEL_TOKEN}",
        }
    )
    try:
        with urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        url = data.get("url") or f"{slug}.vercel.app"
        return f"https://{url}"
    except HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Vercel API error {e.code}: {body}")


def deploy_vercel_cli(html_content: str) -> str | None:
    """Deploy via vercel CLI if available and authed."""
    if not shutil.which("vercel"):
        return None
    # Check if authed
    auth_path = os.path.expanduser("~/.config/vercel/auth.json")
    if not os.path.exists(auth_path):
        return None
    try:
        with open(auth_path) as f:
            auth = json.load(f)
        if not auth.get("token"):
            return None
    except Exception:
        return None

    deploy_dir = tempfile.mkdtemp(prefix="deploy-v0-")
    try:
        with open(os.path.join(deploy_dir, "index.html"), "w") as f:
            f.write(html_content)
        print(f"  → Deploying via vercel CLI...")
        result = subprocess.run(
            ["vercel", deploy_dir, "--yes", "--prod"],
            capture_output=True, text=True, timeout=120
        )
        for line in result.stdout.splitlines():
            if line.startswith("https://"):
                return line.strip()
        # Sometimes it's the last line
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        if lines and lines[-1].startswith("https://"):
            return lines[-1]
    except Exception as e:
        print(f"  [vercel CLI] failed: {e}")
    finally:
        shutil.rmtree(deploy_dir, ignore_errors=True)
    return None


def deploy(html_content: str, prompt: str) -> str | None:
    """Try deployment methods in order, return URL or None."""
    # 1. Vercel REST API
    if VERCEL_TOKEN:
        return deploy_vercel_api(html_content, prompt[:30])

    # 2. Vercel CLI
    url = deploy_vercel_cli(html_content)
    if url:
        return url

    # 3. Local fallback
    out_path = "/tmp/app.html"
    with open(out_path, "w") as f:
        f.write(html_content)
    print(f"  [No deployment method] Saved locally → {out_path}")
    return None


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]).strip() or "build me a simple dashboard"

    print(f"\n🚀 deploy-v0.py")
    print(f"   Prompt: {prompt}")
    print(f"   VERCEL_TOKEN: {'set ✓' if VERCEL_TOKEN else 'not set (will save locally)'}")
    print()

    t0 = time.time()
    html = generate_app(prompt)
    gen_time = time.time() - t0
    print(f"  ✓ Generated {len(html):,} chars in {gen_time:.1f}s")

    url = deploy(html, prompt)

    print()
    if url:
        print(f"✅ Deployed: {url}")
    else:
        print(f"✅ Saved to /tmp/app.html  (open with: open /tmp/app.html)")
