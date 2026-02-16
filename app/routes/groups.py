# app/routes/groups.py
import time
from markupsafe import escape
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response, session, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import json
from app import db, limiter
from app.models import Group, PricingPlan, Subscription, Transaction
from app.utils.admin_helpers import get_effective_creator, is_admin_viewing
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

def _save_cover_image(file, group_id, old_cover_url=None):
    """Valida, sanitiza e salva imagem de capa. Remove capa antiga do disco."""
    from app.utils.security import validate_and_sanitize_image

    if not file or file.filename == '':
        return None

    try:
        clean_bytes, ext = validate_and_sanitize_image(file)
    except ValueError:
        return None

    # Remover capa antiga do disco
    if old_cover_url and '/uploads/covers/' in (old_cover_url or ''):
        old_filename = old_cover_url.rsplit('/', 1)[-1]
        old_path = os.path.join(current_app.static_folder, 'uploads', 'covers', old_filename)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    filename = secure_filename(f"{group_id}_{int(time.time())}.{ext}")
    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'covers')
    filepath = os.path.join(upload_dir, filename)
    with open(filepath, 'wb') as f:
        f.write(clean_bytes)
    return url_for('static', filename=f"uploads/covers/{filename}")


def _validate_plan_input(name, price_str, duration_str, description=None, is_lifetime=False):
    """Validate plan input fields. Returns (errors list, price float, duration int)."""
    errors = []
    price = None
    duration = None

    if not name or len(name.strip()) == 0:
        errors.append('Nome do plano é obrigatório')
    elif len(name) > 30:
        errors.append('Nome do plano deve ter no máximo 30 caracteres')

    try:
        price = float(price_str)
        if price < 5 or price > 10000:
            errors.append('Preço mínimo é R$ 5,00 (exigência do Stripe para boleto).')
    except (ValueError, TypeError):
        errors.append('Preço inválido')

    if is_lifetime:
        duration = 0
    else:
        try:
            duration_float = float(duration_str)
            if duration_float != int(duration_float):
                errors.append('Duração deve ser um número inteiro (sem decimais).')
            else:
                duration = int(duration_float)
                if duration <= 0 or duration > 365:
                    errors.append('Duração deve ser entre 1 e 365 dias')
        except (ValueError, TypeError):
            errors.append('Duração inválida')

    if description and len(description) > 500:
        errors.append('Descrição do plano deve ter no máximo 500 caracteres')

    return errors, price, duration


def _notify_plan_price_change(plan, old_price, new_price):
    """Notificar assinantes ativos sobre mudança de preço via Telegram."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN')
    if not bot_token:
        return

    group = plan.group
    creator = group.creator
    active_subs = Subscription.query.filter_by(
        plan_id=plan.id, status='active'
    ).all()

    for sub in active_subs:
        end_date_str = sub.end_date.strftime('%d/%m/%Y') if sub.end_date else 'N/A'
        text = (
            f"<b>Alteração de preço</b>\n\n"
            f"O criador <b>{escape(creator.name)}</b> alterou o valor do plano "
            f"<b>{escape(plan.name)}</b> do grupo <b>{escape(group.name)}</b>.\n\n"
            f"Valor anterior: <code>R$ {old_price:.2f}</code>\n"
            f"Novo valor: <code>R$ {new_price:.2f}</code>\n\n"
            f"Sua próxima renovação em <code>{end_date_str}</code> será "
            f"no novo valor.\n\n"
            f"<i>Se preferir, pode cancelar a qualquer momento.</i>"
        )
        try:
            requests.post(
                f'https://api.telegram.org/bot{bot_token}/sendMessage',
                json={'chat_id': sub.telegram_user_id, 'text': text, 'parse_mode': 'HTML'},
                timeout=5
            )
        except Exception:
            pass


def _escape_ilike(search_term):
    """Escape SQL ILIKE wildcard characters in user input."""
    return search_term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

@bp.route('/')
@login_required
def list():
    """Lista todos os grupos do criador"""
    effective = get_effective_creator()
    groups = Group.query.filter_by(creator_id=effective.id).all()
    
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
    if is_admin_viewing():
        flash('Ação não permitida no modo admin.', 'warning')
        return redirect(url_for('groups.list'))

    if request.method == 'POST':
        # Dados básicos do grupo
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        telegram_id = request.form.get('telegram_id', '').replace(' ', '').replace('\t', '').strip()
        invite_link = request.form.get('invite_link', '').strip()
        chat_type = request.form.get('chat_type', 'group')
        if chat_type not in ('group', 'channel'):
            chat_type = 'group'

        # Validar formato do telegram_id (deve ser numerico, opcionalmente com -)
        if telegram_id and not telegram_id.lstrip('-').isdigit():
            flash('ID do Telegram deve ser numérico.', 'error')
            return render_template('dashboard/group_form.html',
                                 group=None, show_success_modal=False)

        # Validar grupo no Telegram
        bot_token = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')

        if bot_token and telegram_id:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/getChat"
                response = requests.get(url, params={"chat_id": telegram_id}, timeout=10)

                if response.status_code != 200:
                    flash('Erro ao conectar com o Telegram. Verifique o ID e tente novamente.', 'error')
                    return render_template('dashboard/group_form.html',
                                         group=None, show_success_modal=False)

                try:
                    data = response.json()
                except Exception:
                    flash('Resposta inválida do Telegram. Tente novamente.', 'error')
                    return render_template('dashboard/group_form.html',
                                         group=None, show_success_modal=False)

                if not data.get('ok'):
                    error_msg = str(escape(data.get('description', 'Erro desconhecido')))
                    flash(f'Telegram: {error_msg}', 'error')
                    return render_template('dashboard/group_form.html',
                                         group=None, show_success_modal=False)

                # Verificar se o bot é admin
                bot_id = bot_token.split(':')[0]
                bot_member = requests.get(
                    f"https://api.telegram.org/bot{bot_token}/getChatMember",
                    params={"chat_id": telegram_id, "user_id": bot_id},
                    timeout=10
                )

                if bot_member.status_code == 200:
                    member_data = bot_member.json()
                    if member_data.get('ok'):
                        status = member_data.get('result', {}).get('status')
                        if status not in ['administrator', 'creator']:
                            flash('O bot precisa ser administrador do grupo! Adicione-o como admin e tente novamente.', 'warning')
                            return render_template('dashboard/group_form.html',
                                                 group=None, show_success_modal=False)

            except requests.exceptions.RequestException as req_error:
                logger.error(f"Telegram connection error: {req_error}")
                flash('Erro de conexão com o Telegram. Tente novamente.', 'error')
                return render_template('dashboard/group_form.html',
                                     group=None, show_success_modal=False)
            except Exception as e:
                logger.error(f"Erro na validação do grupo Telegram: {e}")
                flash('Erro ao validar o grupo. Tente novamente.', 'error')
                return render_template('dashboard/group_form.html',
                                     group=None, show_success_modal=False)
        elif not telegram_id:
            flash('ID do Telegram é obrigatório.', 'error')
            return render_template('dashboard/group_form.html',
                                 group=None, show_success_modal=False)

        # Verificar se já existe grupo com este telegram_id
        if telegram_id:
            existing_group = Group.query.filter_by(telegram_id=telegram_id).first()
            if existing_group:
                flash('Já existe um grupo cadastrado com este ID do Telegram.', 'error')
                return render_template('dashboard/group_form.html',
                                     group=None, show_success_modal=False)

        # Criar grupo + planos de forma atômica
        try:
            # Processar whitelist do formulário
            whitelist_ids = request.form.getlist('whitelist_ids[]')
            whitelist_names = request.form.getlist('whitelist_names[]')
            whitelist_data = []
            for i, tid in enumerate(whitelist_ids):
                tid = tid.strip()
                if tid and tid.isdigit():
                    wl_name = whitelist_names[i].strip() if i < len(whitelist_names) else ''
                    whitelist_data.append({
                        'telegram_id': tid,
                        'name': wl_name[:50],
                        'added_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M')
                    })

            group = Group(
                name=name,
                description=description,
                telegram_id=telegram_id or None,
                invite_link=invite_link or None,
                creator_id=current_user.id,
                is_active=True,
                is_public='is_public' in request.form,
                chat_type=chat_type,
                whitelist_json=json.dumps(whitelist_data) if whitelist_data else '[]',
                anti_leak_enabled='anti_leak_enabled' in request.form
            )
            db.session.add(group)
            db.session.flush()  # gera group.id sem commitar

            # Upload de capa (se enviado arquivo)
            cover_file = request.files.get('cover_image')
            if cover_file and cover_file.filename:
                cover_url = _save_cover_image(cover_file, group.id)
                if cover_url:
                    group.cover_image_url = cover_url

            # Adicionar planos (create) — máximo 5
            plan_names = request.form.getlist('plan_name[]')[:6]
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
                        name=plan_names[i][:30],
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
    effective = get_effective_creator()
    group = Group.query.filter_by(id=id, creator_id=effective.id).first_or_404()

    if request.method == 'POST':
        if is_admin_viewing():
            flash('Ação não permitida no modo admin.', 'warning')
            return redirect(url_for('groups.list'))
        # Atualizar dados básicos
        group.name = request.form.get('name')
        group.description = request.form.get('description')
        group.invite_link = request.form.get('invite_link')
        group.is_active = 'is_active' in request.form
        group.is_public = 'is_public' in request.form

        # Upload de capa (se enviado arquivo)
        cover_file = request.files.get('cover_image')
        if cover_file and cover_file.filename:
            cover_url = _save_cover_image(cover_file, group.id, old_cover_url=group.cover_image_url)
            if cover_url:
                group.cover_image_url = cover_url

        # Atualizar lista de exceção (whitelist)
        whitelist_ids = request.form.getlist('whitelist_ids[]')
        whitelist_names = request.form.getlist('whitelist_names[]')
        new_whitelist = []
        for i, tid in enumerate(whitelist_ids):
            tid = tid.strip()
            if tid and tid.isdigit():
                name = whitelist_names[i].strip() if i < len(whitelist_names) else ''
                # Preserve original added_at if entry already existed
                existing = next((e for e in group.get_whitelist() if e['telegram_id'] == tid), None)
                new_whitelist.append({
                    'telegram_id': tid,
                    'name': name[:50],
                    'added_at': existing['added_at'] if existing else datetime.utcnow().strftime('%Y-%m-%d %H:%M')
                })
        group.whitelist_json = json.dumps(new_whitelist)

        # In-place plan editing: update existing plans, create new ones
        plan_ids = request.form.getlist('plan_id[]')
        plan_names = request.form.getlist('plan_name[]')[:6]
        plan_durations = request.form.getlist('plan_duration[]')
        plan_durations_original = request.form.getlist('plan_duration_original[]')
        plan_prices = request.form.getlist('plan_price[]')
        plan_lifetimes = request.form.getlist('plan_lifetime[]')

        submitted_plan_ids = set()
        for i in range(len(plan_names)):
            if not plan_names[i]:
                continue

            plan_id_str = plan_ids[i] if i < len(plan_ids) else ''
            lifetime = (plan_lifetimes[i] == '1') if i < len(plan_lifetimes) else False

            # For plans with active subs, duration comes from hidden original field
            duration_str = plan_durations[i] if i < len(plan_durations) else '0'
            if not duration_str and i < len(plan_durations_original) and plan_durations_original[i]:
                duration_str = plan_durations_original[i]

            errs, price, duration = _validate_plan_input(
                plan_names[i],
                plan_prices[i] if i < len(plan_prices) else '0',
                duration_str,
                is_lifetime=lifetime
            )
            if errs:
                for e in errs:
                    flash(e, 'error')
                continue

            if plan_id_str:
                # Update existing plan in-place
                plan = PricingPlan.query.get(int(plan_id_str))
                if plan and plan.group_id == group.id:
                    old_price = float(plan.price)

                    active_sub_count = Subscription.query.filter_by(
                        plan_id=plan.id, status='active'
                    ).count()

                    plan.name = plan_names[i][:30]
                    plan.price = price
                    plan.is_lifetime = lifetime
                    plan.is_active = True

                    if active_sub_count == 0:
                        plan.duration_days = duration
                    # else: keep existing duration — active subs depend on it

                    if price != old_price and active_sub_count > 0:
                        _notify_plan_price_change(plan, old_price, price)

                    submitted_plan_ids.add(plan.id)
            else:
                # Create new plan
                plan = PricingPlan(
                    group_id=group.id,
                    name=plan_names[i][:30],
                    duration_days=duration,
                    price=price,
                    is_lifetime=lifetime,
                    is_active=True
                )
                db.session.add(plan)

        # Deactivate or delete plans NOT in submitted list
        existing_plans = PricingPlan.query.filter_by(group_id=group.id, is_active=True).all()
        for plan in existing_plans:
            if plan.id not in submitted_plan_ids:
                has_active_subs = Subscription.query.filter_by(
                    plan_id=plan.id, status='active'
                ).count() > 0
                if has_active_subs:
                    # NEVER deactivate a plan with active subscribers
                    pass
                elif Subscription.query.filter(Subscription.plan_id == plan.id).count() > 0:
                    plan.is_active = False
                else:
                    db.session.delete(plan)

        db.session.commit()
        flash('Grupo atualizado com sucesso!', 'success')
        return redirect(url_for('groups.list'))

    # GET: compute active subscriber counts per plan
    # Also auto-heal: reactivate any plan that has active subs but was incorrectly deactivated
    plan_sub_counts = {}
    for plan in group.pricing_plans:
        active_count = Subscription.query.filter_by(
            plan_id=plan.id, status='active'
        ).count()
        if active_count > 0:
            if not plan.is_active:
                plan.is_active = True
                db.session.commit()
            plan_sub_counts[plan.id] = active_count

    return render_template('dashboard/group_form.html', group=group, plan_sub_counts=plan_sub_counts)

@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Deletar grupo"""
    if is_admin_viewing():
        flash('Ação não permitida no modo admin.', 'warning')
        return redirect(url_for('groups.list'))

    effective = get_effective_creator()
    group = Group.query.filter_by(id=id, creator_id=effective.id).first_or_404()
    
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
    if is_admin_viewing():
        flash('Ação não permitida no modo admin.', 'warning')
        return redirect(url_for('groups.list'))

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
    if is_admin_viewing():
        flash('Ação não permitida no modo admin.', 'warning')
        return redirect(url_for('groups.list'))

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
                    group_name_safe = group.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    msg_safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    msg_text = f"<b>Mensagem de {group_name_safe}</b>\n\n{msg_safe}"

                    payload = {
                        'chat_id': sub.telegram_user_id,
                        'text': msg_text,
                        'parse_mode': 'HTML',
                    }

                    if group.anti_leak_enabled:
                        from bot.utils.watermark import watermark_text
                        payload['text'] = watermark_text(msg_text, sub.id)
                        payload['protect_content'] = True

                    response = requests.post(
                        f'https://api.telegram.org/bot{bot_token}/sendMessage',
                        json=payload,
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
    effective = get_effective_creator()
    group = Group.query.filter_by(id=id, creator_id=effective.id).first_or_404()

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
    effective = get_effective_creator()
    group = Group.query.filter_by(id=id, creator_id=effective.id).first_or_404()
    sub = Subscription.query.filter_by(id=sub_id, group_id=group.id).first_or_404()

    now = datetime.utcnow()
    days_left = (sub.end_date - now).days if sub.end_date > now else 0

    transactions = sub.transactions.order_by(Transaction.created_at.desc()).limit(10).all()

    return render_template('dashboard/_subscriber_details.html',
                           sub=sub, now=now, days_left=days_left,
                           transactions=transactions)


@bp.route('/<int:id>/export-subscribers')
@login_required
@limiter.limit("30 per hour")
def export_subscribers(id):
    """Exportar lista de assinantes em CSV"""
    effective = get_effective_creator()
    group = Group.query.filter_by(id=id, creator_id=effective.id).first_or_404()

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
    effective = get_effective_creator()
    group = Group.query.filter_by(id=id, creator_id=effective.id).first_or_404()
    
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

@bp.route('/<int:id>/antileak', methods=['POST'])
@login_required
def toggle_antileak(id):
    """Ativar/Desativar proteção anti-vazamento"""
    if is_admin_viewing():
        flash('Ação não permitida no modo admin.', 'warning')
        return redirect(url_for('groups.list'))

    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    group.anti_leak_enabled = not group.anti_leak_enabled
    db.session.commit()
    status = 'ativado' if group.anti_leak_enabled else 'desativado'
    flash(f'Anti-vazamento {status} para {group.name}!', 'success')
    return redirect(url_for('groups.edit', id=id))


@bp.route('/<int:id>/decode-watermark', methods=['POST'])
@login_required
def decode_watermark_route(id):
    """Decodificar marca d'água invisível para identificar vazador"""
    group = Group.query.filter_by(id=id, creator_id=current_user.id).first_or_404()
    text = request.form.get('leaked_text', '')

    from bot.utils.watermark import decode_watermark
    sub_id = decode_watermark(text)

    if sub_id:
        sub = Subscription.query.get(sub_id)
        if sub and sub.group_id == group.id:
            return jsonify({
                'found': True,
                'subscription_id': sub.id,
                'username': sub.telegram_username or 'N/A',
                'telegram_id': sub.telegram_user_id,
                'plan': sub.plan.name if sub.plan else 'N/A',
                'status': sub.status,
            })

    return jsonify({'found': False})


@bp.route('/<int:id>/link')
@login_required
def get_link(id):
    """Obter link do bot para o grupo"""
    effective = get_effective_creator()
    group = Group.query.filter_by(id=id, creator_id=effective.id).first_or_404()
    
    # CORREÇÃO: Usar group.id ao invés de telegram_id
    bot_username = os.getenv('TELEGRAM_BOT_USERNAME') or os.getenv('BOT_USERNAME', 'televipbra_bot')
    bot_link = f"https://t.me/{bot_username}?start=g_{group.invite_slug}"

    return jsonify({
        'success': True,
        'link': bot_link,
        'group_name': group.name
    })