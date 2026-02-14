from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, session
from flask_login import login_user, logout_user, current_user, login_required
from app import db, limiter, oauth
from app.models import Creator, Report
from app.utils.email import send_password_reset_email, send_welcome_email, send_confirmation_email
from app.utils.security import generate_reset_token, verify_reset_token, generate_confirmation_token, verify_confirmation_token, is_safe_url
import re
import logging
import secrets
from datetime import datetime

bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


def _regenerate_session():
    """Regenera o session ID mantendo os dados (previne session fixation).

    Flask cookie-based sessions don't have a server-side ID, but clearing
    and re-setting with a fresh nonce forces a new signed cookie to be issued.
    """
    data = dict(session)
    session.clear()
    session.update(data)
    # Add a random nonce to guarantee the cookie value changes
    session['_csrf_nonce'] = secrets.token_hex(8)

@bp.route('/')
def index():
    """Página inicial - redireciona para login ou dashboard"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return render_template('public/landing.html')

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        remember = request.form.get('remember', False)

        user = Creator.query.filter_by(email=email).first()
        if not user:
            # Dummy check to prevent timing-based email enumeration
            from werkzeug.security import check_password_hash
            check_password_hash(
                'scrypt:32768:8:1$dummy$0000000000000000000000000000000000000000000000000000000000000000',
                password
            )
        if user and user.check_password(password):
            if not user.is_verified:
                flash('Confirme seu email antes de fazer login. Verifique sua caixa de entrada.', 'warning')
                return render_template('auth/login.html', unverified_email=email)
            # Vincular Google pendente (se veio do fluxo OAuth)
            pending_google_id = session.pop('pending_google_id', None)
            if pending_google_id and not user.google_id:
                user.google_id = pending_google_id
                db.session.commit()
                flash('Conta Google vinculada com sucesso!', 'success')
            user.update_last_login()
            # Regenerar sessão para prevenir session fixation
            _regenerate_session()
            login_user(user, remember=bool(remember))
            next_page = request.args.get('next')
            if next_page and not is_safe_url(next_page):
                next_page = None
            flash(f'Bem-vindo de volta, {user.name}!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('dashboard.index'))
        else:
            flash('Email ou senha incorretos. Tente novamente.', 'error')

    return render_template('auth/login.html')

@bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        accept_terms = request.form.get('accept_terms')

        # Validações
        errors = []

        if not accept_terms:
            errors.append('Você precisa aceitar os Termos de Uso e a Política de Privacidade')

        # Validar nome
        if len(name) < 3:
            errors.append('Nome deve ter pelo menos 3 caracteres')

        # Validar email
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            errors.append('Email inválido')
        elif Creator.query.filter_by(email=email).first():
            errors.append('Email ou username já em uso.')

        # Validar username
        if not re.match(r'^[a-z0-9]+$', username):
            errors.append('Username deve conter apenas letras minúsculas e números')
        elif len(username) < 3:
            errors.append('Username deve ter pelo menos 3 caracteres')
        elif Creator.query.filter_by(username=username).first():
            # Sugerir alternativas
            base = re.sub(r'\d+$', '', username)
            suggestions = []
            for i in range(1, 100):
                candidate = f"{base}{i}"
                if not Creator.query.filter_by(username=candidate).first():
                    suggestions.append(candidate)
                    if len(suggestions) >= 3:
                        break
            hint = ', '.join(suggestions)
            errors.append(f'Username já em uso. Sugestões: {hint}')

        # Validar senha
        if len(password) < 8:
            errors.append('A senha deve ter pelo menos 8 caracteres')
        elif not any(c.isupper() for c in password):
            errors.append('A senha deve conter pelo menos uma letra maiuscula')
        elif not any(c.isdigit() for c in password):
            errors.append('A senha deve conter pelo menos um numero')
        elif password != confirm_password:
            errors.append('As senhas nao coincidem')

        # Se houver erros, mostrar
        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            # Criar novo usuário com prova jurídica do aceite dos termos
            user = Creator(
                name=name,
                email=email,
                username=username,
                terms_accepted_at=datetime.utcnow(),
                terms_ip=request.remote_addr,
                terms_user_agent=request.headers.get('User-Agent', '')[:500]
            )
            user.set_password(password)

            db.session.add(user)
            db.session.commit()

            # Enviar email de confirmacao
            try:
                token = generate_confirmation_token(user.email)
                send_confirmation_email(user, token)
            except Exception:
                logger.error("Failed to send confirmation email", exc_info=True)

            flash('Conta criada! Verifique seu email para confirmar sua conta.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("3 per minute", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        user = Creator.query.filter_by(email=email).first()
        # Só enviar reset para contas com senha (bloqueia contas OAuth-only)
        if user and user.password_hash:
            token = generate_reset_token(user.id, password_hash=user.password_hash)
            try:
                send_password_reset_email(user, token)
            except Exception:
                logger.error("Failed to send password reset email", exc_info=True)

        # Mensagem genérica sempre (previne enumeração de usuários)
        flash('Se o email estiver cadastrado, você receberá as instruções.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def reset_password(token):
    if current_user.is_authenticated:
        logout_user()

    # First decode without hash check to get user_id
    user_id = verify_reset_token(token)
    if not user_id:
        flash('Link inválido ou expirado. Solicite um novo.', 'error')
        return redirect(url_for('auth.forgot_password'))

    user = Creator.query.get(user_id)
    if not user:
        flash('Usuário não encontrado.', 'error')
        return redirect(url_for('auth.login'))

    # Verify token hasn't been used (password hash still matches)
    user_id = verify_reset_token(token, current_password_hash=user.password_hash)
    if not user_id:
        flash('Este link já foi utilizado. Solicite um novo.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if len(password) < 8:
            flash('A senha deve ter pelo menos 8 caracteres', 'error')
        elif not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
            flash('A senha deve conter pelo menos uma letra maiuscula e um numero', 'error')
        elif password != confirm_password:
            flash('As senhas nao coincidem', 'error')
        else:
            # Atualizar senha
            user.set_password(password)
            db.session.commit()

            flash('Senha alterada com sucesso! Faça login com a nova senha.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)

@bp.route('/confirm-email/<token>')
@limiter.limit("10 per minute")
def confirm_email(token):
    """Confirmar email via token"""
    email = verify_confirmation_token(token)
    if not email:
        flash('Link de confirmacao invalido ou expirado.', 'error')
        return redirect(url_for('auth.login'))

    user = Creator.query.filter_by(email=email).first()
    if not user:
        flash('Usuario nao encontrado.', 'error')
        return redirect(url_for('auth.login'))

    if user.is_verified:
        flash('Email ja confirmado! Faca login.', 'info')
        return redirect(url_for('auth.login'))

    user.is_verified = True
    db.session.commit()

    # Enviar email de boas-vindas agora que confirmou
    try:
        send_welcome_email(user)
    except Exception:
        logger.error("Failed to send welcome email", exc_info=True)

    flash('Email confirmado com sucesso! Faca login para comecar.', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/resend-confirmation', methods=['POST'])
@limiter.limit("3 per minute")
def resend_confirmation():
    """Reenviar email de confirmacao"""
    email = request.form.get('email', '').strip().lower()

    user = Creator.query.filter_by(email=email).first()
    if user and not user.is_verified:
        try:
            token = generate_confirmation_token(user.email)
            send_confirmation_email(user, token)
        except Exception:
            logger.error("Failed to resend confirmation email", exc_info=True)

    flash('Se o email estiver cadastrado, voce recebera um novo link de confirmacao.', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/auth/google')
def google_login():
    """Inicia o fluxo OAuth com Google"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    nonce = secrets.token_urlsafe(32)
    session['google_oauth_nonce'] = nonce
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri, nonce=nonce)


@bp.route('/auth/google/callback')
def google_callback():
    """Callback do Google OAuth — login, vinculação ou cadastro"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    try:
        token = oauth.google.authorize_access_token()
        nonce = session.pop('google_oauth_nonce', None)
        user_info = oauth.google.parse_id_token(token, nonce=nonce)
    except Exception:
        logger.error("Google OAuth callback failed", exc_info=True)
        flash('Erro ao autenticar com Google. Tente novamente.', 'error')
        return redirect(url_for('auth.login'))

    google_id = user_info.get('sub')
    email = user_info.get('email', '').lower()
    name = user_info.get('name', '')

    if not google_id or not email:
        flash('Não foi possível obter suas informações do Google.', 'error')
        return redirect(url_for('auth.login'))

    # 1. Buscar por google_id (já vinculado)
    user = Creator.query.filter_by(google_id=google_id).first()

    # 2. Se não achou, buscar por email
    if not user:
        existing = Creator.query.filter_by(email=email).first()
        if existing:
            if existing.password_hash:
                # Conta com senha — exigir login para vincular (previne account takeover)
                session['pending_google_id'] = google_id
                flash('Já existe uma conta com este email. Faça login com sua senha para vincular o Google.', 'warning')
                return redirect(url_for('auth.login'))
            else:
                # Conta OAuth-only (sem senha) — vincular direto
                existing.google_id = google_id
                db.session.commit()
                user = existing

    # 3. Se não achou nenhum, criar nova conta
    if not user:
        # Gerar username a partir do email (parte antes do @)
        base_username = re.sub(r'[^a-z0-9]', '', email.split('@')[0].lower())
        if len(base_username) < 3:
            base_username = base_username + 'user'
        username = base_username
        # Garantir unicidade do username
        counter = 1
        while Creator.query.filter_by(username=username).first():
            username = f"{base_username}{counter}"
            counter += 1

        user = Creator(
            name=name,
            email=email,
            username=username,
            google_id=google_id,
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()

        flash(f'Conta criada com sucesso! Bem-vindo, {user.name}!', 'success')
        _regenerate_session()
        login_user(user)
        return redirect(url_for('dashboard.index'))

    # M8: Se vinculou por email e não era verificado, verificar agora (Google confirmou o email)
    if not user.is_verified:
        user.is_verified = True

    # Login
    user.update_last_login()
    _regenerate_session()
    login_user(user)
    flash(f'Bem-vindo de volta, {user.name}!', 'success')
    return redirect(url_for('dashboard.index'))


@bp.route('/como-funciona')
def wiki():
    """Central de Ajuda / Wiki"""
    return render_template('public/wiki.html')


@bp.route('/em-breve')
def coming_soon():
    """Página Em Construção"""
    return render_template('public/coming_soon.html')


@bp.route('/conta-bloqueada')
@login_required
def blocked_account():
    """Página exibida para contas bloqueadas"""
    return render_template('public/blocked.html')


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('auth.index'))


@bp.route('/sitemap.xml')
def sitemap():
    """Sitemap XML dinâmico — páginas estáticas + criadores + grupos públicos"""
    from app.models import Group
    from sqlalchemy import or_

    base = 'https://televip.app'

    # Páginas estáticas
    static_pages = [
        ('/', 'daily', '1.0'),
        ('/recursos', 'weekly', '0.8'),
        ('/precos', 'weekly', '0.8'),
        ('/como-funciona', 'weekly', '0.7'),
        ('/termos', 'monthly', '0.3'),
        ('/privacidade', 'monthly', '0.3'),
        ('/denuncia', 'monthly', '0.3'),
    ]

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for path, freq, priority in static_pages:
        xml += (
            f'  <url>\n'
            f'    <loc>{base}{path}</loc>\n'
            f'    <changefreq>{freq}</changefreq>\n'
            f'    <priority>{priority}</priority>\n'
            f'  </url>\n'
        )

    # Páginas públicas de criadores ativos
    creators = Creator.query.filter(
        Creator.is_active == True,
        or_(Creator.is_blocked == False, Creator.is_blocked.is_(None)),
        Creator.username.isnot(None)
    ).all()

    for creator in creators:
        xml += (
            f'  <url>\n'
            f'    <loc>{base}/c/{creator.username}</loc>\n'
            f'    <changefreq>weekly</changefreq>\n'
            f'    <priority>0.6</priority>\n'
            f'  </url>\n'
        )

        # Grupos públicos deste criador
        public_groups = Group.query.filter_by(
            creator_id=creator.id, is_public=True, is_active=True
        ).all()

        for group in public_groups:
            if group.invite_slug:
                xml += (
                    f'  <url>\n'
                    f'    <loc>{base}/c/{creator.username}/{group.invite_slug}</loc>\n'
                    f'    <changefreq>weekly</changefreq>\n'
                    f'    <priority>0.5</priority>\n'
                    f'  </url>\n'
                )

    xml += '</urlset>\n'
    return Response(xml, content_type='application/xml')


@bp.route('/robots.txt')
def robots():
    """Robots.txt para motores de busca"""
    txt = "User-agent: *\nAllow: /\n\nSitemap: https://televip.app/sitemap.xml\n"
    return Response(txt, content_type='text/plain')


@bp.route('/recursos')
def recursos():
    """Página de recursos"""
    return render_template('public/recursos.html')


@bp.route('/precos')
def precos():
    """Página de preços"""
    return render_template('public/precos.html')


@bp.route('/termos')
def terms():
    """Termos de Uso"""
    return render_template('public/terms.html')


@bp.route('/privacidade')
def privacy():
    """Política de Privacidade"""
    return render_template('public/privacy.html')


@bp.route('/denuncia', methods=['GET', 'POST'])
@limiter.limit("5 per hour", methods=["POST"])
def report():
    """Canal de denúncia de abuso"""
    if request.method == 'POST':
        report_type = request.form.get('report_type', '').strip()
        target_name = request.form.get('target_name', '').strip()
        description = request.form.get('description', '').strip()
        reporter_email = request.form.get('reporter_email', '').strip() or None

        # Validação
        valid_types = ['conteudo_ilicito', 'fraude', 'abuso', 'outro']
        if not report_type or report_type not in valid_types:
            flash('Selecione um tipo de denúncia válido.', 'error')
        elif not target_name or len(target_name) < 2:
            flash('Informe o nome do grupo ou criador.', 'error')
        elif not description or len(description) < 10:
            flash('A descrição deve ter pelo menos 10 caracteres.', 'error')
        else:
            new_report = Report(
                report_type=report_type,
                target_name=target_name[:200],
                description=description[:2000],
                reporter_email=reporter_email[:200] if reporter_email else None
            )
            db.session.add(new_report)
            db.session.commit()
            logger.info(f"New abuse report submitted: type={report_type}, target={target_name}")
            return render_template('public/report.html', success=True)

    return render_template('public/report.html', success=False)
