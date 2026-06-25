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
