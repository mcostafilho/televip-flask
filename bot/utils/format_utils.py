"""
Utilitários de formatação para o bot
"""
from typing import Union
from datetime import datetime, timedelta, timezone

# Fuso horário de Brasília (UTC-3)
BRT = timezone(timedelta(hours=-3))


def to_brt(dt: datetime) -> datetime:
    """Converter datetime UTC para horário de Brasília (UTC-3)"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume UTC se naive
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT)


def is_sub_effectively_active(sub, now=None) -> bool:
    """
    Verifica se uma assinatura está efetivamente ativa, considerando
    a janela de ~1h que o Stripe leva para finalizar e cobrar invoices
    de renovação (draft → finalized → paid).

    Para subs Stripe auto-renew (cancel_at_period_end=False), tolera
    até 2h após end_date antes de considerar expirada.
    """
    if now is None:
        now = datetime.utcnow()

    if sub.status != 'active':
        return False

    if not sub.end_date:
        return False

    # Ainda dentro do período — ativa normalmente
    if sub.end_date > now:
        return True

    # end_date já passou — verificar se é Stripe auto-renew dentro da janela
    is_stripe_autorenew = (
        getattr(sub, 'stripe_subscription_id', None)
        and not getattr(sub, 'is_legacy', False)
        and not getattr(sub, 'cancel_at_period_end', False)
    )

    if is_stripe_autorenew:
        grace = timedelta(hours=2)
        return sub.end_date > (now - grace)

    return False


def is_sub_renewing(sub, now=None) -> bool:
    """
    Retorna True se a sub está na janela de renovação do Stripe
    (end_date passou mas dentro de 2h, Stripe auto-renew ativo).
    Útil para mostrar 'Renovando...' ao invés de 'Expirada'.

    Retorna False se já existir transação completed de renovação
    após o end_date (webhook já processou, só falta atualizar end_date).
    """
    if now is None:
        now = datetime.utcnow()

    if sub.status != 'active' or not sub.end_date:
        return False

    if sub.end_date > now:
        return False  # Ainda não expirou

    is_stripe_autorenew = (
        getattr(sub, 'stripe_subscription_id', None)
        and not getattr(sub, 'is_legacy', False)
        and not getattr(sub, 'cancel_at_period_end', False)
    )

    if is_stripe_autorenew:
        grace = timedelta(hours=2)
        if sub.end_date > (now - grace):
            # Verificar se já existe transação de renovação concluída
            # Se sim, o pagamento já foi processado — não é mais "renovando"
            try:
                from app.models.subscription import Transaction
                has_renewal = Transaction.query.filter(
                    Transaction.subscription_id == sub.id,
                    Transaction.status == 'completed',
                    Transaction.billing_reason == 'subscription_cycle',
                    Transaction.paid_at >= sub.end_date - timedelta(hours=1)
                ).first()
                if has_renewal:
                    return False  # Já renovado, webhook processou
            except Exception:
                pass
            return True

    return False


def format_currency(value: Union[float, int]) -> str:
    """
    Formatar valor monetário para Real brasileiro
    
    Args:
        value: Valor a ser formatado
        
    Returns:
        String formatada (ex: R$ 29,90)
    """
    if value is None:
        return "R$ 0,00"
    
    # Garantir que é float
    value = float(value)
    
    # Formatar com 2 casas decimais
    formatted = f"R$ {value:,.2f}"
    
    # Trocar . por , (padrão brasileiro)
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    
    return formatted


def format_date(date: datetime, include_time: bool = False) -> str:
    """
    Formatar data para padrão brasileiro em horário de Brasília (BRT).

    Args:
        date: Data a ser formatada (assume UTC se naive)
        include_time: Se deve incluir horário

    Returns:
        String formatada (ex: 17/06/2025 ou 17/06/2025 14:30)
    """
    if not date:
        return "N/A"

    date = to_brt(date)

    if include_time:
        return date.strftime("%d/%m/%Y %H:%M")
    else:
        return date.strftime("%d/%m/%Y")


def format_duration(days: int) -> str:
    """
    Formatar duração em dias para texto legível
    
    Args:
        days: Número de dias
        
    Returns:
        String formatada (ex: 30 dias, 1 mês, 3 meses)
    """
    if days == 1:
        return "1 dia"
    elif days < 30:
        return f"{days} dias"
    elif days == 30:
        return "1 mês"
    elif days == 60:
        return "2 meses"
    elif days == 90:
        return "3 meses"
    elif days == 180:
        return "6 meses"
    elif days == 365:
        return "1 ano"
    elif days % 365 == 0:
        years = days // 365
        return f"{years} anos"
    elif days % 30 == 0:
        months = days // 30
        return f"{months} meses"
    else:
        return f"{days} dias"


def format_percentage(value: float) -> str:
    """
    Formatar porcentagem
    
    Args:
        value: Valor decimal (ex: 0.1 para 10%)
        
    Returns:
        String formatada (ex: 10%)
    """
    if value is None:
        return "0%"
    
    percentage = value * 100
    
    # Se for número inteiro, não mostrar decimais
    if percentage == int(percentage):
        return f"{int(percentage)}%"
    else:
        return f"{percentage:.1f}%"


def format_phone(phone: str) -> str:
    """
    Formatar número de telefone brasileiro
    
    Args:
        phone: Número de telefone
        
    Returns:
        String formatada (ex: (11) 98765-4321)
    """
    if not phone:
        return ""
    
    # Remover caracteres não numéricos
    phone = ''.join(filter(str.isdigit, phone))
    
    # Formatar baseado no tamanho
    if len(phone) == 11:  # Celular com DDD
        return f"({phone[:2]}) {phone[2:7]}-{phone[7:]}"
    elif len(phone) == 10:  # Fixo com DDD
        return f"({phone[:2]}) {phone[2:6]}-{phone[6:]}"
    elif len(phone) == 9:  # Celular sem DDD
        return f"{phone[:5]}-{phone[5:]}"
    elif len(phone) == 8:  # Fixo sem DDD
        return f"{phone[:4]}-{phone[4:]}"
    else:
        return phone


def format_remaining_text(end_date: datetime) -> str:
    """
    Formatar tempo restante como texto simples (sem emoji).
    Mostra horas quando ≤ 72h (3 dias) para maior precisão em planos curtos.
    Acima de 72h mostra dias.

    Args:
        end_date: Data final

    Returns:
        String como '5 dias', '48 horas', '30 minutos', ou 'Expirado'
    """
    if not end_date:
        return "N/A"

    total_seconds = (end_date - datetime.utcnow()).total_seconds()

    if total_seconds <= 0:
        return "Expirado"

    hours = int(total_seconds // 3600)

    if hours > 72:
        days = hours // 24
        return f"{days} {'dia' if days == 1 else 'dias'}"
    elif hours >= 1:
        return f"{hours} {'hora' if hours == 1 else 'horas'}"
    else:
        minutes = max(1, int(total_seconds // 60))
        return f"{minutes} {'minuto' if minutes == 1 else 'minutos'}"


def get_expiry_emoji(end_date: datetime) -> str:
    """
    Retorna emoji de urgência baseado no tempo restante.

    Returns:
        '❌' expirado, '🔴' <= 3 dias, '🟡' <= 7 dias, '🟢' > 7 dias
    """
    if not end_date:
        return "❌"

    total_hours = (end_date - datetime.utcnow()).total_seconds() / 3600

    if total_hours <= 0:
        return "❌"
    elif total_hours <= 72:  # 3 days
        return "🔴"
    elif total_hours <= 168:  # 7 days
        return "🟡"
    else:
        return "🟢"


def format_time_remaining(end_date: datetime) -> str:
    """
    Formatar tempo restante com emoji (compatibilidade).
    """
    emoji = get_expiry_emoji(end_date)
    text = format_remaining_text(end_date)
    if text == "Expirado":
        return f"❌ {text}"
    return f"{emoji} {text} restantes"


def escape_markdown(text: str) -> str:
    """
    Escapar caracteres especiais do Markdown do Telegram
    
    Args:
        text: Texto a ser escapado
        
    Returns:
        Texto com caracteres escapados
    """
    if not text:
        return ""
    
    # Caracteres que precisam ser escapados
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def escape_html(text: str) -> str:
    """Escapar caracteres especiais para HTML do Telegram"""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_currency_code(value) -> str:
    """Formatar valor monetário dentro de <code> para Telegram HTML"""
    return f"<code>{format_currency(value)}</code>"


def format_date_code(date: datetime, include_time: bool = False) -> str:
    """Formatar data dentro de <code> para Telegram HTML"""
    return f"<code>{format_date(date, include_time)}</code>"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncar texto longo
    
    Args:
        text: Texto a ser truncado
        max_length: Tamanho máximo
        suffix: Sufixo a adicionar se truncado
        
    Returns:
        Texto truncado
    """
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix