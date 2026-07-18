import os
import pathlib
import sys

# The in-repo SDK (loreweave_safety etc.) is a develop-install fixed at install time; on a host
# whose Python predates the SDK's requires-python it can't be re-discovered. Expose sdks/python
# from source so the shared safety floor imports (the container installs it normally).
_SDK = pathlib.Path(__file__).resolve().parents[3] / "sdks" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

os.environ.setdefault("KNOWLEDGE_DB_URL", "postgresql://u:p@h:5432/knowledge")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_token")
