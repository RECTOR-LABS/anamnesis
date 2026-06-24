# Anamnesis — Spec

> A **Solana pre-trade forensic agent with compounding memory.** You drop in a token; it investigates the deployer, funding trail, liquidity, and holder concentration — and because it *remembers every deployer it has ever seen* in a provenance-tracked, **bi-temporal knowledge graph**, a serial rugger's brand-new token gets flagged on sight with the receipts. Built on **Qwen** (via Qwen Cloud / DashScope) + **Qwen-Agent** + an **MCP** forensic toolset, deployed on **Alibaba Cloud**.

*Anamnesis* (Greek: "recollection / un-forgetting"; in medicine, a patient's recalled case history) — the agent compiles the *case history* of every deployer and never forgets it.

---

## ⏰ Deadline & format — READ FIRST
**Submit by Jul 9, 2026 @ 2:00 PM PDT** (= Jul 10, 04:00 WIB). Today is **Jun 22, 2026** → **~17 days, solo.** Fully online. This is a comfortable runway *only if* scope stays disciplined: the bi-temporal knowledge graph is the most ambitious surface and is built **inward-out** (see Build Phases) so a complete, demoable agent exists at every checkpoint and the graph deepens an already-shippable core — it is never the thing blocking submission.

Two access gates must clear in the first 48h, before real build:
1. **Qwen Cloud account + API key issuance from Indonesia** works (near-certain — Alibaba has a Jakarta region — but unverified until we sign up).
2. **Alibaba Cloud account + hackathon cloud credits** claimed (voucher form), since deployment proof on Alibaba Cloud is a hard, judged requirement.

## Hackathon context (authoritative)
- **Event:** Global AI Hackathon Series with Qwen Cloud (Devpost). Online. [qwencloud-hackathon.devpost.com](https://qwencloud-hackathon.devpost.com/)
- **Submission window:** May 25 → **Jul 9, 2026 2:00 PM PDT**. Judging Jul 10–31; winners ~Aug 7.
- **Five themed tracks** (each **$7K cash + $3K credits**): **MemoryAgent** · AI Showrunner · Agent Society · Autopilot Agent · EdgeAgent. Bonus: Honorable Mention + Blog Post Award (10× $500+$500 each). Pool **$70K+**.
- **Our track: MemoryAgent** — "persistent memory that accumulates experience, remembers across multi-turn / cross-session interactions, and improves decisions over time." Anamnesis answers this thesis *literally*: compounding memory **is** the product, not a feature bolted on.
- **Required stack (hard rules):**
  1. **Qwen models on Qwen Cloud** — required. We use `qwen-max` (strong agentic reasoning) via the DashScope **international** OpenAI-compatible endpoint, with a cheaper Qwen model as the high-volume fallback.
  2. **Proof of Alibaba Cloud deployment** — required and gated at Stage-1 judging. A link to a repo code file demonstrating use of Alibaba Cloud services/APIs **+** a short recording of the backend running on Alibaba Cloud.
  3. Agent framework — **not mandated** (unlike Google ADK). We choose **Qwen-Agent** (native MCP support; the natural Qwen analog to ADK).
  4. **MCP** — *not* required but explicitly rewarded under the 30% Innovation criterion ("sophisticated use of Qwen Cloud APIs, e.g. custom skills, MCP integrations"). We lead with it.
- **Deliverables:** public open-source repo (visible OSS license) · **<3-min** demo video (YouTube) · text description · **Alibaba Cloud deployment proof** · architecture diagram · stated track. Optional blog post → unlocks Blog Post Award.
- **Judging:** Innovation & AI Creativity **30%** · Technical Depth & Engineering **30%** · Problem Value & Impact **25%** · Presentation & Documentation **15%**. (Stage 1 is pass/fail on theme fit + viable API usage.)
- **Eligibility:** adults, solo allowed, no student restriction; excluded only where Qwen Cloud registration is unsupported or under sanctions. Indonesia is **not** excluded (confirm by registering — gate #1 above).

## Problem & target user
On-chain due-diligence is **amnesiac**. Every existing AI on-chain tool — Arkham's AI, Nansen Agent — is a *stateless query interface*: it re-investigates each token cold, hitting an API per question and remembering nothing between sessions. Serial scammers exploit exactly this: the *same* deployer wallets (or freshly-funded siblings from the same funder) recycle the *same* rug playbook across a stream of new tokens, and each new token looks "new" to a stateless tool.

**Primary user:** an active Solana trader deciding *"should I ape this token?"* before buying.
**The job:** given a token mint, return a fast, evidence-cited risk verdict — and get **measurably sharper every session** as the agent's private memory of deployers and scam clusters compounds.

## Concept

A single **Qwen-Agent `Assistant`** (model: `qwen-max`) whose tools are:
1. an **MCP forensic toolset** (a thin MCP server wrapping Helius) for grounded Solana reads — token profile, deployer, funding trace, holders, and **the deployer's prior-token history**;
2. **native memory tools** over a **bi-temporal forensic knowledge graph** in MongoDB — `recall`, `remember`, `assess_risk`, and (Phase B) `watchlist_add` / `draft_alert`.

The agent **checks memory first**, investigates via tools, writes findings back into the graph with **provenance**, and returns a verdict that **cites the on-chain evidence and the remembered history**. The compounding-memory payoff is concrete: a repeat deployer is an instant graph hit → instant retrieval of its `RUGGED` history → instant flag, in a fraction of a cold investigation's time.

### PSR (Problem → Solve → Results)
- **Problem:** amnesiac due-diligence lets serial ruggers recycle playbooks; stateless AI tools never learn the repeat offenders.
- **Solve:** an agent that builds a private, provenance-tracked, **bi-temporal** memory of wallets/deployers/funders/clusters and *compounds* it across sessions, hardened against on-chain memory-poisoning.
- **Results:** **"session 1 misses a fresh rug → by session 5 it catches it in <1s because it remembered the deployer from session 2,"** with a quantified *memory-hit vs cold-investigation* speed/accuracy metric — the demo's spine and the literal proof of the MemoryAgent thesis.

### Why this is defensible (not "Arkham/Rektradar with a chatbot")
The deployer-clustering *capability* is not itself new (Rektradar, TRM). Anamnesis's defensibility rests **entirely on the memory framing**: existing tools query *their* graph statelessly; Anamnesis grows *your* compounding forensic memory and gets demonstrably better at catching repeat offenders the more you use it. Every pitch leads with **memory + measurable compounding + memory-integrity**, never with "we detect scams."

## MVP features (YAGNI-tight, inward-out)
1. **One agent, memory-first.** Qwen-Agent `Assistant` on `qwen-max`; tools = forensic MCP + native memory tools. No multi-agent, no fine-tuning.
2. **Grounded forensic investigation** of a token mint: deployer identity, mint/freeze-authority status, LP burned/locked, top-holder concentration, deployer funding trace, **deployer's prior tokens and their fate.** Every signal cites the on-chain source.
3. **Compounding memory** in a bi-temporal knowledge graph: each investigation upserts nodes/edges with provenance; a repeat entity is an instant recall.
4. **Provenance-weighted poisoning defense:** verdicts use trust-weighted aggregation + corroboration so adversary-seeded on-chain breadcrumbs can't flip a call.
5. **Risk verdict** with a plain-English rationale, the cited evidence chain, and the remembered history.
6. **Hosted on Alibaba Cloud** — chat surface = **Qwen-Agent's built-in WebUI** (`qwen-agent[gui]`, no custom frontend), plus a minimal relationship-graph view (Phase B) for the "watch it connect the dots" demo moment.

**Deferred past MVP:** multi-chain (EVM), wallet-level portfolio analysis, write/trade actions, auth/multi-tenant, fine-tuning, a bespoke design system.

## Architecture (grounded in verified current docs)

**Solana-first.** Single Python backend, deployed on Alibaba Cloud:

```
Trader ──chat──▶ thin UI + relationship-graph view   (on Alibaba Cloud)
                      │
                      ▼
        Qwen-Agent  Assistant   (model: qwen-max via DashScope-intl, OpenAI-compatible)
          ├─ MCP toolset ──▶ Solana Forensics MCP  (wraps Helius DAS + Enhanced Tx)
          │     get_token_profile · get_deployer · get_holders
          │     (trace_funding · get_deployer_token_history — deferred: need a
          │      funding-source address set + an on-chain mint-scan + live Helius)
          └─ native tools:  recall() · remember() · assess_risk()
                            · watchlist_add() · draft_alert()        (Phase B)
                                │
                                ▼
              Bi-temporal forensic knowledge graph
              (ApsaraDB for MongoDB — Alibaba Cloud managed)
              collections: entities (nodes) · relations (bi-temporal edges)
```

### Qwen-Agent wiring (verbatim-faithful to current Qwen-Agent docs)
```python
import os
from qwen_agent.agents import Assistant

# Qwen via DashScope international, OpenAI-compatible mode.
# (model_type 'oai' + model_server = the compatible-mode base URL;
#  'qwen_dashscope' is the native alternative.)
llm_cfg = {
    "model": "qwen-max",
    "model_server": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "api_key": os.environ["DASHSCOPE_API_KEY"],
    "model_type": "oai",
    "generate_cfg": {"top_p": 0.8},
}

# Forensic MCP server + native memory tools share one function_list.
tools = [
    {"mcpServers": {
        "solana_forensics": {
            "command": "python",   # the project venv interpreter (sys.executable in code)
            "args": ["mcp/solana_forensics_mcp.py"],
            # HELIUS_API_KEY flows through the child process env, never argv.
        }
    }},
    "recall", "remember", "assess_risk",            # native @register_tool tools
]

agent = Assistant(
    llm=llm_cfg,
    name="anamnesis",
    system_message=SYSTEM_INSTRUCTION,   # memory-first, cite-everything, distrust-uncorroborated
    function_list=tools,
)
```

Native tools follow Qwen-Agent's `@register_tool('name') / class(BaseTool) / def call(self, params, **kwargs)` pattern. **MODEL NOTE:** model ids drift — confirm `qwen-max` (or `qwen3-max`) is accepted on the international endpoint on Day 1; keep a cheaper Qwen model (`qwen-plus`/`qwen-flash`) as the high-volume fallback. Tools cannot be combined with `stream=True` in OpenAI-compatible mode.

### The bi-temporal forensic knowledge graph (the technical-depth core)
A property graph in MongoDB. **Nodes** (`entities`): `Wallet`, `Token`, `LiquidityPool`, `FundingSource` (CEX/bridge/mixer), `Cluster`. **Edges** (`relations`): `DEPLOYED`, `FUNDED_BY`, `PROVIDES_LP`, `SAME_CLUSTER`, `RUGGED`.

Every edge is **bi-temporal**, carrying two independent time axes plus provenance:
```
{
  type: "DEPLOYED", from: "<wallet>", to: "<mint>",
  valid_from, valid_to,        // when the fact was true ON-CHAIN  (valid time)
  recorded_at, superseded_at,  // when the AGENT learned/revised it (transaction time)
  provenance: { source, method, confidence }   // e.g. "helius:getAsset", first-party, 0.95
}
```
- **Time-travel queries:** *"what did we believe about this deployer as of last week"* (filter `recorded_at ≤ T < superseded_at`) vs *"what was true on-chain at time T"* (filter `valid_from ≤ T < valid_to`). This bi-temporal separation — not the storage engine — is the sophistication.
- **Compounding = a cache hit:** repeat deployer → instant node match → instant `RUGGED`-history retrieval. The "N× sharper" metric is memory-hit latency vs cold-investigation latency.
- **Substrate decision:** **MongoDB-native bi-temporal**, not Graphiti+Neo4j. The sophistication is the bi-temporal logic; one DB means a far cleaner Alibaba deploy, and **ApsaraDB for MongoDB doubles as the Alibaba Cloud deployment proof.**

### Forensic data layer (Helius)
Verified-capable; exact endpoints confirmed Day 1:
- **Token profile / authorities:** Helius DAS `getAsset` (mint authority, freeze authority, metadata).
- **Holders / concentration:** `getTokenAccounts` / RPC `getTokenLargestAccounts` (top-holder %).
- **Deployer + prior tokens (the memory crux):** `getAssetsByCreator` / `getSignaturesForAddress` on the deployer wallet → the set of tokens it has launched and their outcomes.
- **Funding trace:** Helius Enhanced Transactions (parsed history) → where the deployer's SOL came from (CEX / bridge / mixer / known-bad cluster).
- **LP status:** pool account + LP-token burn/lock checks.

Fallback if the MCP seam fights us Day 1: call Helius directly as Qwen-Agent function tools (lose the MCP innovation flourish, keep the agent). `HELIUS_API_KEY` via env only, never argv/committed.

### Poisoning defense (AI-safety story, banks Innovation points)
On-chain memory is adversarial — attackers can seed misleading breadcrumbs (e.g., dust transfers to fabricate a `SAME_CLUSTER` link). Defense: every edge's `provenance.confidence` plus a **corroboration count**; `assess_risk` uses **trust-weighted aggregation**, so first-party facts we derived from RPC/DAS dominate and uncorroborated "claims" an adversary could plant carry near-zero weight and cannot flip a verdict. Directly answers the documented 2026 memory-poisoning attack class.

## Deployment — Alibaba Cloud (mandatory, judged)
- **Compute:** backend (Python agent + Qwen-Agent WebUI + the Python forensic-MCP child process) on **Alibaba Cloud ECS** (primary). ECS is chosen deliberately over Function Compute: the agent spawns the MCP server as a **child process** (the exact child-subprocess-in-a-serverless-container seam that bit Velox's Google-Cloud analog), and a persistent VM hosts that cleanly. Function Compute (scale-to-zero, cheaper) is the noted alternative *only if* Phase-0 proves the subprocess model runs there.
- **Memory:** **ApsaraDB for MongoDB** (managed) — also the cleanest "uses Alibaba Cloud services/APIs" proof artifact.
- **Model:** Qwen via DashScope international (OpenAI-compatible).
- **Required proof:** a repo code file using the Alibaba Cloud SDK/service (the ApsaraDB client config / Function Compute handler) **+** a short recording of the backend running on Alibaba Cloud.
- **Credits:** claimed via the hackathon voucher form (gate #2). Target spend ≈ credits only.

## Non-goals
- No write/trade/transaction-signing actions (read-only forensics; Phase-B "acts" = watchlist + drafted alert with human-in-the-loop, never an on-chain action).
- No EVM/multi-chain in MVP (Solana-first; architecture leaves room).
- No auth/multi-tenant, no PII, no fine-tuning, no bespoke design system.
- No second model provider — Qwen only (hackathon rule + focus).

## Risks & unknowns
| Risk | Likelihood | Mitigation |
|---|---|---|
| **Data layer** — reliable deployer + funding-trace + holder pulls for an arbitrary token | **High** | Day-1 tracer bullet through Helius end-to-end before any feature; direct-function-tool fallback if the MCP seam stalls. |
| **Bi-temporal scope** eats the timeline (solo) | **High** | Inward-out build (A→B→C); the graph deepens an already-shippable agent and is never on the submission critical path. |
| **Alibaba Cloud deploy friction** (new platform; mandatory proof) | **Med-High** | Derisk in first 48h: stand up a hello-world backend + ApsaraDB before features; never leave deploy to the last days. |
| **Qwen account/keys from Indonesia** | Med | Register Day 0; if blocked, escalate to RECTOR / alternative region. Gate #1. |
| **Exact Qwen model id / region availability** | Med | Confirm `qwen-max` accepted on intl endpoint Day 1; cheaper-Qwen fallback. |
| **"We're not Rektradar" framing** | Med | Every artifact leads with *memory + compounding + integrity*, never with scam-detection. |
| **Memory-poisoning makes the agent confidently wrong** | Low-Med (by design) | Provenance-weighted trust + corroboration; first-party-only high confidence. |
| **Solo bandwidth over 17 days** | Med | Hard scope freeze after Phase B lands; remaining days = demo + Alibaba proof + submission. |

## Build phases (inward-out — each phase is shippable)
- **Phase 0 — Access & tracer (Day 0–2):** Qwen key from Indonesia ✔, Alibaba credits ✔, hello-world Qwen-Agent answering with one Helius read ✔, hello-world backend on Alibaba Cloud + ApsaraDB ✔. *DoD: a deployed agent makes one real Solana read on Alibaba Cloud.*
- **Phase A — Lean MemoryAgent (core):** forensic MCP tools, MongoDB entity store w/ provenance, `recall`/`remember`/`assess_risk`, verdict with cited evidence + remembered history. *DoD: investigate→remember→verdict; a repeat deployer is an instant memory hit.*
- **Phase B — MemoryAgent that acts:** threshold-triggered `watchlist_add` + `draft_alert` (human-in-the-loop), relationship-graph view. *DoD: a remembered repeat offender auto-drafts an alert; graph lights up the cluster.* **Scope freeze here.**
- **Phase C — Bi-temporal + time-travel (stretch on the already-shippable B):** dual-axis edges + "what did we know as of T" queries; deepen poisoning defense. *DoD: a time-travel query demonstrably distinguishes valid-time from transaction-time.*
- **Submission (final days):** README + SVG architecture diagram, OSS license, secret-scan, **<3-min demo video**, **Alibaba deploy proof** (code link + recording), Devpost form (track = MemoryAgent), optional blog post.

## Submission checklist
- [ ] **Hosted on Alibaba Cloud** — backend reachable; agent answers a live investigation; **deploy proof** (code file + recording) ready.
- [ ] **Public open-source repo** w/ visible **OSS license**, README (overview + SVG architecture diagram + Qwen/MCP/memory notes), **zero secrets** (env-var refs only; `.env.example`; secret-scanned).
- [ ] **<3-min demo video** (YouTube) — cold investigation → verdict → two more from the same deployer → 4th fresh token **instant memory flag** + graph cluster → the N× metric → one line on Qwen + Qwen-Agent + MCP + Alibaba.
- [ ] **Architecture diagram** (Qwen Cloud ↔ backend ↔ ApsaraDB ↔ frontend).
- [ ] **Text description** + **track = MemoryAgent** stated.
- [ ] **Qwen-only** model usage; `--readOnly` posture on all on-chain reads; provenance/poisoning defense documented.
- [ ] (Optional) **Blog post** on the build journey → Blog Post Award eligibility.

---

**Doc sources (verified current, Jun 2026):**
- Hackathon: https://qwencloud-hackathon.devpost.com/ · /rules · /resources
- Qwen-Agent: https://github.com/QwenLM/Qwen-Agent · https://qwenlm.github.io/Qwen-Agent/
- DashScope OpenAI-compatible (intl): https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope
- Helius (DAS + Enhanced Tx): https://www.helius.dev/docs
- ApsaraDB for MongoDB: https://www.alibabacloud.com/product/apsaradb-for-mongodb
- Memory-poisoning (context): arXiv 2601.05504 · Palo Alto Unit 42 long-term-memory poisoning
