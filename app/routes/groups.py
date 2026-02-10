# app/routes/groups.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response, session, current_app
from flask_login import login_required, current_user
from app import db, limiter
from app.models import Group, PricingPlan, Subscription, Transaction
from datetime import datetime, timedelta
from sqlalchemy import func
import requests
import os
import re
import csv
import logging
from io import StringIO

bp = Blueprint('groups', __name__, url_prefix='/groups')
logger = logging.getLogger(__name__)


def _validate_plan_input(name, price_str, duration_str, description=None, is_lifetime=False):
    """Validate plan input fields. Returns (errors list, price float, duration int)."""
    errors = []
    price = None
    duration = None

    if not name or len(name.strip()) == 0:
        errors.append('Nome do plano é obrigatório')
    elif len(name) > 100:
        errors.append('Nome do plano deve ter no máximo 100 caracteres')

    try:
        price = float(price_str)
        if price <= 0 or price > 10000:
            errors.append('Preço deve ser entre R$ 0,01 e R$ 10.000,00')
    except (ValueError, TypeError):
        errors.append('Preço inválido')

    if is_lifetime:
        duration = 0
    else:
        try:
            duration = int(duration_str)
            if duration <= 0 or duration > 365:
                errors.append('Duração deve ser entre 1 e 365 dias')
        except (ValueError, TypeError):
            errors.append('Duração inválida')

    if description and len(description) > 500:
        errors.append('Descrição do plano deve ter no máximo 500 caracteres')

    return errors, price, duration


def _escape_ilike(search_term):
    """Escape SQL ILIKE wildcard characters in user input."""
    return search_term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

@bp.route('/')
@login_required
def list():
    """Lista todos os grupos do criador"""
    groups = current_user.groups.all()
    
    # Atualizar contador de assinantes para cada grupo
    for group in groups:
        group.total_subscribers = Subscription.query.filter_by(
            group_id=group.id,
            status='active'
        ).count()
        
        # Calcular receita total do grupo
        group.total_revenue = db.session.query(func.sum(Transaction.amount)).join(
            Subscription
        ).filter(
            Subscription.group_id == group.id,
            Transaction.status == 'completed'
        ).scalar() or 0
    
    return render_template('dashboard/groups.html', groups=groups)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
@limiter.limit("20 per hour", methods=["POST"])
def create():
    """Criar novo grupo"""
    if request.method == 'POST':
        # Dados básicos do grupo
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        telegram_id = request.form.get('telegram_id', '').replace(' ', '').replace('\t', '').strip()
        invite_link = request.form.get('invite_link', '').strip()
        
        # Verificar se deve validar no Telegram
        skip_validation = request.form.get('skip_validation') == 'on'
        
        # Se marcar para pular validação, criar direto
        if skip_validation:
            pass
        else:
            # Tentar validar
            bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
            
            if bot_token and telegram_id:
                try:
                    # URL da API
                    url = f"https://api.telegram.org/bot{bot_token}/getChat"
                    
                    # Fazer requisição
                    response = requests.get(
                        url,
                        params={"chat_id": telegram_id},
                        timeout=10
                    )
                    
                    if response.status_code != 200:
                        flash('❌ Erro ao conectar com o Telegram. Use "Pular validação" para continuar.', 'error')
                        return render_template('dashboard/group_form.html', 
                                             group=None,
                                             show_success_modal=False)
                    
                    # Processar resposta
                    try:
                        data = response.json()
                    except Exception as json_error:
                        flash('❌ Resposta inválida do Telegram. Use "Pular validação".', 'error')
                        return render_template('dashboard/group_form.html', 
                                             group=None,
                                             show_success_modal=False)
                    
                    if not data.get('ok'):
                        error_msg = data.get('description', 'Erro desconhecido')
                        flash(f'❌ Telegram: {error_msg}', 'error')
                        return render_template('dashboard/group_form.html', 
                                             group=None,
                                             show_success_modal=False)
                    
                    # Grupo encontrado!
                    chat = data.get('result', {})
                    
                    # Verificar se o bot é admin
                    bot_id = bot_token.split(':')[0]
                    bot_member = requests.get(
                        f"https://api.telegram.org/bot{bot_token}/getChatMember",
                        params={
                            "chat_id": telegram_id,
                            "user_id": bot_id
                        },
                        timeout=10
                    )
                    
                    if bot_member.status_code == 200:
                        member_data = bot_member.json()
                        if member_data.get('ok'):
                            status = member_data.get('result', {}).get('status')
                            if status not in ['administrator', 'creator']:
                                flash('⚠️ O bot precisa ser administrador do grupo!', 'warning')
                                return render_template('dashboard/group_form.html', 
                                                     group=None,
                                                     show_success_modal=False)
                    
                except requests.exceptions.RequestException as req_error:
                    logger.error(f"Telegram connection error: {req_error}")
                    flash('Erro de conexão com o Telegram. Use "Pular validação".', 'error')
                    return render_template('dashboard/group_form.html', 
                                         group=None,
                                         show_success_modal=False)
                except Exception as e:
                    logger.error(f"Erro na validação do grupo Telegram: {e}")
                    flash('Erro ao validar grupo. Use "Pular validação".', 'error')
                    return render_template('dashboard/group_form.html',
                                         group=None,
                                         show_success_modal=False)
            else:
                if not bot_token:
                    flash('Bot nao configurado. Use "Pular validacao".', 'warning')
                else:
                    flash('⚠️ ID do Telegram não fornecido.', 'warning')
        
        # Criar grupo + planos de forma atômica
        try:
            group = Group(
                name=name,
                description=description,
                telegram_id=telegram_id or None,
                invite_link=invite_link or None,
                creator_id=current_user.id,
                is_active=True
            )
            db.session.add(group)
            db.session.flush()  # gera group.id sem commitar

            # Adicionar planos
            plan_names = request.form.getlist('plan_name[]')
            plan_durations = request.form.getlist('plan_duration[]')
            plan_prices = request.form.getlist('plan_price[]')
            plan_lifetimes = request.form.getlist('plan_lifetime[]')

            has_valid_plan = False
            for i in range(len(plan_names)):
                if plan_names[i]:
                    lifetime = (plan_lifetimes[i] == '1') if i < len(plan_lifetimes) else False
                    errs, price, duration = _validate_plan_input(
                        plan_names[i],
                        plan_prices[i] if i < len(plan_prices) else '0',
                        plan_durations[i] if i < len(plan_durations) else '0',
                        is_lifetime=lifetime
                    )
                    if errs:
                        for e in errs:
                            flash(e, 'error')
                        continue
                    plan = PricingPlan(
                        group_id=group.id,
                        name=plan_names[i][:100],
                        duration_days=duration,
                        price=price,
                        is_lifetime=lifetime,
                        is_active=True
                    )
                    db.session.add(plan)
                    has_valid_plan = True

            if not has_valid_plan:
                db.session.rollback()
                flash('Adicione pelo menos um plano válido.', 'error')
                return render_template('dashboard/group_form.html',
                                     group=None,
                                     show_success_modal=False)

            db.session.commit()

        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar grupo: {e}")
            if 'UNIQUE' in str(e).upper() or 'unique' in str(e).lower():
                flash('Já existe um grupo com esse ID do Telegram.', 'error')
            else:
                flash('Erro ao criar grupo. Tente novamente.', 'error')
            return render_template('dashboard/group_form.html',
                                 group=None,
                                 show_success_modal=False)

        # Gerar link do bot
        bot_username = os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME', 'televipbra_bot')
        bot_link = f"https://t.me/{bot_username}?start=g_{group.invite_slug}"

        flash(f'Grupo "{group.name}" criado com sucesso! Link: {bot_link}', 'success')

        return render_template('dashboard/group_form.html',
                             group=None,
                             show_success_modal=True,
                             new_group_name=group.name,
                             new_group_id=group.id,
                             new_group_telegram_id=group.telegram_id,
                             bot_link=bot_link)
    
    return render_template('dashboard/group_form.html', 
                         group=None,
                         show_success_modal=False)

@bp.route('/clear-success-modal', methods=['POST'])
@login_required
def clear_success_modal():
    """Limpar flags do modal de sucesso da sessão"""
    session.pop('show_success_modal', None)
    session.pop('new_group_name', None)
    session.pop('new_group_id', None)
    session.pop('new_group_telegram_id', None)
    session.pop('bot_link', None)
    return '', 204

@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Editar grupo existente"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        # Atualizar dados básicos
        group.name = request.form.get('name')
        group.description = request.form.get('description')
        group.invite_link = request.form.get('invite_link')
        group.is_active = 'is_active' in request.form
        
        # Safe plan editing: deactivate plans that have ANY subscriptions referencing them
        existing_plans = PricingPlan.query.filter_by(group_id=group.id).all()
        for plan in existing_plans:
            sub_count = Subscription.query.filter(
                Subscription.plan_id == plan.id
            ).count()
            if sub_count > 0:
                # Deactivate instead of delete — subscriptions reference this plan
                plan.is_active = False
            else:
                db.session.delete(plan)

        # Add new plans from form with validation
        plan_names = request.form.getlist('plan_name[]')
        plan_durations = request.form.getlist('plan_duration[]')
        plan_prices = request.form.getlist('plan_price[]')
        plan_lifetimes = request.form.getlist('plan_lifetime[]')

        for i in range(len(plan_names)):
            if plan_names[i]:
                lifetime = (plan_lifetimes[i] == '1') if i < len(plan_lifetimes) else False
                errs, price, duration = _validate_plan_input(
                    plan_names[i],
                    plan_prices[i] if i < len(plan_prices) else '0',
                    plan_durations[i] if i < len(plan_durations) else '0',
                    is_lifetime=lifetime
                )
                if errs:
                    for e in errs:
                        flash(e, 'error')
                    continue
                plan = PricingPlan(
                    group_id=group.id,
                    name=plan_names[i][:100],
                    duration_days=duration,
                    price=price,
                    is_lifetime=lifetime,
                    is_active=True
                )
                db.session.add(plan)
        
        db.session.commit()
        flash('Grupo atualizado com sucesso!', 'success')
        return redirect(url_for('groups.list'))
    
    return render_template('dashboard/group_form.html', group=group)

@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Deletar grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # Verificar se há assinaturas ativas
    active_subs = Subscription.query.filter_by(
        group_id=id,
        status='active'
    ).count()
    
    if active_subs > 0:
        flash(f'Não é possível deletar o grupo. Existem {active_subs} assinaturas ativas.', 'error')
        return redirect(url_for('groups.list'))

    # Deletar na ordem correta: transactions -> subscriptions -> plans -> grupo
    subs = Subscription.query.filter_by(group_id=id).all()
    for sub in subs:
        Transaction.query.filter_by(subscription_id=sub.id).delete()
    Subscription.query.filter_by(group_id=id).delete()
    PricingPlan.query.filter_by(group_id=id).delete()
    db.session.delete(group)
    db.session.commit()
    
    flash('Grupo deletado com sucesso!', 'success')
    return redirect(url_for('groups.list'))

@bp.route('/<int:id>/toggle', methods=['POST'])
@login_required
def toggle(id):
    """Ativar/Desativar grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    group.is_active = not group.is_active
    db.session.commit()
    
    status = 'ativado' if group.is_active else 'desativado'
    flash(f'Grupo {status} com sucesso!', 'success')
    
    return redirect(url_for('groups.list'))

# Adicione esta função no arquivo app/routes/groups.py

@bp.route('/<int:group_id>/broadcast', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per hour")
def broadcast(group_id):
    """Enviar mensagem para todos os assinantes do grupo"""
    group = Group.query.filter_by(id=group_id, creator_id=current_user.id).first_or_404()

    if request.method == 'POST':
        message = request.form.get('message', '').strip()

        if not message:
            flash('Por favor, digite uma mensagem.', 'error')
            return redirect(url_for('groups.broadcast', group_id=group_id))

        # Fix #17: Message length cap (Telegram limit)
        if len(message) > 4000:
            flash('Mensagem muito longa. Máximo de 4000 caracteres.', 'error')
            return redirect(url_for('groups.broadcast', group_id=group_id))

        # Fix #17: Broadcast cooldown — 5 minutes between broadcasts
        if group.last_broadcast_at:
            cooldown_remaining = (group.last_broadcast_at + timedelta(minutes=5)) - datetime.utcnow()
            if cooldown_remaining.total_seconds() > 0:
                minutes_left = int(cooldown_remaining.total_seconds() // 60) + 1
                flash(f'Aguarde {minutes_left} minuto(s) entre broadcasts.', 'warning')
                return redirect(url_for('groups.broadcast', group_id=group_id))

        # Buscar assinantes ativos
        active_subs = Subscription.query.filter_by(
            group_id=group_id,
            status='active'
        ).all()

        if not active_subs:
            flash('Nenhum assinante ativo para enviar mensagem.', 'warning')
            return redirect(url_for('groups.subscribers', id=group_id))

        sent_count = 0
        failed_count = 0

        bot_token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN')

        if bot_token:
            for sub in active_subs:
                try:
                    response = requests.post(
                        f'https://api.telegram.org/bot{bot_token}/sendMessage',
                        json={
                            'chat_id': sub.telegram_user_id,
                            'text': f"📢 **Mensagem de {group.name}**\n\n{message}",
                            'parse_mode': 'Markdown'
                        }
                    )
                    if response.status_code == 200:
                        sent_count += 1
                    else:
                        failed_count += 1
                except Exception:
                    failed_count += 1
        else:
            flash('Bot do Telegram não configurado.', 'error')
            return redirect(url_for('groups.subscribers', id=group_id))

        # Update broadcast cooldown timestamp
        group.last_broadcast_at = datetime.utcnow()
        db.session.commit()

        flash(f'Mensagem enviada para {sent_count} assinantes. {failed_count} falharam.', 'success')
        return redirect(url_for('groups.subscribers', id=group_id))

    # GET - mostrar formulário
    active_count = Subscription.query.filter_by(
        group_id=group_id,
        status='active'
    ).count()

    return render_template('dashboard/broadcast.html',
                         group=group,
                         active_count=active_count)

@bp.route('/<int:id>/subscribers')
@login_required
def subscribers(id):
    """Listar assinantes do grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()

    now = datetime.utcnow()

    # Query base com filtros opcionais
    query = Subscription.query.filter_by(group_id=id)

    status_filter = request.args.get('status')
    if status_filter:
        query = query.filter_by(status=status_filter)

    plan_filter = request.args.get('plan_id')
    if plan_filter:
        query = query.filter_by(plan_id=int(plan_filter))

    search = request.args.get('search', '').strip()
    if search:
        escaped = _escape_ilike(search)
        query = query.filter(
            (Subscription.telegram_username.ilike(f'%{escaped}%', escape='\\')) |
            (Subscription.telegram_user_id.ilike(f'%{escaped}%', escape='\\'))
        )

    # Paginacao
    page = request.args.get('page', 1, type=int)
    per_page = 20
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)

    all_subs = query.order_by(Subscription.end_date.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    # Estatisticas
    active_count = Subscription.query.filter_by(group_id=id, status='active').count()
    expired_count = Subscription.query.filter_by(group_id=id, status='expired').count()
    expiring_soon = Subscription.query.filter(
        Subscription.group_id == id,
        Subscription.status == 'active',
        Subscription.end_date <= now + timedelta(days=7),
        Subscription.end_date > now
    ).count()

    stats = {
        'total': active_count + expired_count,
        'active': active_count,
        'expired': expired_count,
        'expiring_soon': expiring_soon,
        'revenue': db.session.query(func.sum(Transaction.amount)).join(
            Subscription
        ).filter(
            Subscription.group_id == id,
            Transaction.status == 'completed'
        ).scalar() or 0
    }

    return render_template('dashboard/subscribers.html',
                         group=group,
                         subscribers=all_subs,
                         stats=stats,
                         now=now,
                         page=page,
                         total_pages=total_pages)

@bp.route('/<int:id>/subscribers/<int:sub_id>/details')
@login_required
def subscriber_details(id, sub_id):
    """Retornar HTML parcial com detalhes de um assinante (para modal AJAX)"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    sub = Subscription.query.filter_by(id=sub_id, group_id=group.id).first_or_404()

    now = datetime.utcnow()
    days_left = (sub.end_date - now).days if sub.end_date > now else 0

    transactions = sub.transactions.order_by(Transaction.created_at.desc()).limit(10).all()

    html = f'''
    <div class="row">
        <div class="col-md-6">
            <h6 class="text-muted mb-3">Informações do Assinante</h6>
            <p><strong>Username:</strong> @{sub.telegram_username or "Sem username"}</p>
            <p><strong>Telegram ID:</strong> {sub.telegram_user_id}</p>
            <p><strong>Status:</strong>
                <span class="badge bg-{"success" if sub.status == "active" and sub.end_date > now else "danger"}">
                    {sub.status.capitalize()}
                </span>
            </p>
        </div>
        <div class="col-md-6">
            <h6 class="text-muted mb-3">Assinatura</h6>
            <p><strong>Plano:</strong> {sub.plan.name} - R$ {sub.plan.price:.2f}</p>
            <p><strong>Início:</strong> {sub.start_date.strftime("%d/%m/%Y")}</p>
            <p><strong>Expira:</strong> {sub.end_date.strftime("%d/%m/%Y")}
                {f" ({days_left} dias)" if sub.status == "active" and days_left > 0 else ""}
            </p>
            <p><strong>Renovação auto:</strong> {"Sim" if sub.auto_renew else "Não"}</p>
        </div>
    </div>
    '''

    if transactions:
        html += '''
        <hr>
        <h6 class="text-muted mb-3">Histórico de Pagamentos</h6>
        <table class="table table-sm">
            <thead><tr><th>Data</th><th>Valor</th><th>Status</th></tr></thead>
            <tbody>
        '''
        for t in transactions:
            status_class = "success" if t.status == "completed" else "warning" if t.status == "pending" else "danger"
            html += f'''
            <tr>
                <td>{t.created_at.strftime("%d/%m/%Y %H:%M")}</td>
                <td>R$ {t.amount:.2f}</td>
                <td><span class="badge bg-{status_class}">{t.status.capitalize()}</span></td>
            </tr>
            '''
        html += '</tbody></table>'

    return html


@bp.route('/<int:id>/export-subscribers')
@login_required
@limiter.limit("30 per hour")
def export_subscribers(id):
    """Exportar lista de assinantes em CSV"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()

    # Buscar todos os assinantes
    subscribers = Subscription.query.filter_by(group_id=id).all()

    # Criar CSV
    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'Username',
        'Plano',
        'Status',
        'Data Início',
        'Data Fim',
        'Valor Pago'
    ])

    # Dados
    for sub in subscribers:
        # Calcular valor total pago
        total_paid = db.session.query(func.sum(Transaction.amount)).filter_by(
            subscription_id=sub.id,
            status='completed'
        ).scalar() or 0

        writer.writerow([
            sub.telegram_username or 'N/A',
            sub.plan.name if sub.plan else 'N/A',
            sub.status,
            sub.start_date.strftime('%d/%m/%Y') if sub.start_date else '',
            sub.end_date.strftime('%d/%m/%Y') if sub.end_date else '',
            f'R$ {total_paid:.2f}'
        ])

    # Sanitize filename: remove special chars, limit length
    safe_name = re.sub(r'[^\w\s-]', '', group.name)[:50].strip() or 'grupo'

    # Preparar resposta
    output.seek(0)
    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="assinantes_{safe_name}_{datetime.now().strftime("%Y%m%d")}.csv"'
        }
    )

    return response

@bp.route('/<int:id>/stats')
@login_required
def stats(id):
    """Estatísticas detalhadas do grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # Estatísticas gerais
    stats = {
        'total_subscribers': Subscription.query.filter_by(group_id=id).count(),
        'active_subscribers': Subscription.query.filter_by(group_id=id, status='active').count(),
        'total_revenue': 0,
        'monthly_revenue': 0,
        'avg_subscription_value': 0,
        'churn_rate': 0
    }
    
    # Receita total
    stats['total_revenue'] = db.session.query(func.sum(Transaction.amount)).join(
        Subscription
    ).filter(
        Subscription.group_id == id,
        Transaction.status == 'completed'
    ).scalar() or 0
    
    # Receita do mês atual
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    stats['monthly_revenue'] = db.session.query(func.sum(Transaction.amount)).join(
        Subscription
    ).filter(
        Subscription.group_id == id,
        Transaction.status == 'completed',
        Transaction.created_at >= start_of_month
    ).scalar() or 0
    
    # Valor médio de assinatura
    if stats['total_subscribers'] > 0:
        stats['avg_subscription_value'] = stats['total_revenue'] / stats['total_subscribers']
    
    # Taxa de cancelamento (churn)
    if stats['total_subscribers'] > 0:
        expired_count = Subscription.query.filter_by(
            group_id=id,
            status='expired'
        ).count()
        stats['churn_rate'] = (expired_count / stats['total_subscribers']) * 100
    
    # Buscar dados para gráficos (últimos 30 dias)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Receita por dia
    daily_revenue = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.amount).label('revenue')
    ).join(
        Subscription
    ).filter(
        Subscription.group_id == id,
        Transaction.status == 'completed',
        Transaction.created_at >= thirty_days_ago
    ).group_by(
        func.date(Transaction.created_at)
    ).all()
    
    # Novas assinaturas por dia
    daily_subscriptions = db.session.query(
        func.date(Subscription.created_at).label('date'),
        func.count(Subscription.id).label('count')
    ).filter(
        Subscription.group_id == id,
        Subscription.created_at >= thirty_days_ago
    ).group_by(
        func.date(Subscription.created_at)
    ).all()
    
    # Distribuição por plano
    plan_distribution = db.session.query(
        PricingPlan.name,
        func.count(Subscription.id).label('count')
    ).join(
        Subscription
    ).filter(
        Subscription.group_id == id,
        Subscription.status == 'active'
    ).group_by(
        PricingPlan.name
    ).all()
    
    return render_template('dashboard/group_stats.html',
                         group=group,
                         stats=stats,
                         daily_revenue=daily_revenue,
                         daily_subscriptions=daily_subscriptions,
                         plan_distribution=plan_distribution)

@bp.route('/<int:id>/link')
@login_required
def get_link(id):
    """Obter link do bot para o grupo"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    
    # CORREÇÃO: Usar group.id ao invés de telegram_id
    bot_username = os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME', 'televipbra_bot')
    bot_link = f"https://t.me/{bot_username}?start=g_{group.invite_slug}"

    return jsonify({
        'success': True,
        'link': bot_link,
        'group_name': group.name
    })