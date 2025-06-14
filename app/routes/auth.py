from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.models import Creator

bp = Blueprint('auth', __name__)

@bp.route('/')
def index():
    """Página inicial - redireciona para login ou dashboard"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return render_template('public/landing.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = Creator.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard.index'))
        else:
            flash('Email ou senha incorretos', 'error')
    
    return render_template('auth/login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Validações
        if Creator.query.filter_by(email=email).first():
            flash('Email já cadastrado!', 'error')
        elif Creator.query.filter_by(username=username).first():
            flash('Username já em uso!', 'error')
        elif len(password) < 6:
            flash('A senha deve ter pelo menos 6 caracteres!', 'error')
        else:
            # Criar novo usuário
            user = Creator(
                name=name,
                email=email,
                username=username.lower()
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            login_user(user)
            flash('Conta criada com sucesso!', 'success')
            return redirect(url_for('dashboard.index'))
    
    return render_template('auth/register.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('auth.index'))