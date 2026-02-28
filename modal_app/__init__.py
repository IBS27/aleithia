"""Alethia Modal app — all functions must be transitively imported here for discovery.

These imports run at deploy time (locally) so Modal can discover all functions.
Inside containers, each function only imports its own dependencies, so we guard
these imports to avoid pulling in packages that aren't installed in every image.
"""
import os as _os

from modal_app.volume import app  # noqa: F401  — always safe, only depends on modal

# Only import all modules for function discovery during `modal deploy` (local machine).
# Inside containers, Modal imports the specific function module directly.
if not _os.environ.get("MODAL_IS_REMOTE"):
    from modal_app import agents  # noqa: F401
    from modal_app import compress  # noqa: F401
    from modal_app import scaling_demo  # noqa: F401
    from modal_app import classify  # noqa: F401
    from modal_app import llm  # noqa: F401
    from modal_app import web  # noqa: F401
    from modal_app import reconciler  # noqa: F401
    from modal_app import supermemory  # noqa: F401
    from modal_app.pipelines import news  # noqa: F401
    from modal_app.pipelines import reddit  # noqa: F401
    from modal_app.pipelines import public_data  # noqa: F401
    from modal_app.pipelines import politics  # noqa: F401
    from modal_app.pipelines import demographics  # noqa: F401
    from modal_app.pipelines import reviews  # noqa: F401
    from modal_app.pipelines import realestate  # noqa: F401
    from modal_app.pipelines import federal_register  # noqa: F401
    from modal_app.pipelines import traffic  # noqa: F401
