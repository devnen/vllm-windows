from __future__ import annotations
import json
import time
import httpx


def test_chat(port: int, model: str = "any", timeout: float = 60.0,
              host: str = "127.0.0.1") -> dict:
    """Stream a tiny chat completion and return summary stats."""
    url = f"http://{host}:{port}/v1/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "What is 2+2? One sentence."}],
        "max_tokens": 50,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    text_chunks: list[str] = []
    completion_tokens = 0
    prompt_tokens = 0
    t0 = time.perf_counter()
    t_first = None
    try:
        with httpx.stream("POST", url, json=body, timeout=timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                if obj.get("usage"):
                    completion_tokens = obj["usage"].get("completion_tokens", completion_tokens)
                    prompt_tokens = obj["usage"].get("prompt_tokens", prompt_tokens)
                for ch in obj.get("choices", []) or []:
                    delta = ch.get("delta", {}).get("content")
                    if delta:
                        if t_first is None:
                            t_first = time.perf_counter()
                        text_chunks.append(delta)
        t_end = time.perf_counter()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    elapsed = t_end - t0
    decode_time = (t_end - t_first) if t_first else elapsed
    text = "".join(text_chunks)
    decode_tps = (completion_tokens / decode_time) if (completion_tokens and decode_time > 0) else 0.0
    return {
        "ok": True,
        "text": text,
        "completion_tokens": completion_tokens,
        "prompt_tokens": prompt_tokens,
        "decode_tps": decode_tps,
        "ttft_s": (t_first - t0) if t_first else None,
        "total_s": elapsed,
    }
