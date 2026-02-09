from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db, limiter
from app.models import Creator
from app.utils.email import send_password_reset_email, send_welcome_email
from app.utils.security import generate_reset_token, verify_reset_token, is_safe_url
import re

bp = Blueprint('auth', __name__)

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

        # Validações
        errors = []

        # Validar nome
        if len(name) < 3:
            errors.append('Nome deve ter pelo menos 3 caracteres')

        # Validar email
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            errors.append('Email inválido')
        elif Creator.query.filter_by(email=email).first():
            errors.append('Email já cadastrado!')

        # Validar username
        if not re.match(r'^[a-z0-9]+$', username):
            errors.append('Username deve conter apenas letras minúsculas e números')
        elif len(username) < 3:
            errors.append('Username deve ter pelo menos 3 caracteres')
        elif Creator.query.filter_by(username=username).first():
            errors.append('Username já em uso!')

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
            # Criar novo usuário
            user = Creator(
                name=name,
                email=email,
                username=username
            )
            user.set_password(password)

            db.session.add(user)
            db.session.commit()

            # Enviar email de boas-vindas (opcional)
            try:
                send_welcome_email(user)
            except:
                pass  # Não bloquear registro se email falhar

            login_user(user)
            flash('🎉 Conta criada com sucesso! Bem-vindo ao TeleVIP!', 'success')
            return redirect(url_for('dashboard.index'))

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
            # Gerar token de reset
            token = generate_reset_token(user.id)

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

    # Verificar token
    user_id = verify_reset_token(token)
    if not user_id:
        flash('Link inválido ou expirado. Solicite um novo.', 'error')
        return redirect(url_for('auth.forgot_password'))

    user = Creator.query.get(user_id)
    if not user:
        flash('Usuário não encontrado.', 'error')
        return redirect(url_for('auth.login'))

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

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('auth.index'))
