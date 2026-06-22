# Anamnesis

> A **Solana pre-trade forensic agent with compounding memory.** Drop in a token; it investigates the deployer, funding trail, liquidity, and holder concentration — and because it *remembers every deployer it has ever seen* in a provenance-tracked, bi-temporal knowledge graph, a serial rugger's brand-new token gets flagged on sight, with the receipts.

*Anamnesis* (Greek: "recollection / un-forgetting"; in medicine, a patient's recalled case history) — the agent compiles the case history of every deployer and never forgets it.

**Status:** 📐 Pre-build — see [`SPEC.md`](./SPEC.md) and [`PLAN.md`](./PLAN.md).

| | |
|---|---|
| **Hackathon** | Global AI Hackathon with Qwen Cloud (Devpost) — **MemoryAgent** track |
| **Submit by** | Jul 9, 2026 2:00 PM PDT · $70K+ |
| **Stack** | Python · Qwen-Agent · `qwen-max` (DashScope-intl) · MCP · Helius · MongoDB/ApsaraDB · Alibaba Cloud |

The differentiator is **memory**, not detection: existing on-chain AI tools query statelessly and re-investigate every token cold; Anamnesis builds a private forensic memory that **compounds across sessions** and gets measurably sharper at catching repeat-offender deployers — hardened against on-chain memory-poisoning via provenance-weighted trust.

## License
MIT — see [`LICENSE`](./LICENSE). Synthetic/demo data; not financial advice.
