<!-- Satellite context file — extends the global hub (~/.claude/CLAUDE.md | ~/.pi/agent/AGENTS.md). Host-neutral; project-specific only. Do not duplicate hub standards here. -->

# Anamnesis

> A **Solana pre-trade forensic agent with compounding memory.** Paste a token mint; it investigates the deployer, funding trail, liquidity, and holder concentration — and because it *remembers every deployer it has ever seen* in a provenance-tracked, bi-temporal knowledge graph, a serial rugger's brand-new token gets flagged **on sight**, with the receipts.

*Anamnesis* (Greek: "recollection / un-forgetting"; in medicine, a patient's recalled case history) — the agent compiles the case history of every deployer and never forgets it.

**Live:** https://anamnesis.rectorspace.com · **Devpost:** https://devpost.com/software/anamnesis-solana-forensic-agent-with-memory · **Demo:** Vimeo 1207872741

## Architecture

A Qwen-Agent orchestrator over native memory tools (MongoDB/ApsaraDB) and an MCP forensic server (Helius), producing a memory-fused verdict. See `assets/architecture.svg`.

## Stack

Python (`pyproject.toml`, `uv.lock`) · FastAPI (`app.py`, `api/`) · Qwen-Agent orchestrator · MongoDB/ApsaraDB (bi-temporal knowledge graph) · MCP forensic server (Helius) · Vercel (frontend + API) · Docker (`Dockerfile`, `docker-compose.yml`).

## Common Commands

```bash
# Python (uv)
uv sync
uv run pytest            # tests
uv run python app.py     # API server
# Frontend
cd frontend && ...       # see frontend/README
```

## Structure

`api/` · `app/` · `app.py` · `src/` · `frontend/` · `mcp/` (forensic MCP server) · `workspace/` · `tests/` · `scripts/` · `deploy/` · `docs/` · `SPEC.md` · `PLAN.md` · `vercel.json`.

## Notes

- Shipped + Devpost submitted (Track=MemoryAgent). ECS torn down post-demo (billing stopped).
- Backend proof: log + 28s clip. Blog journal live at rectorspace.com/journal/building-anamnesis-qwen-memory-agent.
- See the cross-session TODO for post-submit optional work (README quickstart fix, MemoryBand scaling, useChatStream glitch, optional Vercel app deploy).