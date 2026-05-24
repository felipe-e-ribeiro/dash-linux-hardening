import logging
from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8765, threaded=True)
