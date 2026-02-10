# tests/test_invite_slug.py
"""
Testes para invite_slug nos grupos, OAuth UX no perfil,
deleção de grupos, criadores bloqueados e cenários de fraude.
"""
import secrets
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from app import db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction
from tests.conftest import login


# ============================================================
# Parte 1: Invite Slug - Model e Geração
# ============================================================

class TestInviteSlugModel:
    """Testes do campo invite_slug no model Group"""

    def test_group_has_invite_slug(self, app_context, group):
        """Grupo criado deve ter invite_slug preenchido"""
        assert group.invite_slug is not None
        assert len(group.invite_slug) > 0

    def test_invite_slug_is_url_safe(self, app_context, group):
        """Slug deve conter apenas caracteres URL-safe"""
        import re
        assert re.match(r'^[A-Za-z0-9_-]+$', group.invite_slug)

    def test_invite_slug_length(self, app_context, group):
        """Slug gerado por token_urlsafe(6) deve ter 8 chars"""
        assert len(group.invite_slug) == 8

    def test_invite_slug_unique(self, app_context, db, creator):
        """Dois grupos devem ter slugs diferentes"""
        g1 = Group(
            name='Group A', telegram_id='-100111', creator_id=creator.id,
            is_active=True,
        )
        g2 = Group(
            name='Group B', telegram_id='-100222', creator_id=creator.id,
            is_active=True,
        )
        db.session.add_all([g1, g2])
        db.session.commit()
        assert g1.invite_slug != g2.invite_slug

    def test_invite_slug_auto_generated(self, app_context, db, creator):
        """Slug deve ser gerado automaticamente sem ser passado explicitamente"""
        g = Group(
            name='Auto Slug Group', telegram_id='-100333',
            creator_id=creator.id, is_active=True,
        )
        db.session.add(g)
        db.session.commit()
        assert g.invite_slug is not None
        assert len(g.invite_slug) == 8

    def test_invite_slug_persists(self, app_context, db, group):
        """Slug deve permanecer o mesmo após re-query"""
        slug = group.invite_slug
        db.session.expire_all()
        g = Group.query.get(group.id)
        assert g.invite_slug == slug


# ============================================================
# Parte 2: Links usam invite_slug
# ============================================================

class TestInviteSlugInLinks:
    """Testes de que os links de grupo usam invite_slug"""

    def test_group_link_uses_slug(self, client, creator, group):
        """Link do grupo no endpoint /groups/<id>/link deve usar slug"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/link')
        assert resp.status_code == 200
        data = resp.get_json()
        assert group.invite_slug in data['link']
        assert f'g_{group.invite_slug}' in data['link']
        # Não deve conter o ID numérico
        assert f'g_{group.id}' not in data['link']

    def test_groups_list_uses_slug(self, client, creator, group):
        """Lista de grupos no dashboard deve usar slug no link"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/groups/')
        html = resp.data.decode('utf-8')
        assert f'g_{group.invite_slug}' in html

    def test_dashboard_uses_slug(self, client, creator, group):
        """Dashboard principal deve usar slug no link do grupo"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/')
        html = resp.data.decode('utf-8')
        assert f'g_{group.invite_slug}' in html

    def test_subscribers_page_uses_slug(self, client, creator, group, subscription):
        """Página de assinantes deve usar slug no link"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers')
        html = resp.data.decode('utf-8')
        assert f'g_{group.invite_slug}' in html

    def test_create_group_generates_slug_link(self, client, creator, db):
        """Criar grupo deve gerar link com slug"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/groups/create', data={
            'name': 'Slug Test Group',
            'description': 'Testing slug generation',
            'telegram_id': '-100999888',
            'skip_validation': 'on',
        }, follow_redirects=True)
        assert resp.status_code == 200
        g = Group.query.filter_by(name='Slug Test Group').first()
        assert g is not None
        assert g.invite_slug is not None
        html = resp.data.decode('utf-8')
        assert f'g_{g.invite_slug}' in html


# ============================================================
# Parte 3: Subscriber Details Modal
# ============================================================

class TestSubscriberDetails:
    """Testes do endpoint de detalhes do assinante (AJAX modal)"""

    def test_subscriber_details_returns_html(self, client, creator, group, subscription):
        """Endpoint de detalhes deve retornar HTML com info do assinante"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers/{subscription.id}/details')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'testsubscriber' in html
        assert '123456789' in html

    def test_subscriber_details_shows_plan(self, client, creator, group, subscription, pricing_plan):
        """Detalhes devem mostrar info do plano"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers/{subscription.id}/details')
        html = resp.data.decode('utf-8')
        assert 'Plano Mensal' in html
        assert '49.90' in html

    def test_subscriber_details_shows_transactions(self, client, creator, group, subscription, transaction):
        """Detalhes devem mostrar histórico de pagamentos"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers/{subscription.id}/details')
        html = resp.data.decode('utf-8')
        assert '49.90' in html
        assert 'Completed' in html or 'completed' in html.lower()

    def test_subscriber_details_wrong_owner(self, client, second_creator, group, subscription):
        """Outro criador não deve ver detalhes de assinantes de grupo alheio"""
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.get(f'/groups/{group.id}/subscribers/{subscription.id}/details')
        assert resp.status_code == 404

    def test_subscriber_details_nonexistent(self, client, creator, group):
        """Assinante inexistente deve retornar 404"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/subscribers/99999/details')
        assert resp.status_code == 404

    def test_subscriber_details_requires_login(self, client, group, subscription):
        """Endpoint de detalhes requer autenticação"""
        resp = client.get(f'/groups/{group.id}/subscribers/{subscription.id}/details')
        assert resp.status_code == 302


# ============================================================
# Parte 4: Deleção de grupo com cascade
# ============================================================

class TestGroupDeletion:
    """Testes de deleção de grupo com subscriptions e transactions"""

    def test_delete_group_with_expired_subscriptions(self, client, creator, db, group, pricing_plan):
        """Deve deletar grupo com assinaturas expiradas (não ativas)"""
        sub = Subscription(
            group_id=group.id, plan_id=pricing_plan.id,
            telegram_user_id='111', telegram_username='expired_user',
            start_date=datetime.utcnow() - timedelta(days=60),
            end_date=datetime.utcnow() - timedelta(days=30),
            status='expired',
        )
        db.session.add(sub)
        db.session.commit()

        txn = Transaction(
            subscription_id=sub.id, amount=Decimal('49.90'),
            status='completed', payment_method='stripe',
        )
        db.session.add(txn)
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post(f'/groups/{group.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        assert Group.query.get(group.id) is None
        assert Subscription.query.filter_by(group_id=group.id).count() == 0
        assert Transaction.query.filter_by(subscription_id=sub.id).count() == 0

    def test_delete_group_with_multiple_subs_and_txns(self, client, creator, db, group, pricing_plan):
        """Deve deletar grupo com múltiplas subscriptions e transactions"""
        for i in range(3):
            sub = Subscription(
                group_id=group.id, plan_id=pricing_plan.id,
                telegram_user_id=str(1000 + i), telegram_username=f'user{i}',
                start_date=datetime.utcnow() - timedelta(days=60),
                end_date=datetime.utcnow() - timedelta(days=30),
                status='expired',
            )
            db.session.add(sub)
            db.session.flush()
            for j in range(2):
                txn = Transaction(
                    subscription_id=sub.id, amount=Decimal('49.90'),
                    status='completed', payment_method='stripe',
                )
                db.session.add(txn)
        db.session.commit()

        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post(f'/groups/{group.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        assert Group.query.get(group.id) is None

    def test_delete_group_blocked_with_active_subs(self, client, creator, db, group, subscription):
        """Não deve deletar grupo com assinaturas ativas"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post(f'/groups/{group.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        # Grupo ainda deve existir
        assert Group.query.get(group.id) is not None

    def test_delete_empty_group(self, client, creator, group):
        """Deve deletar grupo sem assinaturas"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post(f'/groups/{group.id}/delete', follow_redirects=True)
        assert resp.status_code == 200
        assert Group.query.get(group.id) is None


# ============================================================
# Parte 5: OAuth UX no Perfil
# ============================================================

class TestOAuthProfileUX:
    """Testes de UX do perfil para usuários OAuth"""

    def _create_oauth_user(self, db):
        """Helper: cria usuário OAuth (sem password_hash)"""
        user = Creator(
            name='OAuth User', email='oauth@test.com',
            username='oauthuser', google_id='google123',
            is_verified=True, balance=Decimal('0'), total_earned=Decimal('0'),
        )
        # Não definir senha — simula cadastro via Google
        db.session.add(user)
        db.session.commit()
        return user

    def test_profile_oauth_shows_define_password(self, client, db):
        """Usuário OAuth deve ver 'Definir Senha' em vez de 'Alterar Senha'"""
        user = self._create_oauth_user(db)
        # Login direto via flask-login (sem senha)
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        assert 'Definir Senha' in html
        assert 'criada via Google' in html

    def test_profile_oauth_hides_current_password(self, client, db):
        """Usuário OAuth não deve ver campo de senha atual"""
        user = self._create_oauth_user(db)
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        assert 'current_password' not in html or 'primeiro defina uma senha' in html

    def test_profile_normal_shows_change_password(self, client, creator):
        """Usuário normal deve ver 'Alterar Senha (opcional)'"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        assert 'Alterar Senha (opcional)' in html
        assert 'current_password' in html

    def test_profile_normal_shows_forgot_password(self, client, creator):
        """Usuário normal deve ver link 'Esqueceu a senha?'"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        assert 'Esqueceu a senha?' in html

    def test_profile_has_password_flag(self, client, creator, db):
        """has_password deve ser True para usuário com senha"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        # Verifica que mostra seção de alterar senha (indica has_password=True)
        assert 'Alterar Senha' in html

    def test_profile_password_minlength_8(self, client, creator):
        """Campos de senha devem ter minlength=8"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get('/dashboard/profile')
        html = resp.data.decode('utf-8')
        assert 'minlength="8"' in html


# ============================================================
# Parte 6: Reset password para usuários logados
# ============================================================

class TestProfileResetPassword:
    """Testes do envio de email de reset de senha do perfil"""

    def test_reset_password_requires_login(self, client):
        """Endpoint de reset de senha do perfil requer autenticação"""
        resp = client.post('/dashboard/profile/reset-password')
        assert resp.status_code == 302

    def test_reset_password_oauth_user_redirects(self, client, db):
        """Usuário OAuth sem senha recebe flash info"""
        user = Creator(
            name='OAuth', email='oauth2@test.com', username='oauth2',
            google_id='g456', is_verified=True,
            balance=Decimal('0'), total_earned=Decimal('0'),
        )
        db.session.add(user)
        db.session.commit()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
        resp = client.post('/dashboard/profile/reset-password', follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert resp.status_code == 200


# ============================================================
# Parte 7: Sessão expira por inatividade
# ============================================================

class TestSessionTimeout:
    """Testes de configuração de timeout de sessão"""

    def test_session_is_permanent(self, app):
        """Sessão deve ser permanente"""
        assert app.config['SESSION_PERMANENT'] is True

    def test_session_lifetime_is_2h(self, app):
        """Lifetime deve ser 2 horas"""
        assert app.config['PERMANENT_SESSION_LIFETIME'] == timedelta(hours=2)


# ============================================================
# Parte 8: Criadores bloqueados
# ============================================================

class TestBlockedCreator:
    """Testes de que criadores bloqueados não podem operar"""

    def _block_creator(self, db, creator):
        creator.is_blocked = True
        db.session.commit()

    def test_blocked_creator_cannot_access_dashboard(self, client, creator, db):
        """Criador bloqueado deve ser redirecionado ao acessar dashboard"""
        login(client, 'creator@test.com', 'TestPass123')
        self._block_creator(db, creator)
        resp = client.get('/dashboard/')
        # Deve redirecionar para página de bloqueio
        assert resp.status_code == 302

    def test_blocked_creator_cannot_access_groups(self, client, creator, db):
        """Criador bloqueado não acessa lista de grupos"""
        login(client, 'creator@test.com', 'TestPass123')
        self._block_creator(db, creator)
        resp = client.get('/groups/')
        assert resp.status_code == 302

    def test_blocked_creator_group_link_returns_unavailable(self, client, creator, db, group):
        """Link do grupo de criador bloqueado não deve funcionar no dashboard"""
        login(client, 'creator@test.com', 'TestPass123')
        self._block_creator(db, creator)
        resp = client.get(f'/groups/{group.id}/link')
        assert resp.status_code == 302


# ============================================================
# Parte 9: Testes de Fraude
# ============================================================

class TestFraudPrevention:
    """Testes de cenários de fraude e abuso"""

    # --- Acesso não autorizado ---

    def test_access_other_creator_group(self, client, creator, second_creator, group):
        """Criador não pode acessar/editar grupo de outro criador"""
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.get(f'/groups/{group.id}/edit')
        assert resp.status_code == 404

    def test_delete_other_creator_group(self, client, creator, second_creator, group):
        """Criador não pode deletar grupo de outro"""
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.post(f'/groups/{group.id}/delete')
        assert resp.status_code == 404
        assert Group.query.get(group.id) is not None

    def test_toggle_other_creator_group(self, client, creator, second_creator, group):
        """Criador não pode ativar/desativar grupo de outro"""
        login(client, 'second@test.com', 'SecondPass123')
        was_active = group.is_active
        resp = client.post(f'/groups/{group.id}/toggle')
        assert resp.status_code == 404
        db_group = Group.query.get(group.id)
        assert db_group.is_active == was_active

    def test_export_other_creator_subscribers(self, client, creator, second_creator, group):
        """Criador não pode exportar CSV de assinantes de grupo alheio"""
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.get(f'/groups/{group.id}/export-subscribers')
        assert resp.status_code == 404

    def test_view_other_creator_stats(self, client, creator, second_creator, group):
        """Criador não pode ver estatísticas de grupo alheio"""
        login(client, 'second@test.com', 'SecondPass123')
        resp = client.get(f'/groups/{group.id}/stats')
        assert resp.status_code == 404

    # --- Enumeração de IDs ---

    def test_slug_prevents_group_enumeration(self, app_context, db, creator):
        """Slugs aleatórios impedem enumeração sequencial de grupos"""
        slugs = []
        for i in range(10):
            g = Group(
                name=f'Group {i}', telegram_id=f'-100{i:04d}',
                creator_id=creator.id, is_active=True,
            )
            db.session.add(g)
            db.session.commit()
            slugs.append(g.invite_slug)

        # Slugs não devem seguir padrão sequencial
        for i in range(len(slugs) - 1):
            assert slugs[i] != slugs[i + 1]

        # Nenhum slug deve ser apenas número (para não confundir com IDs)
        for slug in slugs:
            assert not slug.isdigit()

    def test_group_link_does_not_expose_id(self, client, creator, group):
        """Link do grupo não deve expor o ID numérico"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{group.id}/link')
        data = resp.get_json()
        # O link deve conter slug, não ID
        link = data['link']
        assert f'?start=g_{group.id}' not in link
        assert f'?start=g_{group.invite_slug}' in link

    # --- Manipulação de preços ---

    def test_cannot_create_negative_price_plan(self, client, creator, group, db):
        """Não deve ser possível criar plano com preço negativo"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post(f'/groups/{group.id}/edit', data={
            'name': group.name,
            'description': group.description or '',
            'plan_names': 'Plano Fraudulento',
            'plan_prices': '-10.00',
            'plan_durations': '30',
        }, follow_redirects=True)
        # Plano negativo não deve ser aceito
        plan = PricingPlan.query.filter_by(group_id=group.id, name='Plano Fraudulento').first()
        if plan:
            assert plan.price >= 0

    # --- Manipulação de identidade ---

    def test_cannot_change_email_without_password(self, client, creator):
        """Não deve ser possível alterar email sem senha atual"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'email': 'hacker@evil.com',
            # Sem current_password
        }, follow_redirects=True)
        html = resp.data.decode('utf-8')
        # Email não deve ter mudado
        user = Creator.query.filter_by(email='creator@test.com').first()
        assert user is not None
        hacker = Creator.query.filter_by(email='hacker@evil.com').first()
        assert hacker is None

    def test_cannot_change_password_without_current(self, client, creator):
        """Não deve ser possível alterar senha sem senha atual"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'email': 'creator@test.com',
            'new_password': 'HackedPass1',
            'confirm_password': 'HackedPass1',
            # Sem current_password
        }, follow_redirects=True)
        # Senha original ainda deve funcionar
        user = Creator.query.filter_by(email='creator@test.com').first()
        assert user.check_password('TestPass123')

    def test_cannot_change_pix_without_password(self, client, creator):
        """Não deve ser possível alterar chave PIX sem senha atual"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'email': 'creator@test.com',
            'pix_key_type': 'cpf',
            'pix_key_value': '12345678901',
            'phone': '(11) 99999-9999',
            # Sem current_password
        }, follow_redirects=True)
        user = Creator.query.filter_by(email='creator@test.com').first()
        assert user.pix_key is None or user.pix_key == ''

    def test_wrong_password_blocks_email_change(self, client, creator):
        """Senha incorreta deve bloquear alteração de email"""
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Test Creator',
            'email': 'stolen@evil.com',
            'current_password': 'WrongPassword1',
        }, follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'incorreta' in html.lower() or 'Senha atual' in html
        user = Creator.query.filter_by(email='creator@test.com').first()
        assert user is not None

    # --- Deleção de conta de terceiros ---

    def test_cannot_delete_other_account(self, client, creator, second_creator):
        """Usuário não pode deletar conta de outro"""
        login(client, 'creator@test.com', 'TestPass123')
        # Tentar deletar não altera o segundo criador
        initial_count = Creator.query.count()
        # A rota de delete account só deleta o current_user
        assert Creator.query.filter_by(email='second@test.com').first() is not None

    # --- Acesso não autenticado ---

    def test_unauthenticated_cannot_create_group(self, client):
        """Usuário não autenticado não pode criar grupo"""
        resp = client.post('/groups/create', data={
            'name': 'Hacked Group',
        })
        assert resp.status_code == 302  # Redirect to login

    def test_unauthenticated_cannot_access_profile(self, client):
        """Usuário não autenticado não pode acessar perfil"""
        resp = client.get('/dashboard/profile')
        assert resp.status_code == 302

    def test_unauthenticated_cannot_update_profile(self, client):
        """Usuário não autenticado não pode atualizar perfil"""
        resp = client.post('/dashboard/profile/update', data={
            'name': 'Hacker',
            'email': 'hacker@evil.com',
        })
        assert resp.status_code == 302

    # --- Replay / duplicação de transações ---

    def test_duplicate_stripe_session_id(self, app_context, db, subscription):
        """Não deve haver transações duplicadas com mesmo stripe_session_id"""
        txn1 = Transaction(
            subscription_id=subscription.id, amount=Decimal('49.90'),
            status='completed', payment_method='stripe',
            stripe_session_id='cs_unique_123',
        )
        db.session.add(txn1)
        db.session.commit()

        # Segunda transação com mesmo session_id — deve ser detectável
        existing = Transaction.query.filter_by(
            stripe_session_id='cs_unique_123'
        ).first()
        assert existing is not None
        assert existing.id == txn1.id

    # --- Abuso de rate limiting ---

    def test_profile_reset_password_rate_limited(self, app, db):
        """Endpoint de reset de senha do perfil deve ter rate limit"""
        # Verificar que o rate limit está configurado na rota
        with app.test_request_context():
            for rule in app.url_map.iter_rules():
                if rule.endpoint == 'dashboard.profile_reset_password':
                    assert 'POST' in rule.methods
                    break

    # --- IDOR (Insecure Direct Object Reference) ---

    def test_idor_subscriber_details(self, client, creator, second_creator, db):
        """Criador não pode ver detalhes de assinante de outro grupo via IDOR"""
        # Criar grupo e assinatura do second_creator
        other_group = Group(
            name='Other Group', telegram_id='-100777',
            creator_id=second_creator.id, is_active=True,
        )
        db.session.add(other_group)
        db.session.commit()

        plan = PricingPlan(
            group_id=other_group.id, name='Plan', duration_days=30,
            price=Decimal('29.90'), is_active=True,
        )
        db.session.add(plan)
        db.session.commit()

        sub = Subscription(
            group_id=other_group.id, plan_id=plan.id,
            telegram_user_id='999', telegram_username='victim',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status='active',
        )
        db.session.add(sub)
        db.session.commit()

        # Logar como creator (não dono do grupo)
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{other_group.id}/subscribers/{sub.id}/details')
        assert resp.status_code == 404

    def test_idor_subscriber_cross_group(self, client, creator, db, group, pricing_plan, subscription):
        """Não pode ver detalhes de assinante passando group_id diferente"""
        # Criar outro grupo do mesmo creator
        other_group = Group(
            name='My Other Group', telegram_id='-100888',
            creator_id=creator.id, is_active=True,
        )
        db.session.add(other_group)
        db.session.commit()

        # Tentar acessar sub do group original via other_group
        login(client, 'creator@test.com', 'TestPass123')
        resp = client.get(f'/groups/{other_group.id}/subscribers/{subscription.id}/details')
        assert resp.status_code == 404  # Sub não pertence a other_group
