import os
from pathlib import Path

from flask import Flask


def create_app():
    app = Flask(__name__)
    secret_key = os.environ.get("FLASK_SECRET_KEY", "openscap-dev-secret")
    app.secret_key = secret_key

    data_dir = Path(os.environ.get("DATA_DIR", "/data"))

    # Initialise target registry (loads targets.json)
    from app import targets as target_registry
    target_registry.init(data_dir, secret_key)

    # Initialise SSH keypair
    from app import scanner
    scanner.init_ssh_keypair()

    # Initialise and start scheduler, re-register saved jobs
    from app import scheduler as sched_mod
    sched_mod.start()
    sched_mod.reload_jobs(target_registry.all_targets())

    # Teardown: stop scheduler when app context tears down
    @app.teardown_appcontext
    def _shutdown_scheduler(exc=None):
        sched_mod.shutdown()

    from app.routes import index as index_route
    from app.routes import import_ as import_route
    from app.routes import report as report_route
    from app.routes import network as network_route
    from app.routes import scan as scan_route

    app.register_blueprint(index_route.bp)
    app.register_blueprint(import_route.bp)
    app.register_blueprint(report_route.bp)
    app.register_blueprint(network_route.bp)
    app.register_blueprint(scan_route.bp)

    return app
