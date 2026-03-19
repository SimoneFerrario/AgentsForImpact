#!/usr/bin/env python3
"""
Test script to verify Nemotron chat API is working
"""
import json
import time
from urllib.request import Request, urlopen

NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
NVIDIA_KEY = "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"
MODEL = "nvidia/nemotron-3-super-120b-a12b"

def test_nemotron_chat():
    """Test basic chat completion with Nemotron"""
    print(f"Testing Nemotron model: {MODEL}")
    print("-" * 60)

    messages = [
        {"role": "system", "content": "You are a helpful AI assistant powered by NVIDIA Nemotron. Be concise and helpful."},
        {"role": "user", "content": "Hello! Can you tell me what model you are running on?"}
    ]

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 600,
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
        print("Sending request to NVIDIA API...")
        t0 = time.time()
        with urlopen(req, timeout=90) as resp:
            elapsed = round((time.time() - t0) * 1000)
            body = json.loads(resp.read())

            print(f"\n✅ Success! (took {elapsed}ms)")
            print("\nFull Response:")
            print(json.dumps(body, indent=2))

            # Extract the actual message
            choice = body.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content") or message.get("reasoning_content") or ""

            print(f"\n📝 Assistant Reply:")
            print(content)
            print(f"\nModel: {body.get('model', 'unknown')}")

            return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_nemotron_chat()
    exit(0 if success else 1)
