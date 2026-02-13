# bot/handlers/start.py
"""
Handler do comando /start com suporte multi-criador
VERSÃO CORRIGIDA - Sem referências a plan.description
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_plans_menu
from bot.utils.format_utils import (
    format_remaining_text, get_expiry_emoji, format_date, format_date_code,
    format_currency, escape_html
)
from app.models import Group, Creator, PricingPlan, Subscription, Transaction
from bot.handlers.payment_verification import check_payment_from_start

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler do comando /start
    - Sem parâmetros: mostra dashboard do usuário
    - Com g_XXXXX: inicia fluxo de assinatura
    - Com success_: retorno de pagamento bem-sucedido
    - Com cancel: retorno de pagamento cancelado
    """
    user = update.effective_user
    args = context.args

    logger.info(f"Start command - User: {user.id}, Args: {args}")

    # Tratar diferentes tipos de argumentos
    if args:
        if args[0].startswith('success_') or args[0] == 'payment_success':
            await check_payment_from_start(update, context)
            return
        elif args[0] == 'cancel':
            await handle_payment_cancel(update, context)
            return
        elif args[0].startswith('g_'):
            group_identifier = args[0][2:]
            logger.info(f"Iniciando fluxo de assinatura para grupo: {group_identifier}")
            await start_subscription_flow(update, context, group_identifier)
            return

    # Sem argumentos - mostrar dashboard
    await show_user_dashboard(update, context)

async def show_user_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dashboard central do assinante — nunca bloqueia, mostra tudo."""
    # Detectar se veio de comando ou callback
    if update.callback_query:
        user = update.callback_query.from_user
        message = update.callback_query.message
        is_callback = True
    else:
        user = update.effective_user
        message = update.message
        is_callback = False

    name = escape_html(user.first_name)

    with get_db_session() as session:
        now = datetime.utcnow()

        # Buscar TODAS as assinaturas do usuário
        all_subs = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status.in_(['active', 'expired', 'cancelled'])
        ).order_by(Subscription.end_date.desc()).all()

        active = [s for s in all_subs if s.status == 'active' and s.end_date > now]
        expiring = [s for s in active if s.end_date <= now + timedelta(days=7)]
        expired = [s for s in all_subs if s.status == 'expired' or (s.status == 'active' and s.end_date <= now)]
        cancelled = [s for s in all_subs if s.status == 'cancelled']
        history_count = len(expired) + len(cancelled)

        # Verificar pagamentos pendentes (não bloqueia, só avisa)
        pending_txn = session.query(Transaction).join(
            Subscription
        ).filter(
            Subscription.telegram_user_id == str(user.id),
            Transaction.status == 'pending',
            Transaction.created_at >= now - timedelta(hours=2)
        ).order_by(Transaction.created_at.desc()).first()

        # ── Montar texto ──
        text = f"Olá, {name}!\n"

        # Seção: pagamento pendente (aviso, não bloqueio)
        if pending_txn:
            text += "\n⏳ Você tem um pagamento pendente\n"

        # Seção: assinaturas ativas
        if active:
            text += f"\n✅ {len(active)} assinatura{'s' if len(active) != 1 else ''} ativa{'s' if len(active) != 1 else ''}\n"
            for sub in active[:5]:
                group_name = escape_html(sub.group.name) if sub.group else "N/A"
                is_lifetime = getattr(sub.plan, 'is_lifetime', False) or (sub.plan and sub.plan.duration_days == 0)
                if is_lifetime:
                    remaining = "Vitalício"
                    emoji = "♾️"
                else:
                    remaining = format_remaining_text(sub.end_date)
                    emoji = get_expiry_emoji(sub.end_date)
                text += f"  {emoji} {group_name} — {remaining}\n"
            if len(active) > 5:
                text += f"  ... e mais {len(active) - 5}\n"

            if expiring:
                text += f"\n⚠️ {len(expiring)} expirando em breve\n"
        else:
            text += "\nVocê não possui assinaturas ativas.\n"

        if history_count > 0:
            text += f"\n📋 {history_count} no histórico\n"

        # ── Montar botões ──
        keyboard = []

        # Botão de pagamento pendente
        if pending_txn:
            stripe_url = context.user_data.get('stripe_checkout_url')
            if stripe_url:
                keyboard.append([InlineKeyboardButton("💳 Completar Pagamento", url=stripe_url)])
            keyboard.append([
                InlineKeyboardButton("✅ Já Paguei", callback_data="check_payment_status"),
                InlineKeyboardButton("❌ Desistir", callback_data="abandon_payment")
            ])

        # Botões de navegação
        if active:
            keyboard.append([InlineKeyboardButton("✅ Minhas Assinaturas", callback_data="subs_active")])
        if history_count > 0:
            keyboard.append([InlineKeyboardButton("📋 Histórico", callback_data="subs_history")])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        # Enviar ou editar mensagem
        if is_callback:
            await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def start_subscription_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, group_identifier: str):
    """Iniciar fluxo de assinatura para um grupo específico (por slug ou ID legado)"""
    user = update.effective_user

    with get_db_session() as session:
        # Tentar buscar por invite_slug primeiro, fallback para ID numérico (links antigos)
        group = session.query(Group).filter_by(invite_slug=group_identifier).first()
        if not group:
            try:
                group_id = int(group_identifier)
                group = session.query(Group).filter_by(id=group_id).first()
            except ValueError:
                pass

        if not group:
            logger.warning(f"Grupo não encontrado - identificador: {group_identifier}")

            await update.message.reply_text(
                "Grupo não encontrado. O link pode estar expirado ou inválido."
            )
            return

        if not group.is_active:
            logger.warning(f"Grupo inativo: {group.name} (ID: {group.id})")
            await update.message.reply_text(
                "Este grupo está temporariamente indisponível."
            )
            return

        # Verificar se o criador está bloqueado
        creator = group.creator
        if creator and getattr(creator, 'is_blocked', False):
            logger.warning(f"Criador bloqueado: {creator.name} (grupo: {group.name})")
            await update.message.reply_text(
                "Este grupo está temporariamente indisponível."
            )
            return

        # Log para debug
        logger.info(f"Grupo encontrado: {group.name} (ID: {group.id}, Ativo: {group.is_active})")

        group_name = escape_html(group.name)

        # Verificar se já tem assinatura ativa
        existing_sub = session.query(Subscription).filter_by(
            group_id=group.id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()

        if existing_sub:
            remaining = format_remaining_text(existing_sub.end_date)
            plan_name = escape_html(existing_sub.plan.name) if existing_sub.plan else "N/A"
            text = (
                f"<b>Você já é assinante</b>\n\n"
                f"Grupo: <b>{group_name}</b>\n"
                f"Plano: <code>{plan_name}</code>\n"
                f"Expira em: {format_date_code(existing_sub.end_date)} ({remaining})"
            )
            keyboard = [
                [
                    InlineKeyboardButton("Ver Status", callback_data="check_status"),
                    InlineKeyboardButton("Menu Principal", callback_data="back_to_start")
                ]
            ]

            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Buscar planos disponíveis
        plans = session.query(PricingPlan).filter_by(
            group_id=group.id,
            is_active=True
        ).order_by(PricingPlan.price).all()

        if not plans:
            logger.warning(f"Nenhum plano ativo para o grupo {group.name}")
            await update.message.reply_text(
                "Nenhum plano disponível para este grupo no momento.\n\n"
                "Entre em contato com o administrador do grupo."
            )
            return

        # Mostrar informações do grupo e planos
        type_label = "canal" if group.chat_type == 'channel' else "grupo"
        description = escape_html(group.description) if group.description else f"{type_label.capitalize()} VIP exclusivo"
        text = (
            f"Bem-vindo ao {type_label} <b>{group_name}</b>!\n"
            f"{description}\n\n"
            f"<b>Planos disponíveis:</b>\n"
        )

        keyboard = []
        for plan in plans:
            plan_name = escape_html(plan.name)
            text += f"\n<code>{plan_name}</code> — {format_currency(plan.price)} / {plan.duration_days} dias"

            keyboard.append([
                InlineKeyboardButton(
                    f"{plan.name} - {format_currency(plan.price)}",
                    callback_data=f"plan_{group.id}_{plan.id}"
                )
            ])

        text += '\n\n<i>Ao assinar, você concorda com os <a href="https://televip.app/termos">termos de uso</a>.</i>'

        keyboard.append([
            InlineKeyboardButton("Cancelar", callback_data="cancel")
        ])

        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_payment_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para pagamento cancelado"""
    text = (
        "<b>Pagamento cancelado</b>\n\n"
        "Nenhuma cobrança foi realizada.\n"
        "Para tentar novamente, use o link de convite do grupo."
    )

    keyboard = [
        [InlineKeyboardButton("Menu Principal", callback_data="back_to_start")]
    ]

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
