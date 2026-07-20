"""Entrypoint: uvicorn server for Century Core (WP-5)."""
import uvicorn

from century_core.app import create_app
from century_core.config import Config

app = create_app()


def main() -> None:
    uvicorn.run(app, host=Config.HOST, port=Config.PORT)


if __name__ == "__main__":
    main()
