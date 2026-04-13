import os

# Populate required env vars BEFORE any `app.*` import. Pytest imports test
# modules at collection time; without these, `from app.config import settings`
# would raise during collection.
os.environ.setdefault("KNOWLEDGE_DB_URL", "postgresql://u:p@h:5432/knowledge")
os.environ.setdefault("GLOSSARY_DB_URL", "postgresql://u:p@h:5432/glossary")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "default_test_token")
os.environ.setdefault("JWT_SECRET", "s" * 32)
