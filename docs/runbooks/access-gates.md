# Runbook — opening the access gates

Anamnesis depends on three external accounts ("access gates"). Each is a single env var
read at runtime via `config.require(...)`, which fails loudly with an actionable message
when the value is missing. This runbook is how you **open** each gate and **verify** it in
one command. It is the operational companion to `SPEC.md` (§"Two access gates must clear in
the first 48h" and §"Deployment — Alibaba Cloud").

| Gate | Service | Env var | Verify | Status |
|------|---------|---------|--------|--------|
| #1 | Qwen / DashScope (`qwen-max`) | `ANAMNESIS_DASHSCOPE_API_KEY` | `scripts/check_qwen.py` | ⬜ to open |
| #2 | ApsaraDB for MongoDB | `ANAMNESIS_MONGODB_URI` | `scripts/check_mongo.py` | ⬜ to open |
| #3 | Helius Solana RPC | `ANAMNESIS_HELIUS_API_KEY` | `scripts/check_helius.py` | ✅ open |

> Gates #1 and #2 are **external provisioning** — they need an Alibaba Cloud account,
> hackathon credits, and a managed instance. They cannot be opened from the codebase; this
> runbook is the checklist for the human who can. Once both are open, **A.10** (live agent /
> WebUI smoke, demo seed, Alibaba Cloud deploy) is unblocked.

## Secrets discipline (read first)

- All values live in `~/Documents/secret/.env` (iCloud-encrypted), **never** committed. The
  repo ships `.env.example` with the variable names only.
- The verify scripts **never print secret values** — `check_helius.py`/`check_mongo.py` keep
  the key/URI out of stdout, and on failure `check_mongo.py` surfaces only the pymongo
  exception *type* (a connection string carries a password; driver errors can echo it).
- Load the gate vars into a shell session without echoing them:

  ```bash
  for v in ANAMNESIS_DASHSCOPE_API_KEY ANAMNESIS_MONGODB_URI ANAMNESIS_HELIUS_API_KEY; do
    line=$(grep -E "^(export )?${v}=" ~/Documents/secret/.env | tail -1); export "$v=${line#*=}"
  done
  ```

---

## Cost model — target ≈ $0

SPEC's budget rule is *"target spend ≈ credits only"* — i.e. **~$0 out of pocket**, on free
tiers + the hackathon voucher. Verified Jun 2026 (cloud prices move; confidence flagged).

| Component | Best case (free tiers + voucher) | Worst case (no free tier) | Confidence |
|---|---|---|---|
| Qwen API (`qwen-max`/`qwen-plus`) | **$0** — 1M free tokens *per model*, 90d, **intl endpoint only**; + $40 voucher | ~$1–3 for the whole build | HIGH |
| ECS (backend) | **$0** — new-user free trial (1c/1GB, 12 mo) | ~$3.50–15 / mo | HIGH / MED |
| ApsaraDB MongoDB | **$0** — 1-month free trial covers the demo window | **~$30–55 / mo** ⚠️ | LOW (console-gated) |
| **Out of pocket** | **≈ $0** (only a ~$1 refundable card-verification hold) | **≈ $30–55** | — |

**Account note:** creating the Alibaba Cloud account is free but **requires a payment method**
(card/PayPal) + a ~$1 hold that is refunded. No upfront ID verification for international use.

**The $0 playbook:**
1. Claim the **$40 hackathon voucher** — <https://www.qwencloud.com/challenge/hackathon/voucher-application> — using the **same email** as your Devpost registration. (Whether it covers ECS/ApsaraDB or API-only is undocumented; treat it as API budget.)
2. Claim the **ApsaraDB MongoDB 1-month free trial** — zeroes the biggest cost *and* keeps the clean Alibaba proof artifact.
3. Claim the **ECS 12-month free trial** for the backend.
4. Use the **international / Singapore endpoint** — the 1M free token quota does **not** exist on the Global (US-Virginia) endpoint.
5. **Release every instance** the moment the demo is recorded.

**Biggest cost driver:** ApsaraDB MongoDB *managed compute* (~$30–55/mo, unverified). The
1-month free trial removes it for the demo window. Last-resort fallback if the trial is
unavailable: self-host MongoDB Community on the free ECS box (loses the cleaner ApsaraDB proof).

**Could not verify (do not bank on):** exact ApsaraDB compute price · whether the $40 covers
ECS/ApsaraDB or API-only · headline new-user credit amount (sources span $300–$1,700).

---

## Deployment decisions (what runs where, and why)

**Alibaba Cloud deployment is a pass/fail Stage-1 requirement** — the judged backend must run on
Alibaba Cloud, with a recording (SPEC §"Deployment — Alibaba Cloud"). That constraint, not cost,
decides the host.

| Stage | Host | Why |
|---|---|---|
| Develop / iterate | **reclabs3** (your VPS) or local | Persistent VM hosts the agent + its MCP stdio child cleanly; $0; fast |
| **Judged deploy + demo recording** | **Alibaba ECS + ApsaraDB** | Satisfies the mandatory Alibaba proof; both free-trial → $0 |

**Ruled out:**
- **Vercel (compute)** — (1) not Alibaba → fails the deploy gate; (2) serverless cannot host the
  agent, which spawns a **persistent FastMCP stdio child process**. SPEC rejected Alibaba's own
  Function Compute for this exact child-process seam; Vercel is the same serverless model.
- **Vercel MongoDB integration** — a non-Alibaba DB (Atlas, etc.) weakens the "uses Alibaba Cloud
  services" proof and saves nothing (the ApsaraDB free trial is already $0). Keep ApsaraDB.
- **Ollama Cloud / any non-Qwen-Cloud model** — *"Qwen models on Qwen Cloud"* is a hard rule, and
  `qwen-max` is closed-weight (DashScope-only; not served by Ollama). Qwen Cloud end to end.

**Portability:** config is env-var driven (`ANAMNESIS_*`), so dev → ECS is just env + redeploy —
no lock-in. Build on reclabs3; ship the final live demo to ECS and record it there.

---

## Gate #1 — Qwen / DashScope (`ANAMNESIS_DASHSCOPE_API_KEY`)

The agent calls `qwen-max` through the DashScope **international**, OpenAI-compatible endpoint
(`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`, hard-coded in `config.py`). Required
by the hackathon (Qwen-on-Qwen-Cloud is a hard rule).

**Open it:**
1. Create an Alibaba Cloud / Model Studio (DashScope) account on the **international** site.
   From Indonesia this is expected to work (SPEC §Eligibility — Indonesia is *not* excluded);
   confirm by registering. If registration/region is blocked, escalate per `SPEC.md` gate #1.
2. In Model Studio, **enable the model service and create an API key**. Docs:
   <https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope>
3. Put the key in `~/Documents/secret/.env`:
   ```
   ANAMNESIS_DASHSCOPE_API_KEY=sk-...
   ```
4. (Optional) If `qwen-max` is rejected in-region, set the documented fallback:
   ```
   QWEN_MODEL=qwen-plus
   ```

**Verify:**
```bash
PYTHONPATH=src .venv/bin/python scripts/check_qwen.py
# expect:  qwen-max -> OK
```
A success proves the **same** env var the agent consumes (`agent/agent.py` →
`config.require("ANAMNESIS_DASHSCOPE_API_KEY")`) is valid and the model id is accepted in-region.

---

## Gate #2 — ApsaraDB for MongoDB (`ANAMNESIS_MONGODB_URI`)

The compounding-memory store. ApsaraDB is also the cleanest **"uses Alibaba Cloud services"**
proof artifact required at judging (`SPEC.md` §Deployment, §Required proof).

**Open it:**
1. Claim Alibaba Cloud hackathon **credits** via the voucher form (SPEC gate #2) so the managed
   instance runs on credits.
2. Provision an **ApsaraDB for MongoDB** instance (managed). Product:
   <https://www.alibabacloud.com/product/apsaradb-for-mongodb>
3. Create a database user with **readWrite** on the `anamnesis` database, and add your client
   IP to the instance **allowlist** (managed instances reject unlisted IPs).
4. Assemble the connection URI and store it in `~/Documents/secret/.env` (URL-encode any special
   characters in the password):
   ```
   ANAMNESIS_MONGODB_URI=mongodb://<user>:<password>@<host>:<port>/?authSource=admin
   ANAMNESIS_DB=anamnesis   # optional; this is already the default
   ```

**Verify:**
```bash
PYTHONPATH=src .venv/bin/python scripts/check_mongo.py
# expect:  ANAMNESIS_DB 'anamnesis' reachable -> OK (0 collections)
```
This pings the server (connectivity) and lists the target DB's collections (auth + DB access) —
the same `ANAMNESIS_MONGODB_URI` + `ANAMNESIS_DB` that `agent/tools.py` uses. `0 collections` on a
fresh instance is expected.

---

## Gate #3 — Helius Solana RPC (`ANAMNESIS_HELIUS_API_KEY`) — already open

Kept here for completeness. Key is live and mainnet-validated.

**Verify:**
```bash
PYTHONPATH=src .venv/bin/python scripts/check_helius.py
# expect:  a non-empty authorities: [...] list for the USDC test mint
```

---

## After both gates open

With #1, #2, #3 green, **A.10** is unblocked:
- Live "ask the agent" / WebUI smoke (`app.py`) against `qwen-max`.
- Seed the demo deployer + token, wire the seeded mint into the WebUI suggestions.
- Deploy the backend (ECS) + ApsaraDB and capture the Alibaba Cloud deploy proof (code link +
  recording) for submission.

Phase-0 DoD (`SPEC.md`): *a deployed agent makes one real Solana read on Alibaba Cloud.*
