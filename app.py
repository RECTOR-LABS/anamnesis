"""Anamnesis WebUI entrypoint.

Launches Qwen-Agent's built-in WebUI over build_agent() — the judged chat surface. The WebUI
import is deferred into main() so importing this module (e.g. to verify CHATBOT_CONFIG) does
not require the heavy GUI extra, which CI does not install.

Run locally:  python app.py   (needs ANAMNESIS_DASHSCOPE_API_KEY + ANAMNESIS_HELIUS_API_KEY in the env)
"""
from anamnesis.agent.agent import build_agent

# Demo affordances for the judged WebUI. A.10 swaps the concrete seeded mint into the
# suggestions; verbose surfaces the recall -> assess_risk -> MCP tool calls so the
# memory-first, cite-the-evidence reasoning is visible during the demo.
CHATBOT_CONFIG = {
    "prompt.suggestions": [
        "Should I ape this token? Paste a mint address.",
        "What do you already know about this deployer?",
        "Investigate this mint and cite the evidence behind your verdict.",
    ],
    "verbose": True,
    "input.placeholder": "Ask Anamnesis about a token or its deployer.",
}


def main() -> None:
    from qwen_agent.gui import WebUI

    WebUI(build_agent(), chatbot_config=CHATBOT_CONFIG).run()


if __name__ == "__main__":
    main()
