import pytest
from unittest.mock import patch

import app.scanner as _scanner
import app.scheduler as _scheduler
import app.targets as _targets


@pytest.fixture
def app():
    with patch.object(_scanner, "init_ssh_keypair"), \
         patch.object(_scheduler, "start"), \
         patch.object(_scheduler, "reload_jobs"), \
         patch.object(_targets, "init"):
        from app import create_app
        flask_app = create_app()
        flask_app.config["TESTING"] = True
        yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()
