"""
Handler para gerenciamento de assinaturas
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import stripe
import os

from bot.utils.database import get_db_session
from bot.keyboards.menus import get_renewal_keyboard
from bot.utils.format_utils import format_remaining_text, get_expiry_emoji, format_date
from app.models import Subscription, Group, Creator, PricingPlan, Transaction

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

logger = logging.getLogger(__name__)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar status detalhado de todas as assinaturas"""
    # Detectar se é comando ou callback
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        message = query.message
    else:
        user = update.effective_user
        message = update.message
    
    with get_db_session() as session:
        # Buscar TODAS as assinaturas do usuário
        all_subs = session.query(Subscription).filter_by(
            telegram_user_id=str(user.id)
        ).order_by(
            Subscription.status.desc(),  # Ativas primeiro
            Subscription.end_date.desc()  # Mais recentes primeiro
        ).all()
        
        if not all_subs:
            text = "Você ainda não possui nenhuma assinatura.\n\nPara assinar um grupo, use o link de convite fornecido pelo criador."

            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            return
        
        # Separar por status
        active = [s for s in all_subs if s.status == 'active']
        expired = [s for s in all_subs if s.status == 'expired']
        cancelled = [s for s in all_subs if s.status == 'cancelled']
        
        # Calcular estatísticas
        total_spent = sum(t.amount for s in all_subs for t in s.transactions if t.status == 'completed')
        active_value = sum(s.plan.price for s in active)
        
        text = "📊 **Status Completo das Assinaturas**\n\n"
        
        # Resumo
        text += "📈 **Resumo Geral:**\n"
        text += f"• Total de assinaturas: {len(all_subs)}\n"
        text += f"• Ativas: {len(active)} ✅\n"
        text += f"• Expiradas: {len(expired)} ❌\n"
        if cancelled:
            text += f"• Canceladas: {len(cancelled)} 🚫\n"
        text += f"• Valor mensal atual: R$ {active_value:.2f}\n"
        text += f"• Total investido: R$ {total_spent:.2f}\n"
        text += "\n"
        
        # Listar ativas detalhadamente
        if active:
            text += "✅ **ASSINATURAS ATIVAS:**\n\n"
            
            need_renewal_urgent = []
            need_renewal_soon = []
            
            for i, sub in enumerate(active, 1):
                group = sub.group
                creator = group.creator
                plan = sub.plan
                is_lifetime = getattr(plan, 'is_lifetime', False) or plan.duration_days == 0

                if is_lifetime:
                    emoji = "♾️"
                else:
                    remaining = format_remaining_text(sub.end_date)
                    emoji = get_expiry_emoji(sub.end_date)
                    days_left = (sub.end_date - datetime.utcnow()).days

                    # Classificar urgência
                    if days_left <= 3:
                        need_renewal_urgent.append(sub)
                    elif days_left <= 7:
                        need_renewal_soon.append(sub)

                text += f"{i}. {emoji} **{group.name}**\n"
                text += f"   👤 Criador: @{creator.username or creator.name}\n"
                text += f"   💰 Plano: {plan.name} (R$ {plan.price:.2f})\n"

                if is_lifetime:
                    text += f"   ♾️ **Acesso Vitalicio**\n"
                else:
                    text += f"   📅 Expira: {format_date(sub.end_date)}\n"
                    text += f"   ⏳ Restam: {remaining}\n"

                    # Subscription status info
                    if getattr(sub, 'cancel_at_period_end', False):
                        text += f"   🚫 Cancelamento agendado - acesso ate {format_date(sub.end_date)}\n"
                    elif getattr(sub, 'auto_renew', False) and sub.stripe_subscription_id and not getattr(sub, 'is_legacy', False):
                        text += f"   🔄 Renovacao automatica ativa\n"
                    elif getattr(sub, 'is_legacy', False) or not sub.stripe_subscription_id:
                        text += f"   📅 Assinatura avulsa (sem renovacao automatica)\n"

                # Estatísticas da assinatura
                duration = (datetime.utcnow() - sub.start_date).days
                text += f"   📊 Assinante ha {duration} dias\n"

                text += "\n"
        
        # Listar expiradas recentes
        if expired:
            recent_expired = expired[:5]  # Últimas 5
            text += "\n❌ **EXPIRADAS RECENTEMENTE:**\n\n"
            
            for sub in recent_expired:
                group = sub.group
                days_ago = (datetime.utcnow() - sub.end_date).days
                
                text += f"• **{group.name}**\n"
                text += f"  Expirou há {days_ago} dias ({format_date(sub.end_date)})\n"
                text += f"  Durou {(sub.end_date - sub.start_date).days} dias\n\n"
            
            if len(expired) > 5:
                text += f"... e mais {len(expired) - 5} assinaturas antigas\n"
        
        # Criar botões baseados no contexto
        keyboard = []
        
        # Botões de renovação se necessário
        if need_renewal_urgent:
            keyboard.append([
                InlineKeyboardButton(
                    f"🚨 Renovar Urgente ({len(need_renewal_urgent)})",
                    callback_data="renew_urgent"
                )
            ])
        
        if need_renewal_soon:
            keyboard.append([
                InlineKeyboardButton(
                    f"⚠️ Renovar em Breve ({len(need_renewal_soon)})",
                    callback_data="renew_soon"
                )
            ])
        
        # Botões de ação para cada assinatura ativa
        for sub in active:
            group = sub.group
            row = [
                InlineKeyboardButton(
                    f"🔗 Link: {group.name[:15]}",
                    callback_data=f"get_link_{sub.id}"
                )
            ]
            if getattr(sub, 'cancel_at_period_end', False):
                row.append(
                    InlineKeyboardButton(
                        f"🔄 Reativar",
                        callback_data=f"reactivate_sub_{sub.id}"
                    )
                )
            else:
                row.append(
                    InlineKeyboardButton(
                        f"❌ Cancelar",
                        callback_data=f"cancel_sub_{sub.id}"
                    )
                )
            keyboard.append(row)

        # Botão voltar
        keyboard.append([
            InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")
        ])
        
        # Responder
        if update.callback_query:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

async def planos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listar todos os planos ativos do usuário"""
    user = update.effective_user
    
    with get_db_session() as session:
        # Buscar apenas assinaturas ativas
        active_subs = session.query(Subscription).filter_by(
            telegram_user_id=str(user.id),
            status='active'
        ).order_by(Subscription.end_date).all()
        
        if not active_subs:
            text = "Você não possui planos ativos no momento.\n\nPara assinar um grupo, use o link de convite fornecido pelo criador."
            keyboard = []
        else:
            text = f"📋 **Seus {len(active_subs)} Planos Ativos**\n\n"

            for i, sub in enumerate(active_subs, 1):
                group = sub.group
                plan = sub.plan
                is_lifetime = getattr(plan, 'is_lifetime', False) or plan.duration_days == 0

                text += f"**{i}. {group.name}**\n"
                text += f"   Plano: {plan.name} - R$ {plan.price:.2f}\n"

                if is_lifetime:
                    text += f"   Acesso vitalicio\n"
                else:
                    remaining = format_remaining_text(sub.end_date)
                    text += f"   Expira em: {remaining} ({format_date(sub.end_date)})\n"

                text += "\n"

            keyboard = [
                [
                    InlineKeyboardButton("📊 Ver Detalhes", callback_data="check_status")
                ]
            ]
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar renovação de assinatura"""
    query = update.callback_query
    await query.answer()
    
    # Identificar tipo de renovação
    if query.data == "check_renewals":
        await show_renewals_list(update, context)
    elif query.data == "renew_urgent":
        await show_urgent_renewals(update, context)
    elif query.data == "renew_soon":
        await show_soon_renewals(update, context)
    elif query.data.startswith("renew_"):
        # Renovar assinatura específica
        sub_id = int(query.data.replace("renew_", ""))
        await process_renewal(update, context, sub_id)

async def show_renewals_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar lista de assinaturas para renovar"""
    query = update.callback_query
    user = query.from_user
    
    with get_db_session() as session:
        # Buscar assinaturas que expiram em até 15 dias
        expiring = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date <= datetime.utcnow() + timedelta(days=15)
        ).order_by(Subscription.end_date).all()
        
        if not expiring:
            text = """
🔄 **Renovações**

✅ Todas as suas assinaturas estão em dia!

Nenhuma assinatura precisa ser renovada nos próximos 15 dias.
"""
            keyboard = [[
                InlineKeyboardButton("⬅️ Voltar", callback_data="check_status")
            ]]
        else:
            text = f"🔄 **Renovações Disponíveis ({len(expiring)})**\n\n"
            
            keyboard = []
            total_renewal = 0
            
            for sub in expiring:
                group = sub.group
                plan = sub.plan
                remaining = format_remaining_text(sub.end_date)
                emoji = get_expiry_emoji(sub.end_date)

                days_left = (sub.end_date - datetime.utcnow()).days
                if days_left <= 3:
                    urgency = "URGENTE"
                elif days_left <= 7:
                    urgency = "Em breve"
                else:
                    urgency = "Disponível"

                text += f"{emoji} **{group.name}**\n"
                text += f"   Status: {urgency}\n"
                text += f"   Expira em: {remaining}\n"
                text += f"   Valor renovação: R$ {plan.price:.2f}\n\n"
                
                total_renewal += plan.price
                
                # Botão para renovar
                keyboard.append([
                    InlineKeyboardButton(
                        f"{emoji} Renovar {group.name[:20]}... (R$ {plan.price:.2f})",
                        callback_data=f"renew_{sub.id}"
                    )
                ])
            
            text += f"💰 **Total para renovar tudo:** R$ {total_renewal:.2f}\n"
            text += "\n💡 Dica: Renove com antecedência e ganhe descontos!"
            
            keyboard.append([
                InlineKeyboardButton("⬅️ Voltar", callback_data="check_status")
            ])
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_urgent_renewals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar apenas renovações urgentes (3 dias ou menos)"""
    query = update.callback_query
    user = query.from_user
    
    with get_db_session() as session:
        urgent = session.query(Subscription).filter(
            Subscription.telegram_user_id == str(user.id),
            Subscription.status == 'active',
            Subscription.end_date <= datetime.utcnow() + timedelta(days=3)
        ).order_by(Subscription.end_date).all()
        
        text = "🚨 **Renovações Urgentes**\n\n"
        text += "Estas assinaturas expiram em 3 dias ou menos!\n\n"
        
        keyboard = []
        
        for sub in urgent:
            group = sub.group
            plan = sub.plan
            remaining = format_remaining_text(sub.end_date)

            text += f"🔴 **{group.name}**\n"
            text += f"   ⏰ Expira em: {remaining}!\n"
            text += f"   💰 Renovar por: R$ {plan.price:.2f}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"🚨 Renovar {group.name[:25]}...",
                    callback_data=f"renew_{sub.id}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("⬅️ Voltar", callback_data="check_status")
        ])
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def process_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    """Processar renovação de uma assinatura específica"""
    query = update.callback_query
    
    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)
        
        if not sub:
            await query.edit_message_text("❌ Assinatura não encontrada.")
            return
        
        group = sub.group
        plan = sub.plan
        
        # Simular renovação com desconto
        days_left = (sub.end_date - datetime.utcnow()).days
        
        if days_left >= 5:
            discount = 0.1  # 10% de desconto
            discount_text = "10% de desconto por renovação antecipada!"
        else:
            discount = 0
            discount_text = ""
        
        final_price = float(plan.price) * (1 - discount)
        
        text = f"""
🔄 **Renovar Assinatura**

**Grupo:** {group.name}
**Plano atual:** {plan.name}
**Duração:** {plan.duration_days} dias
**Valor original:** R$ {plan.price:.2f}
"""
        
        if discount > 0:
            text += f"\n✨ **{discount_text}**\n"
            text += f"**Valor com desconto:** R$ {final_price:.2f}\n"
            text += f"**Você economiza:** R$ {float(plan.price) - final_price:.2f}\n"
        else:
            text += f"\n**Valor:** R$ {final_price:.2f}\n"
        
        text += f"\n📅 **Nova data de expiração:** {format_date(sub.end_date + timedelta(days=plan.duration_days))}"
        
        text += "\n\n✅ A renovação é processada imediatamente"
        text += "\n🔒 Pagamento seguro via Stripe"
        
        # Armazenar dados para pagamento
        context.user_data['renewal'] = {
            'subscription_id': sub_id,
            'group_id': group.id,
            'plan_id': plan.id,
            'amount': final_price,
            'discount': discount
        }
        
        keyboard = [
            [
                InlineKeyboardButton("💳 Pagar com Cartão", callback_data="pay_renewal_stripe")
            ],
            [
                InlineKeyboardButton("❌ Cancelar", callback_data="check_renewals")
            ]
        ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostrar confirmação de cancelamento de assinatura"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # Extrair sub_id do callback_data "cancel_sub_123"
    sub_id = int(query.data.replace("cancel_sub_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id) or sub.status != 'active':
            await query.edit_message_text("❌ Assinatura não encontrada ou já cancelada.")
            return

        group = sub.group

        # Differentiate Stripe-managed vs legacy
        if sub.stripe_subscription_id and not sub.is_legacy:
            cancel_text = (
                f"Voce mantera acesso ao grupo ate **{format_date(sub.end_date)}**.\n"
                f"A renovacao automatica sera desativada."
            )
        else:
            cancel_text = (
                f"Voce mantera acesso ao grupo ate **{format_date(sub.end_date)}**.\n"
                f"Apos essa data, o acesso sera removido automaticamente."
            )

        text = (
            f"⚠️ **Cancelar Assinatura**\n\n"
            f"**Grupo:** {group.name}\n"
            f"**Plano:** {sub.plan.name}\n\n"
            f"Tem certeza que deseja cancelar?\n"
            f"{cancel_text}"
        )

        keyboard = [
            [
                InlineKeyboardButton("✅ Sim, cancelar", callback_data=f"confirm_cancel_sub_{sub.id}"),
                InlineKeyboardButton("❌ Não, manter", callback_data="back_to_start")
            ]
        ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def confirm_cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirmar cancelamento — Stripe cancel_at_period_end ou legacy immediate"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    sub_id = int(query.data.replace("confirm_cancel_sub_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id) or sub.status != 'active':
            await query.edit_message_text("❌ Assinatura nao encontrada ou ja cancelada.")
            return

        group_name = sub.group.name
        end_date_str = format_date(sub.end_date) if sub.end_date else 'N/A'

        if sub.stripe_subscription_id and not sub.is_legacy:
            # Stripe-managed: cancel at period end (keep access until end_date)
            try:
                stripe.Subscription.modify(
                    sub.stripe_subscription_id,
                    cancel_at_period_end=True
                )
                sub.cancel_at_period_end = True
                sub.auto_renew = False
                session.commit()

                text = (
                    f"✅ **Cancelamento Agendado**\n\n"
                    f"Sua assinatura do grupo **{group_name}** nao sera renovada.\n\n"
                    f"📅 Voce mantera acesso ate **{end_date_str}**.\n\n"
                    f"Mudou de ideia? Voce pode reativar a renovacao automatica a qualquer momento."
                )

                keyboard = [
                    [InlineKeyboardButton("🔄 Reativar Renovacao", callback_data=f"reactivate_sub_{sub.id}")],
                    [InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")]
                ]

            except stripe.error.StripeError as e:
                logger.error(f"Stripe error cancelling subscription: {e}")
                text = (
                    f"❌ Erro ao cancelar assinatura no Stripe.\n"
                    f"Tente novamente ou entre em contato com o suporte."
                )
                keyboard = [[InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")]]
        else:
            # Legacy: cancel at period end (manter acesso até expirar)
            sub.cancel_at_period_end = True
            sub.auto_renew = False
            session.commit()

            text = (
                f"✅ **Cancelamento Agendado**\n\n"
                f"Sua assinatura do grupo **{group_name}** nao sera renovada.\n\n"
                f"📅 Voce mantera acesso ate **{end_date_str}**.\n\n"
                f"Apos essa data, o acesso sera removido automaticamente."
            )

            keyboard = [[InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")]]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def reactivate_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reactivate a subscription that was set to cancel at period end"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    sub_id = int(query.data.replace("reactivate_sub_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id):
            await query.edit_message_text("❌ Assinatura nao encontrada.")
            return

        if not sub.stripe_subscription_id or not sub.cancel_at_period_end:
            await query.edit_message_text("❌ Esta assinatura nao pode ser reativada.")
            return

        try:
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                cancel_at_period_end=False
            )
            sub.cancel_at_period_end = False
            sub.auto_renew = True
            session.commit()

            group_name = sub.group.name

            text = (
                f"✅ **Renovacao Reativada!**\n\n"
                f"Sua assinatura do grupo **{group_name}** sera renovada automaticamente.\n\n"
                f"📅 Proxima renovacao: {format_date(sub.end_date)}"
            )

            keyboard = [[InlineKeyboardButton("🏠 Menu Principal", callback_data="back_to_start")]]

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error reactivating subscription: {e}")
            text = "❌ Erro ao reativar. Tente novamente."
            keyboard = [[InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")]]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def get_invite_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerar novo link de convite para assinatura ativa"""
    query = update.callback_query
    await query.answer("🔗 Gerando link...")
    user = query.from_user

    sub_id = int(query.data.replace("get_link_", ""))

    with get_db_session() as session:
        sub = session.query(Subscription).get(sub_id)

        if not sub or sub.telegram_user_id != str(user.id) or sub.status != 'active':
            await query.edit_message_text(
                "❌ Assinatura nao encontrada ou inativa.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
                ]])
            )
            return

        group = sub.group
        if not group or not group.telegram_id:
            await query.edit_message_text(
                "❌ Grupo sem Telegram ID configurado. Contacte o suporte.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")
                ]])
            )
            return

        try:
            link_obj = await context.bot.create_chat_invite_link(
                chat_id=int(group.telegram_id),
                member_limit=1,
                expire_date=datetime.utcnow() + timedelta(days=7),
                creates_join_request=False
            )
            invite_link = link_obj.invite_link

            text = (
                f"🔗 **Novo Link de Acesso**\n\n"
                f"**Grupo:** {group.name}\n\n"
                f"Clique no botao abaixo para entrar:\n\n"
                f"⚠️ Link pessoal, uso unico, valido por 7 dias."
            )

            keyboard = [
                [InlineKeyboardButton("🚀 Entrar no Grupo", url=invite_link)],
                [InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")]
            ]

        except Exception as e:
            logger.error(f"Erro ao gerar invite link: {e}")
            text = (
                f"❌ Nao foi possivel gerar o link.\n\n"
                f"Contacte o suporte informando assinatura #{sub.id}."
            )
            keyboard = [[InlineKeyboardButton("🏠 Menu", callback_data="back_to_start")]]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )