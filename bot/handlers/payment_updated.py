# bot/handlers/payment_updated.py
"""
Handler de pagamento atualizado com as novas taxas
Adicione estas modificações ao seu payment.py existente
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from datetime import datetime, timedelta
import qrcode
import io
import os
import logging

from app.models import Group, PricingPlan, Subscription, Transaction, Creator
from app.services.payment_service import PaymentService
from app.services.stripe_service import StripeService
from bot.database import get_db_session

logger = logging.getLogger(__name__)

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para quando usuário seleciona um plano"""
    query = update.callback_query
    await query.answer()
    
    # Extrair IDs
    data_parts = query.data.split('_')
    plan_id = int(data_parts[1])
    group_id = int(data_parts[2])
    
    user = update.effective_user
    
    with get_db_session() as session:
        plan = session.query(PricingPlan).get(plan_id)
        group = session.query(Group).get(group_id)
        
        if not plan or not group:
            await query.edit_message_text("❌ Erro ao processar seleção.")
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
        
        # Calcular taxas
        fees = PaymentService.calculate_fees(plan.price)
        
        # Criar sessão de checkout
        checkout_data = {
            'user_id': user.id,
            'username': user.username,
            'group_id': group_id,
            'plan_id': plan_id,
            'amount': plan.price,
            'fees': fees
        }
        
        # Armazenar dados temporariamente
        context.user_data['checkout'] = checkout_data
        
        # Oferecer opções de pagamento com breakdown de taxas
        payment_text = f"""
💳 **Pagamento - {group.name}**

📋 **Plano:** {plan.name}
💰 **Valor:** R$ {plan.price:.2f}
📅 **Duração:** {plan.duration_days} dias

━━━━━━━━━━━━━━━━━━━━

💸 **Detalhamento:**
• Valor do plano: R$ {plan.price:.2f}
• Taxa fixa: R$ {fees['fixed_fee']:.2f}
• Taxa %: R$ {fees['percentage_fee']:.2f} (7,99%)
• **Taxa total: R$ {fees['total_fee']:.2f}**

✅ **Criador recebe: R$ {fees['net_amount']:.2f}**

━━━━━━━━━━━━━━━━━━━━

**Escolha a forma de pagamento:**
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

async def handle_pix_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar pagamento via PIX com novas taxas"""
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
        
        # Criar pré-assinatura
        end_date = datetime.utcnow() + timedelta(days=plan.duration_days)
        
        subscription = Subscription(
            group_id=group.id,
            plan_id=plan.id,
            telegram_user_id=str(checkout_data['user_id']),
            telegram_username=checkout_data['username'],
            start_date=datetime.utcnow(),
            end_date=end_date,
            status='pending'
        )
        
        session.add(subscription)
        session.flush()
        
        # Criar transação com cálculo automático de taxas
        transaction = Transaction(
            subscription_id=subscription.id,
            amount=plan.price,
            status='pending',
            payment_method='pix'
        )
        # As taxas são calculadas automaticamente no __init__ do Transaction
        
        session.add(transaction)
        session.commit()
        
        # Gerar dados do PIX
        pix_data = generate_pix_data(plan.price, creator)
        
        # Criar QR Code
        qr_image = generate_qr_code(pix_data['qr_code_data'])
        
        # Salvar ID da transação no contexto
        context.user_data['pending_transaction_id'] = transaction.id
        
        # Mensagem com instruções e valores detalhados
        payment_text = f"""
💳 **Pagamento via PIX**

━━━━━━━━━━━━━━━━━━━━

📱 **Resumo do Pedido:**
• Grupo: {group.name}
• Plano: {plan.name}
• Valor total: **R$ {plan.price:.2f}**

💸 **Taxas da plataforma:**
• Taxa fixa: R$ {transaction.fixed_fee:.2f}
• Taxa %: R$ {transaction.percentage_fee:.2f} (7,99%)
• Total de taxas: R$ {transaction.total_fee:.2f}

✅ **Criador recebe: R$ {transaction.net_amount:.2f}**

━━━━━━━━━━━━━━━━━━━━

📋 **Instruções (Passo a Passo):**

1️⃣ **Abra o app do seu banco**
2️⃣ **Escolha pagar com PIX**
3️⃣ **Escaneie o QR Code acima**
4️⃣ **Confirme o valor: R$ {plan.price:.2f}**
5️⃣ **Envie o comprovante aqui**

━━━━━━━━━━━━━━━━━━━━

📱 **Chave PIX (Copia e Cola):**
```
{pix_data['pix_key']}
```

⏰ **Importante:**
• Este código expira em 30 minutos
• Após pagar, envie o comprovante
• Acesso liberado em até 2 minutos

🔐 Pagamento 100% seguro
💰 Taxa transparente: R$ 0,99 + 7,99%
"""
        
        keyboard = [[
            InlineKeyboardButton("✅ Já fiz o pagamento", callback_data=f"confirm_pix_{transaction.id}"),
        ], [
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_payment")
        ]]
        
        # Enviar QR Code
        await query.message.reply_photo(
            photo=qr_image,
            caption=payment_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Deletar mensagem anterior
        await query.message.delete()

async def handle_stripe_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processar pagamento via Stripe com novas taxas"""
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
            status='pending'
        )
        
        session.add(subscription)
        session.flush()
        
        # Criar transação com taxas calculadas automaticamente
        transaction = Transaction(
            subscription_id=subscription.id,
            amount=plan.price,
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
                'transaction_id': str(transaction.id),
                'user_id': str(checkout_data['user_id']),
                'group_id': str(group.id)
            }
        )
        
        if stripe_result['success']:
            # Salvar ID da sessão
            transaction.stripe_payment_intent_id = stripe_result['session_id']
            session.commit()
            
            # Enviar link de pagamento com detalhes das taxas
            payment_message = f"""
💳 **Pagamento via Cartão**

📋 **Detalhes do pagamento:**
• Valor: R$ {plan.price:.2f}
• Taxa de processamento: R$ {transaction.total_fee:.2f}
• Criador recebe: R$ {transaction.net_amount:.2f}

🔗 **Link de pagamento seguro:**
[Clique aqui para pagar]({stripe_result['url']})

⏱️ Este link expira em 30 minutos.

Após o pagamento, você será adicionado automaticamente ao grupo.

💰 Taxa transparente: R$ 0,99 + 7,99%
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

def generate_pix_data(amount: float, creator: Creator) -> dict:
    """Gerar dados do PIX"""
    return {
        'pix_key': creator.pix_key if creator and creator.pix_key else "pix@televip.com.br",
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