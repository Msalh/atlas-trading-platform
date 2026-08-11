"""Select the reviewed Railway ASGI boundary without cross-service startup."""

import os


if os.getenv("RAILWAY_SERVICE_NAME") == "snapshot-private-api":
    from atlas_snapshot_api.runtime import app
else:
    from atlas.main import app

__all__ = ["app"]
