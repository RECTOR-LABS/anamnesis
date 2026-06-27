"""A.10 demo seed entrypoint — thin shell over anamnesis.demo_seed.

Seeds the approved serial-rugger's prior-rug history so the live agent flags the deployer's
new clean-looking token HIGH from memory alone. Implementation + design rationale live in
anamnesis.demo_seed / docs/design/2026-06-27-a10-demo-seed-design.md.

Run:  PYTHONPATH=src python scripts/seed_demo.py            # idempotent seed
      PYTHONPATH=src python scripts/seed_demo.py --reset    # clear demo collections first
      PYTHONPATH=src python scripts/seed_demo.py --metric   # print the N× memory-vs-cold metric
Needs ANAMNESIS_MONGODB_URI (+ ANAMNESIS_HELIUS_API_KEY for --metric) in the env.
"""
from anamnesis.demo_seed import main

if __name__ == "__main__":
    raise SystemExit(main())
