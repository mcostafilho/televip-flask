from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_user, logout_user, current_user, login_required
from app import db, limiter
from app.models import Creator, Report
from app.utils.email import send_password_reset_email, send_welcome_email, send_confirmation_email
from app.utils.security import generate_reset_token, verify_reset_token, generate_confirmation_token, verify_confirmation_token, is_safe_url
import re
import logging
from datetime import datetime

bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

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
        if user and user.check_password(password):
            if not user.is_verified:
                flash('Confirme seu email antes de fazer login. Verifique sua caixa de entrada.', 'warning')
                return render_template('auth/login.html', unverified_email=email)
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
            errors.append('Email ou username já em uso.')

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
                terms_ip=request.headers.get('X-Forwarded-For', request.remote_addr),
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
        if user:
            # Gerar token de reset (includes password hash prefix for single-use)
            token = generate_reset_token(user.id, password_hash=user.password_hash)

            # Enviar email
            try:
                send_password_reset_email(user, token)
                flash('Email enviado! Verifique sua caixa de entrada.', 'success')
            except Exception as e:
                flash('Erro ao enviar email. Tente novamente mais tarde.', 'error')
                print(f"Erro ao enviar email: {e}")
        else:
            # Por segurança, sempre mostrar mensagem de sucesso
            flash('Se o email estiver cadastrado, você receberá as instruções.', 'info')

        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

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


@bp.route('/conta-bloqueada')
@login_required
def blocked_account():
    """Página exibida para contas bloqueadas"""
    return render_template('public/blocked.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('auth.index'))


@bp.route('/sitemap.xml')
def sitemap():
    """Sitemap XML para motores de busca"""
    urls = [
        'https://televip.app/',
        'https://televip.app/recursos',
        'https://televip.app/precos',
        'https://televip.app/termos',
        'https://televip.app/privacidade',
        'https://televip.app/denuncia',
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in urls:
        xml += f'  <url><loc>{url}</loc></url>\n'
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
