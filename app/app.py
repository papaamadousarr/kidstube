from pathlib import Path

from flask import Flask, redirect, url_for

from app.db import db

APP_DIR = Path(__file__).resolve().parent


def create_app(start_scheduler: bool = False) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{APP_DIR / 'kidstube.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "kidstube-local-dev"

    db.init_app(app)

    from app.routes.analytics import bp as analytics_bp
    from app.routes.board import bp as board_bp
    from app.routes.calendar import bp as calendar_bp
    from app.routes.chat import bp as chat_bp
    from app.routes.generate import bp as generate_bp
    from app.routes.higgsfield import bp as higgsfield_bp
    from app.routes.ideas import bp as ideas_bp
    from app.routes.publish import bp as publish_bp

    app.register_blueprint(ideas_bp)
    app.register_blueprint(board_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(generate_bp)
    app.register_blueprint(publish_bp)
    app.register_blueprint(higgsfield_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(chat_bp)

    with app.app_context():
        db.create_all()

    if start_scheduler:
        from app import scheduler

        scheduler.init_scheduler(app)

    @app.route("/")
    def index():
        return redirect(url_for("board.board_view"))

    return app


if __name__ == "__main__":
    # use_reloader=False : le rechargeur Werkzeug relance tout le script dans un
    # sous-processus, ce qui démarrerait un second planificateur en double —
    # plus simple et plus sûr de le désactiver que de bricoler une détection.
    create_app(start_scheduler=True).run(
        debug=True, host="127.0.0.1", port=5000, threaded=True, use_reloader=False
    )
