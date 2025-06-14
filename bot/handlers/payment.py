"""
Handler para processar pagamentos
"""
import os
import qrcode
import io
import stripe
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.database import get_db_session
from bot.utils.stripe_integration import create_checkout_session
from bot.keyboards.menus import get_payment_keyboard, get_cancel_keyboard
from app.models import Group, PricingPlan, Subscription, Transaction, Creator
from app.services.stripe_service import StripeService

# Configurar logging
logger = logging.getLogger(__name__)

# Configurar Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler quando usuário seleciona um plano"""
    query = update.callback_query
    await query.answer()
    
    # Extrair dados do callback
    # Formato: plan_{group_id}_{plan_id}
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
            await query.edit_message_text(
                f"✅ Você já possui uma assinatura ativa para {group.name}.\n"
                f"Válida até: {existing_sub.end_date.strftime('%d/%m/%Y')}\n\n"
                "Use /status para ver detalhes."
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
        
        # Oferecer opções de pagamento
        payment_text = f"""
💳 *Pagamento - {group.name}*

📋 *Plano:* {plan.name}
💰 *Valor:* R$ {plan.price:.2f}
📅 *Duração:* {plan.duration_days} dias

*Escolha a forma de pagamento:*
"""
        
        keyboard = [
            [InlineKeyboardButton("💳 Pagar com Cartão (Stripe)", callback_data=f"stripe_{plan_id}")],
            [InlineKeyboardButton("🔄 Pagar com PIX", callback_data=f"pix_{plan_id}")],
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
        success_url = f"https://t.me/{os.getenv('BOT_USERNAME')}?start=success_{subscription.id}"
        cancel_url = f"https://t.me/{os.getenv('BOT_USERNAME')}?start=cancel"
        
        stripe_result = StripeService.create_checkout_session(
            plan_name=f"{group.name} - {plan.name}",
            amount=plan.price,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'subscription_id': str(subscription.id),
                'user_id': str(checkout_data['user_id']),
                'group_id': str(group.id)
            }
        )
        
        if stripe_result['success']:
            # Salvar ID da sessão
            transaction.stripe_payment_intent_id = stripe_result['session_id']
            session.commit()
            
            # Enviar link de pagamento
            payment_message = f"""
💳 *Pagamento via Cartão*

Clique no link abaixo para fazer o pagamento seguro via Stripe:

🔗 [Pagar R$ {plan.price:.2f}]({stripe_result['url']})

⏱️ Este link expira em 30 minutos.

Após o pagamento, você será adicionado automaticamente ao grupo.
"""
            
            await query.edit_message_text(
                payment_message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            await query.edit_message_text(
                f"❌ Erro ao criar link de pagamento: {stripe_result.get('error', 'Erro desconhecido')}"
            )

async def handle_pix_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar pagamento via PIX"""
    query = update.callback_query
    await query.answer()
    
    checkout_data = context.user_data.get('checkout')
    if not checkout_data:
        await query.edit_message_text("❌ Sessão expirada. Por favor, comece novamente.")
        return
    
    with get_db_session() as session:
        plan = session.query(PricingPlan).get(checkout_data['plan_id'])
        group = session.query(Group).get(checkout_data['group_id'])
        creator = session.query(Creator).get(group.creator_id)
        
        # Gerar dados do PIX (simulado por enquanto)
        pix_data = generate_pix_data(plan.price, creator)
        
        # Criar QR Code
        qr_image = generate_qr_code(pix_data['qr_code_data'])
        
        # Mensagem com instruções
        payment_text = f"""
💳 *Pagamento via PIX*

📱 *Grupo:* {group.name}
📋 *Plano:* {plan.name}
💰 *Valor:* R$ {plan.price:.2f}

*Instruções:*
1️⃣ Escaneie o QR Code ou copie o código PIX
2️⃣ Faça o pagamento
3️⃣ Envie o comprovante aqui no chat

*Chave PIX (copia e cola):*
`{pix_data['pix_key']}`

⏱️ Este pagamento expira em 30 minutos.
"""
        
        keyboard = get_payment_keyboard(checkout_data)
        
        # Enviar QR Code
        await query.message.reply_photo(
            photo=qr_image,
            caption=payment_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
        # Deletar mensagem anterior
        await query.message.delete()

async def process_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar comprovante de pagamento enviado pelo usuário"""
    user = update.effective_user
    
    # Verificar se tem checkout pendente
    checkout_data = context.user_data.get('checkout')
    if not checkout_data:
        await update.message.reply_text(
            "❌ Nenhum pagamento pendente encontrado.\n"
            "Por favor, selecione um plano primeiro."
        )
        return
    
    # Verificar se enviou foto
    if not update.message.photo:
        await update.message.reply_text(
            "📸 Por favor, envie uma foto do comprovante de pagamento."
        )
        return
    
    # Processar pagamento
    await update.message.reply_text("⏳ Verificando pagamento...")
    
    with get_db_session() as session:
        plan = session.query(PricingPlan).get(checkout_data['plan_id'])
        group = session.query(Group).get(checkout_data['group_id'])
        
        # Criar transação
        transaction = Transaction(
            subscription_id=None,  # Será atualizado depois
            amount=checkout_data['amount'],
            fee=checkout_data['amount'] * 0.01,  # 1% de taxa
            net_amount=checkout_data['amount'] * 0.99,
            status='completed',
            payment_method='pix',
            paid_at=datetime.utcnow()
        )
        
        # Criar assinatura
        end_date = datetime.utcnow() + timedelta(days=plan.duration_days)
        
        subscription = Subscription(
            group_id=group.id,
            plan_id=plan.id,
            telegram_user_id=str(user.id),
            telegram_username=user.username,
            start_date=datetime.utcnow(),
            end_date=end_date,
            status='active'
        )
        
        session.add(subscription)
        session.flush()  # Para obter o ID
        
        transaction.subscription_id = subscription.id
        session.add(transaction)
        
        # Atualizar saldo do criador
        creator = session.query(Creator).get(group.creator_id)
        creator.balance += transaction.net_amount
        creator.total_earned += transaction.net_amount
        
        # Incrementar contador de assinantes
        group.total_subscribers += 1
        
        session.commit()
        
        # Adicionar usuário ao grupo
        try:
            # Gerar link de convite se não existir
            if not group.invite_link:
                invite_link = await context.bot.create_chat_invite_link(
                    chat_id=group.telegram_id,
                    member_limit=1,  # Link para apenas 1 uso
                    expire_date=datetime.now() + timedelta(minutes=30)
                )
                invite_url = invite_link.invite_link
            else:
                invite_url = group.invite_link
            
            # Limpar dados do checkout
            context.user_data.pop('checkout', None)
            
            # Mensagem de sucesso com link
            success_text = f"""
✅ *Pagamento Confirmado!*

🎉 Bem-vindo ao {group.name}!

📅 *Sua assinatura:*
• Plano: {plan.name}
• Válida até: {end_date.strftime('%d/%m/%Y')}
• Status: Ativa

🔗 *Acesse o grupo:*
{invite_url}

💡 *Dicas:*
• Ative as notificações do grupo
• Leia as regras na mensagem fixada
• Aproveite o conteúdo exclusivo!

Qualquer dúvida, use /help
"""
            
            await update.message.reply_text(
                success_text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Erro ao gerar link de convite: {e}")
            await update.message.reply_text(
                "✅ Pagamento confirmado! Entre em contato com o administrador para receber o link do grupo."
            )

async def handle_payment_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para confirmação de pagamento via Stripe"""
    query = update.callback_query
    await query.answer()
    
    # Implementar integração com Stripe
    await query.edit_message_text(
        "🔄 Processando pagamento via Stripe...\n"
        "Você será redirecionado para página segura de pagamento."
    )

async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancelar processo de pagamento"""
    query = update.callback_query
    await query.answer()
    
    # Limpar dados do checkout
    context.user_data.pop('checkout', None)
    
    await query.edit_message_text(
        "❌ Pagamento cancelado.\n\n"
        "Use /planos quando quiser assinar."
    )

def generate_pix_data(amount: float, creator: Creator) -> dict:
    """Gerar dados do PIX"""
    # Por enquanto, dados simulados
    # Em produção, integrar com API de pagamento PIX real
    return {
        'pix_key': creator.email if creator else "pix@televip.com.br",
        'qr_code_data': f"00020126580014BR.GOV.BCB.PIX0136{creator.id if creator else 1}-{amount}",
        'transaction_id': f"TXN{datetime.now().timestamp()}"
    }

def generate_qr_code(data: str) -> io.BytesIO:
    """Gerar imagem do QR Code"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    bio = io.BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    
    return bio