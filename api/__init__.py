"""Vercel entry package marker — exists so `tool.vercel.entrypoint = "api.index:app"` in
pyproject.toml resolves `api.index` as an importable module. The real entry logic (the
sys.path shim that makes the frozen `anamnesis` package importable) lives in api/index.py.
"""
