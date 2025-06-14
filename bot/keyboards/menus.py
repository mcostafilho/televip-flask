"""
Teclados inline para o bot
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List

def get_main_menu() -> InlineKeyboardMarkup:
    """Menu principal do bot"""
    keyboard = [
        [
            InlineKeyboardButton("📋 Meus Planos", callback_data="my_plans"),
            InlineKeyboardButton("💳 Assinar", callback_data="subscribe")
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="check_status"),
            InlineKeyboardButton("❓ Ajuda", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_plans_menu(group_id: int) -> InlineKeyboardMarkup:
    """Menu com planos disponíveis de um grupo"""
    from bot.utils.database import get_db_session
    from app.models import Group
    
    with get_db_session() as session:
        group = session.query(Group).get(group_id)
        plans = group.pricing_plans.filter_by(is_active=True).all()
        
        keyboard = []
        
        for plan in plans:
            # Calcular desconto se houver
            monthly_price = None
            discount_text = ""
            
            if plan.duration_days > 30:
                # Encontrar plano mensal para calcular desconto
                monthly_plan = next((p for p in plans if p.duration_days == 30), None)
                if monthly_plan:
                    monthly_price = monthly_plan.price * (plan.duration_days / 30)
                    discount = ((monthly_price - plan.price) / monthly_price) * 100
                    if discount > 0:
                        discount_text = f" (-{discount:.0f}%)"
            
            button_text = f"{plan.name} - R$ {plan.price:.2f}{discount_text}"
            
            keyboard.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"plan_{group_id}_{plan.id}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
        ])
        
        return InlineKeyboardMarkup(keyboard)

def get_payment_keyboard(checkout_data: dict) -> InlineKeyboardMarkup:
    """Teclado para opções de pagamento"""
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Já fiz o pagamento",
                callback_data=f"confirm_{checkout_data['plan_id']}"
            )
        ],
        [
            InlineKeyboardButton(
                "💳 Pagar com Cartão (Stripe)",
                callback_data=f"stripe_{checkout_data['plan_id']}"
            )
        ],
        [
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_payment")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Teclado com opção de cancelar"""
    keyboard = [[
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel")
    ]]
    return InlineKeyboardMarkup(keyboard)

def get_renewal_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    """Teclado para renovação de assinatura"""
    keyboard = [[
        InlineKeyboardButton(
            "🔄 Renovar Agora",
            callback_data=f"renew_{subscription_id}"
        )
    ]]
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu() -> InlineKeyboardMarkup:
    """Menu administrativo para criadores"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Estatísticas", callback_data="admin_stats"),
            InlineKeyboardButton("👥 Assinantes", callback_data="admin_subscribers")
        ],
        [
            InlineKeyboardButton("💰 Financeiro", callback_data="admin_finance"),
            InlineKeyboardButton("⚙️ Configurações", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Teclado de confirmação para broadcast"""
    keyboard = [[
        InlineKeyboardButton("✅ Enviar", callback_data="broadcast_confirm"),
        InlineKeyboardButton("❌ Cancelar", callback_data="broadcast_cancel")
    ]]
    return InlineKeyboardMarkup(keyboard)

def get_settings_menu() -> InlineKeyboardMarkup:
    """Menu de configurações do grupo"""
    keyboard = [
        [
            InlineKeyboardButton("💰 Gerenciar Planos", callback_data="settings_plans"),
            InlineKeyboardButton("📝 Editar Descrição", callback_data="settings_description")
        ],
        [
            InlineKeyboardButton("🔗 Atualizar Link", callback_data="settings_link"),
            InlineKeyboardButton("🚫 Pausar Grupo", callback_data="settings_pause")
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data="admin_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)