from flask import Flask, jsonify

from .migrate import init_db
from .routes.announcements import announcements_bp
from .routes.applications import applications_bp
from .routes.auth import auth_bp
from .routes.batches import batches_bp
from .routes.certs import certs_bp
from .routes.courses import courses_bp
from .routes.dashboard import dashboard_bp
from .routes.instructors import instructors_bp
from .routes.logs import logs_bp
from .routes.members_admin import members_bp
from .routes.notify import notify_bp
from .routes.public import public_bp
from .routes.quiz_admin import quiz_bp
from .routes.registrations import registrations_bp
from .routes.reports import reports_bp
from .routes.student import student_bp
from .routes.users import users_bp


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
    app.url_map.strict_slashes = False
    app.json.ensure_ascii = False

    init_db()

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(batches_bp, url_prefix="/api/batches")
    app.register_blueprint(registrations_bp, url_prefix="/api/registrations")
    app.register_blueprint(dashboard_bp, url_prefix="/api/admin/dashboard")
    app.register_blueprint(logs_bp, url_prefix="/api/admin/logs")
    app.register_blueprint(users_bp, url_prefix="/api/admin/users")
    app.register_blueprint(instructors_bp, url_prefix="/api/admin/instructors")
    app.register_blueprint(courses_bp, url_prefix="/api/admin/courses")
    app.register_blueprint(certs_bp, url_prefix="/api/admin/certs")
    app.register_blueprint(members_bp, url_prefix="/api/admin/members")
    app.register_blueprint(announcements_bp, url_prefix="/api/admin/announcements")
    app.register_blueprint(applications_bp, url_prefix="/api/admin/applications")
    app.register_blueprint(quiz_bp, url_prefix="/api/admin/quiz")
    app.register_blueprint(notify_bp, url_prefix="/api/admin/notify")
    app.register_blueprint(reports_bp, url_prefix="/api/admin/reports")
    app.register_blueprint(public_bp, url_prefix="/api/public")
    app.register_blueprint(student_bp, url_prefix="/api/me")

    @app.route("/api/health")
    def health():
        return jsonify({"ok": True})

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({"error": "檔案過大，請確認檔案大小"}), 413

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "找不到此路徑"}), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception(e)
        return jsonify({"error": "系統錯誤，請稍後再試"}), 500

    return app
