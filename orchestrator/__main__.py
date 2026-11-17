"""`python -m orchestrator` : lance l'orchestrateur sur ws://localhost:8000/ws."""

import logging
import os
from pathlib import Path

import uvicorn


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    env_file = Path(".env")
    uvicorn.run(
        "orchestrator.app:app",
        host=os.environ.get("PILOTE_HOST", "127.0.0.1"),
        port=int(os.environ.get("PILOTE_PORT", "8000")),
        env_file=str(env_file) if env_file.exists() else None,
    )


if __name__ == "__main__":
    main()
