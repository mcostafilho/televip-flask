# app/__init__.py
from flask import Flask, request, redirect, render_template, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
csrf = CSRFProtect()
oauth = OAuth()

def create_app():
    app = Flask(__name__)

    # Fix 4: Load environment-based config (development/production/testing)
    from config import get_config
    app.config.from_object(get_config())

    # ProxyFix para IP correto atrás do Nginx (1 proxy: Nginx)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Inicializar extensões
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    csrf.init_app(app)
    oauth.init_app(app)

    # Registrar Google OAuth provider
    oauth.register(
        name='google',
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

    # Fix 2: Restrict CORS to webhooks only (uses signature verification)
    CORS(app, resources={r"/webhooks/*": {"origins": "*"}})

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

    # Context processor: inject admin_viewing into all templates
    @app.context_processor
    def inject_admin_viewing():
        if current_user.is_authenticated and current_user.is_admin and session.get('admin_viewing_id'):
            from app.models.user import Creator as _Creator
            creator = _Creator.query.get(session['admin_viewing_id'])
            return {'admin_viewing': creator, 'is_admin_viewing': True}
        return {'admin_viewing': None, 'is_admin_viewing': False}

    # Custom error pages
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    # Criar diretórios necessários
    import os
    os.makedirs('logs', exist_ok=True)
    os.makedirs('instance', exist_ok=True)

    # Renovar sessão a cada request (timeout por inatividade, não absoluto)
    @app.before_request
    def refresh_session():
        session.permanent = True

    # Bloquear acesso de criadores bloqueados ao dashboard/groups
    @app.before_request
    def check_blocked_user():
        if current_user.is_authenticated and getattr(current_user, 'is_blocked', False):
            allowed_prefixes = ('/conta-bloqueada', '/logout', '/login', '/static')
            if not any(request.path.startswith(p) for p in allowed_prefixes):
                return redirect(url_for('auth.blocked_account'))

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
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com https://js.stripe.com https://www.googletagmanager.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://fonts.googleapis.com; "
            "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://cdn.jsdelivr.net https://api.stripe.com https://www.google-analytics.com https://*.google-analytics.com https://*.analytics.google.com https://accounts.google.com; "
            "frame-src https://js.stripe.com https://accounts.google.com; "
            "object-src 'none'; "
            "base-uri 'self'"
        )

        return response

    return app
