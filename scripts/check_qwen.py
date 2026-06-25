"""Phase-0 access smoke (gate #1): confirm the Qwen Cloud key works and that the
model id is accepted on the DashScope *international* endpoint from this region.

Prereqs: ``pip install openai`` and ANAMNESIS_DASHSCOPE_API_KEY set in .env.
Run:     ``PYTHONPATH=src python scripts/check_qwen.py``
Expect:  ``qwen-max -> OK``
If the model id is rejected in-region, set QWEN_MODEL=qwen-plus in .env and re-run.
"""

from __future__ import annotations

from openai import OpenAI

from anamnesis.config import DASHSCOPE_BASE_URL, QWEN_MODEL, require


def main() -> None:
    client = OpenAI(api_key=require("ANAMNESIS_DASHSCOPE_API_KEY"), base_url=DASHSCOPE_BASE_URL)
    resp = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
    )
    print(f"{QWEN_MODEL} -> {resp.choices[0].message.content}")


if __name__ == "__main__":
    main()
