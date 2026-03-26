"""Docker deployment constants."""

import os
from pathlib import Path

DOCKER_BASE_PORT = 13000
DOCKER_DATA_DIR = Path(os.environ.get(
    "DOCKER_DATA_DIR",
    str(Path.home() / ".nodeskclaw" / "docker-instances"),
))
