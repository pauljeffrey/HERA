"""Docker / local process entrypoint — starts uvicorn.

Prepopulate runs exactly once, from `app.main`'s lifespan hook. This used to
also run here, guarded by a second env flag (`HERA_SKIP_ENTRYPOINT_PREPOPULATE`),
which meant a misconfigured deploy could prepopulate twice.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    reload = os.getenv("HERA_RELOAD", "1") == "1"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=reload,
        reload_dirs=[str(os.getenv("HERA_RELOAD_DIR", "/app/app"))] if reload else None,
        # The log file and plot images both live under app/data/, which is
        # inside the watched reload dir — without this exclude, every log
        # write / chart render triggers a reload, causing an infinite
        # restart loop under --reload.
        reload_excludes=["*/data/*"] if reload else None,
    )


if __name__ == "__main__":
    main()
