"""
Handler para processar pagamentos apenas com Stripe
"""
import os
import stripe
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from app.models import Group, PricingPlan, Subscription, Transaction, Creator
logger = logging.getLogger(__name__)

# Importar StripeService depois de configurar o path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.stripe_service import StripeService

# Configurar Stripe API key
stripe_key = os.getenv('STRIPE_SECRET_KEY')
if stripe_key:
    stripe.api_key = stripe_key
    logger.info("✅ Stripe API key configurada")
else:
    logger.error("❌ STRIPE_SECRET_KEY não encontrada no .env!")

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler quando usuário seleciona um plano"""
    query = update.callback_query
    await query.answer()
    
    # Extrair dados do callback
    data = query.data.split('_')
    group_id = int(data[1])
    plan_id = int(data[2])
    
    user = query.from_user
    
    with get_db_session() as session:
        # Buscar plano e grupo
        plan = session.query(PricingPlan).get(plan_id)
        group = session.query(Group).get(group_id)
        
        if not plan or not group:
            await query.edit_message_text("❌ Plano não encontrado.")
            return
        
        # Verificar se já tem assinatura ativa
        existing_sub = session.query(Subscription).filter_by(
            group_id=group_id,
            telegram_user_id=str(user.id),
            status='active'
        ).first()
        
        if existing_sub:
            days_left = (existing_sub.end_date - datetime.utcnow()).days
            
            renewal_text = f"""
✅ **Você já possui uma assinatura ativa!**

📱 Grupo: {group.name}
📅 Válida até: {existing_sub.end_date.strftime('%d/%m/%Y')}
⏱️ Dias restantes: {days_left}

💡 **Opções:**
• Use /status para ver todos os detalhes
• Aguarde próximo ao vencimento para renovar
• Entre em contato com o suporte se precisar de ajuda
"""
            
            keyboard = [[
                InlineKeyboardButton("📊 Ver Status", callback_data="check_status"),
                InlineKeyboardButton("❌ Fechar", callback_data="close")
            ]]
            
            await query.edit_message_text(
                renewal_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Criar sessão de checkout
        checkout_data = {
            'user_id': user.id,
            'username': user.username,
            'group_id': group_id,
            'plan_id': plan_id,
            'amount': plan.price
        }
        
        # Armazenar dados temporariamente
        context.user_data['checkout'] = checkout_data
        
        # Formatar duração
        if plan.duration_days == 30:
            duration_text = "1 mês"
        elif plan.duration_days == 90:
            duration_text = "3 meses"
        elif plan.duration_days == 180:
            duration_text = "6 meses"
        elif plan.duration_days == 365:
            duration_text = "1 ano"
        else:
            duration_text = f"{plan.duration_days} dias"
        
        # Calcular valor por dia
        daily_value = plan.price / plan.duration_days
        
        # Mensagem de confirmação
        payment_text = f"""
💳 **Confirmar Assinatura**

📱 **Grupo:** {group.name}
📋 **Plano:** {plan.name}
⏱️ **Duração:** {duration_text}
💰 **Valor:** R$ {plan.price:.2f}
📊 **Valor por dia:** R$ {daily_value:.2f}

━━━━━━━━━━━━━━━━━━━━

🔐 **Pagamento Seguro via Stripe**
• Aceitamos cartões de crédito e débito
• Pagamento processado instantaneamente
• Seus dados são 100% protegidos
• Acesso liberado automaticamente

━━━━━━━━━━━━━━━━━━━━

Ao continuar, você será redirecionado para uma página segura de pagamento.
"""
        
        keyboard = [
            [InlineKeyboardButton("💳 Pagar com Cartão", callback_data=f"stripe_{plan_id}")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_payment")]
        ]
        
        await query.edit_message_text(
            payment_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_stripe_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar pagamento via Stripe"""
    query = update.callback_query
    await query.answer()
    
    checkout_data = context.user_data.get('checkout')
    if not checkout_data:
        await query.edit_message_text("❌ Sessão expirada. Por favor, comece novamente.")
        return
    
    # Mostrar que está processando
    await query.edit_message_text(
        "⏳ **Gerando link de pagamento...**\n\nAguarde um momento.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    with get_db_session() as session:
        plan = session.query(PricingPlan).get(checkout_data['plan_id'])
        group = session.query(Group).get(checkout_data['group_id'])
        
        if not plan or not group:
            await query.edit_message_text("❌ Erro ao processar pagamento.")
            return
        
        # Criar pré-assinatura
        end_date = datetime.utcnow() + timedelta(days=plan.duration_days)
        
        subscription = Subscription(
            group_id=group.id,
            plan_id=plan.id,
            telegram_user_id=str(checkout_data['user_id']),
            telegram_username=checkout_data['username'],
            start_date=datetime.utcnow(),
            end_date=end_date,
            status='pending'  # Pendente até pagamento
        )
        
        session.add(subscription)
        session.flush()
        
        # Criar transação pendente
        transaction = Transaction(
            subscription_id=subscription.id,
            amount=plan.price,
            fee=plan.price * 0.01,
            net_amount=plan.price * 0.99,
            status='pending',
            payment_method='stripe'
        )
        
        session.add(transaction)
        session.commit()
        
        # Criar sessão de checkout no Stripe
        bot_username = os.getenv('BOT_USERNAME', 'televipbra_bot')
        success_url = f"https://t.me/{bot_username}?start=success_{subscription.id}"
        cancel_url = f"https://t.me/{bot_username}?start=cancel"
        
        # Log para debug
        logger.info(f"Criando checkout session para: {group.name} - {plan.name}")
        logger.info(f"Valor: R$ {plan.price}")
        
        try:
            stripe_result = StripeService.create_checkout_session(
                plan_name=f"{group.name} - {plan.name}",
                amount=plan.price,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'subscription_id': str(subscription.id),
                    'user_id': str(checkout_data['user_id']),
                    'group_id': str(group.id),
                    'telegram_username': checkout_data.get('username', ''),
                    'transaction_id': str(transaction.id)
                }
            )
        except Exception as e:
            logger.error(f"Erro ao chamar StripeService: {e}")
            await query.edit_message_text(
                f"❌ **Erro ao processar pagamento**\n\n"
                f"Detalhes: {str(e)}\n\n"
                f"Por favor, tente novamente ou contate o suporte.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if stripe_result['success']:
            # Salvar ID da sessão
            transaction.stripe_payment_intent_id = stripe_result['session_id']
            session.commit()
            
            # Limpar checkout data
            context.user_data.pop('checkout', None)
            
            # Enviar link de pagamento
            payment_message = f"""
💳 **Link de Pagamento Gerado!**

━━━━━━━━━━━━━━━━━━━━

📱 **Resumo do Pedido:**
• Grupo: {group.name}
• Plano: {plan.name}
• Valor: **R$ {plan.price:.2f}**

━━━━━━━━━━━━━━━━━━━━

🔐 **Como pagar:**

1️⃣ Clique no link abaixo
2️⃣ Preencha os dados do cartão
3️⃣ Confirme o pagamento
4️⃣ Você será redirecionado de volta ao bot

🔗 **[CLIQUE AQUI PARA PAGAR]({stripe_result['url']})**

━━━━━━━━━━━━━━━━━━━━

⏰ **Importante:**
• Este link expira em 30 minutos
• Pagamento 100% seguro via Stripe
• Acesso liberado automaticamente
• Você receberá confirmação aqui no bot

💡 *Após o pagamento, use /start para ver seu acesso*
"""
            
            keyboard = [[
                InlineKeyboardButton("🔗 Abrir Página de Pagamento", url=stripe_result['url'])
            ]]
            
            await query.edit_message_text(
                payment_message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            error_msg = stripe_result.get('error', 'Erro desconhecido')
            await query.edit_message_text(
                f"❌ **Erro ao criar link de pagamento**\n\n"
                f"Detalhes: {error_msg}\n\n"
                f"Por favor, tente novamente ou contate o suporte.",
                parse_mode=ParseMode.MARKDOWN
            )

async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar processo de pagamento"""
    query = update.callback_query
    await query.answer()
    
    # Limpar dados do checkout
    context.user_data.pop('checkout', None)
    
    await query.edit_message_text(
        "❌ **Pagamento cancelado**\n\n"
        "Que pena! Esperamos você em breve.\n\n"
        "💡 Lembre-se: nossos grupos oferecem conteúdo exclusivo e de alta qualidade!\n\n"
        "Use /start quando quiser tentar novamente.",
        parse_mode=ParseMode.MARKDOWN
    )