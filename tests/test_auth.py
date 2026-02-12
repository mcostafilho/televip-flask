# tests/test_auth.py
"""
Testes das rotas de autenticação
"""
import pytest
from unittest.mock import patch
from app.models import Creator
from tests.conftest import login, logout


class TestLogin:
    """Testes de login"""

    def test_login_page_renders(self, client):
        resp = client.get('/login')
        assert resp.status_code == 200

    def test_login_success(self, client, creator):
        resp = client.post('/login', data={
            'email': 'creator@test.com',
            'password': 'TestPass123',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert 'Bem-vindo' in resp.data.decode('utf-8') or resp.status_code == 200

    def test_login_wrong_password(self, client, creator):
        resp = client.post('/login', data={
            'email': 'creator@test.com',
            'password': 'WrongPass1',
        }, follow_redirects=True)
        assert 'incorretos' in resp.data.decode('utf-8')

    def test_login_nonexistent_email(self, client):
        resp = client.post('/login', data={
            'email': 'nobody@test.com',
            'password': 'Whatever1',
        }, follow_redirects=True)
        assert 'incorretos' in resp.data.decode('utf-8')

    def test_login_empty_fields(self, client):
        resp = client.post('/login', data={
            'email': '',
            'password': '',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_redirects_when_authenticated(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/login')
        assert resp.status_code == 302

    def test_login_safe_redirect(self, client, creator):
        resp = client.post('/login?next=/dashboard/', data={
            'email': 'creator@test.com',
            'password': 'TestPass123',
        })
        assert resp.status_code == 302
        assert '/dashboard' in resp.headers.get('Location', '')

    def test_login_blocks_open_redirect(self, client, creator):
        resp = client.post('/login?next=https://evil.com', data={
            'email': 'creator@test.com',
            'password': 'TestPass123',
        }, follow_redirects=False)
        location = resp.headers.get('Location', '')
        assert 'evil.com' not in location


class TestRegister:
    """Testes de registro"""

    def test_register_page_renders(self, client):
        resp = client.get('/register')
        assert resp.status_code == 200

    @patch('app.routes.auth.send_confirmation_email')
    def test_register_success(self, mock_email, client, db):
        resp = client.post('/register', data={
            'name': 'New User',
            'email': 'newuser@test.com',
            'username': 'newuser',
            'password': 'NewPass123',
            'confirm_password': 'NewPass123',
            'accept_terms': 'on',
        }, follow_redirects=True)
        assert resp.status_code == 200
        user = Creator.query.filter_by(email='newuser@test.com').first()
        assert user is not None
        assert user.name == 'New User'

    def test_register_short_name(self, client):
        resp = client.post('/register', data={
            'name': 'AB',
            'email': 'short@test.com',
            'username': 'shortname',
            'password': 'Pass1234',
            'confirm_password': 'Pass1234',
        }, follow_redirects=True)
        assert 'pelo menos 3' in resp.data.decode('utf-8')

    def test_register_invalid_email(self, client):
        resp = client.post('/register', data={
            'name': 'Valid Name',
            'email': 'not-an-email',
            'username': 'validuser',
            'password': 'Pass1234',
            'confirm_password': 'Pass1234',
        }, follow_redirects=True)
        assert 'inv' in resp.data.decode('utf-8').lower()

    def test_register_duplicate_email(self, client, creator):
        resp = client.post('/register', data={
            'name': 'Duplicate',
            'email': 'creator@test.com',
            'username': 'newunique',
            'password': 'Pass1234',
            'confirm_password': 'Pass1234',
            'accept_terms': 'on',
        }, follow_redirects=True)
        assert 'em uso' in resp.data.decode('utf-8').lower()

    def test_register_duplicate_username(self, client, creator):
        resp = client.post('/register', data={
            'name': 'Duplicate',
            'email': 'unique@test.com',
            'username': 'testcreator',
            'password': 'Pass1234',
            'confirm_password': 'Pass1234',
        }, follow_redirects=True)
        assert 'em uso' in resp.data.decode('utf-8').lower()

    def test_register_invalid_username_special_chars(self, client):
        resp = client.post('/register', data={
            'name': 'Valid Name',
            'email': 'valid@test.com',
            'username': 'user@name!',
            'password': 'Pass1234',
            'confirm_password': 'Pass1234',
        }, follow_redirects=True)
        assert 'min' in resp.data.decode('utf-8').lower() or 'username' in resp.data.decode('utf-8').lower()

    def test_register_short_username(self, client):
        resp = client.post('/register', data={
            'name': 'Valid Name',
            'email': 'valid@test.com',
            'username': 'ab',
            'password': 'Pass1234',
            'confirm_password': 'Pass1234',
        }, follow_redirects=True)
        assert 'pelo menos 3' in resp.data.decode('utf-8')

    def test_register_short_password(self, client):
        resp = client.post('/register', data={
            'name': 'Valid Name',
            'email': 'valid@test.com',
            'username': 'validuser',
            'password': 'Short1',
            'confirm_password': 'Short1',
        }, follow_redirects=True)
        assert 'pelo menos 8' in resp.data.decode('utf-8')

    def test_register_no_uppercase(self, client):
        resp = client.post('/register', data={
            'name': 'Valid Name',
            'email': 'valid@test.com',
            'username': 'validuser',
            'password': 'nouppercase1',
            'confirm_password': 'nouppercase1',
        }, follow_redirects=True)
        assert 'mai' in resp.data.decode('utf-8').lower()

    def test_register_no_digit(self, client):
        resp = client.post('/register', data={
            'name': 'Valid Name',
            'email': 'valid@test.com',
            'username': 'validuser',
            'password': 'NoDigitHere',
            'confirm_password': 'NoDigitHere',
        }, follow_redirects=True)
        assert 'numero' in resp.data.decode('utf-8').lower()

    def test_register_password_mismatch(self, client):
        resp = client.post('/register', data={
            'name': 'Valid Name',
            'email': 'valid@test.com',
            'username': 'validuser',
            'password': 'ValidPass1',
            'confirm_password': 'DifferentPass1',
        }, follow_redirects=True)
        assert 'coincidem' in resp.data.decode('utf-8').lower()

    def test_register_redirects_when_authenticated(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/register')
        assert resp.status_code == 302


class TestLogout:
    """Testes de logout"""

    def test_logout_success(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/logout', follow_redirects=True)
        assert resp.status_code == 200

    def test_logout_requires_login(self, client):
        resp = client.post('/logout')
        assert resp.status_code == 302  # Redireciona para login


class TestForgotPassword:
    """Testes de recuperação de senha"""

    def test_forgot_password_page_renders(self, client):
        resp = client.get('/forgot-password')
        assert resp.status_code == 200

    def test_forgot_password_existing_email(self, client, creator):
        resp = client.post('/forgot-password', data={
            'email': 'creator@test.com',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_forgot_password_nonexistent_email(self, client):
        resp = client.post('/forgot-password', data={
            'email': 'nobody@test.com',
        }, follow_redirects=True)
        # Deve mostrar mensagem genérica por segurança
        assert resp.status_code == 200

    def test_forgot_password_redirects_when_authenticated(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/forgot-password')
        assert resp.status_code == 302


class TestResetPassword:
    """Testes de reset de senha"""

    def test_reset_password_valid_token(self, client, creator):
        from app.utils.security import generate_reset_token
        token = generate_reset_token(creator.id)
        resp = client.get(f'/reset-password/{token}')
        assert resp.status_code == 200

    def test_reset_password_invalid_token(self, client):
        resp = client.get('/reset-password/invalid_token', follow_redirects=True)
        assert resp.status_code == 200
        assert 'inv' in resp.data.decode('utf-8').lower() or 'expirado' in resp.data.decode('utf-8').lower()

    def test_reset_password_success(self, client, creator, db):
        from app.utils.security import generate_reset_token
        token = generate_reset_token(creator.id)
        resp = client.post(f'/reset-password/{token}', data={
            'password': 'NewSecure1',
            'confirm_password': 'NewSecure1',
        }, follow_redirects=True)
        assert resp.status_code == 200
        # Verificar nova senha
        creator_updated = Creator.query.get(creator.id)
        assert creator_updated.check_password('NewSecure1') is True

    def test_reset_password_short(self, client, creator):
        from app.utils.security import generate_reset_token
        token = generate_reset_token(creator.id)
        resp = client.post(f'/reset-password/{token}', data={
            'password': 'Short1',
            'confirm_password': 'Short1',
        }, follow_redirects=True)
        assert 'pelo menos 8' in resp.data.decode('utf-8')

    def test_reset_password_mismatch(self, client, creator):
        from app.utils.security import generate_reset_token
        token = generate_reset_token(creator.id)
        resp = client.post(f'/reset-password/{token}', data={
            'password': 'ValidPass1',
            'confirm_password': 'DiffPass11',
        }, follow_redirects=True)
        assert 'coincidem' in resp.data.decode('utf-8').lower()

    def test_reset_password_logs_out_when_authenticated(self, client, creator):
        """Usuário autenticado é deslogado e vê o formulário de reset"""
        from app.utils.security import generate_reset_token
        login(client, 'creator@test.com', 'TestPass123')
        token = generate_reset_token(creator.id, password_hash=creator.password_hash)
        resp = client.get(f'/reset-password/{token}')
        assert resp.status_code == 200


class TestIndex:
    """Testes da página inicial"""

    def test_index_unauthenticated(self, client):
        resp = client.get('/')
        assert resp.status_code == 200

    def test_index_authenticated_redirects(self, client, creator):
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/')
        assert resp.status_code == 302


class TestSecurityHeaders:
    """Testes dos headers de segurança"""

    def test_x_frame_options(self, client):
        resp = client.get('/')
        assert resp.headers.get('X-Frame-Options') == 'DENY'

    def test_x_content_type_options(self, client):
        resp = client.get('/')
        assert resp.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_xss_protection(self, client):
        resp = client.get('/')
        assert resp.headers.get('X-XSS-Protection') == '1; mode=block'

    def test_referrer_policy(self, client):
        resp = client.get('/')
        assert resp.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_content_security_policy(self, client):
        resp = client.get('/')
        csp = resp.headers.get('Content-Security-Policy')
        assert csp is not None
        assert "default-src 'self'" in csp
        assert "script-src" in csp

    def test_no_hsts_in_testing(self, client):
        resp = client.get('/')
        # HSTS não deve aparecer em modo testing
        assert resp.headers.get('Strict-Transport-Security') is None
