# app/__init__.py
from flask import Flask, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)

    # Fix 4: Load environment-based config (development/production/testing)
    from config import get_config
    app.config.from_object(get_config())

    # Inicializar extensões
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    csrf.init_app(app)

    # Fix 2: Restrict CORS to webhooks and API routes only
    CORS(app, resources={r"/webhooks/*": {"origins": "*"}, r"/api/*": {"origins": "*"}})

    # Configurar login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'

    # Importar modelos e configurar user_loader
    from app.models.user import Creator

    @login_manager.user_loader
    def load_user(user_id):
        return Creator.query.get(int(user_id))

    # Registrar blueprints
    from app.routes import auth, dashboard, groups, admin, webhooks, api
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(groups.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(webhooks.bp)
    app.register_blueprint(api.bp)

    # Exempt webhooks from CSRF (uses Stripe signature verification)
    csrf.exempt(webhooks.bp)

    # Criar diretórios necessários
    import os
    os.makedirs('logs', exist_ok=True)
    os.makedirs('instance', exist_ok=True)

    # Fix 6: Redirecionar HTTP → HTTPS em produção (só quando SSL ativo)
    @app.before_request
    def redirect_to_https():
        if not app.debug and not app.testing and os.environ.get('FORCE_HTTPS', '').lower() in ('true', '1'):
            if request.headers.get('X-Forwarded-Proto', 'http') != 'https':
                url = request.url.replace('http://', 'https://', 1)
                return redirect(url, code=301)

    # Fix 7: Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # HSTS apenas em produção
        if not app.debug and not app.testing:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        # CSP permissivo para compatibilidade com Chart.js, Bootstrap e inline scripts
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://js.stripe.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.stripe.com; "
            "frame-src https://js.stripe.com; "
            "object-src 'none'; "
            "base-uri 'self'"
        )

        return response

    return app
