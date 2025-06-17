"""
Utilitários de formatação para o bot
"""
from typing import Union
from datetime import datetime, timedelta


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
    Formatar data para padrão brasileiro
    
    Args:
        date: Data a ser formatada
        include_time: Se deve incluir horário
        
    Returns:
        String formatada (ex: 17/06/2025 ou 17/06/2025 14:30)
    """
    if not date:
        return "N/A"
    
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


def format_time_remaining(end_date: datetime) -> str:
    """
    Formatar tempo restante até uma data
    
    Args:
        end_date: Data final
        
    Returns:
        String formatada (ex: 15 dias restantes, Expira hoje, Expirado)
    """
    if not end_date:
        return "N/A"
    
    now = datetime.utcnow()
    delta = end_date - now
    
    if delta.days < 0:
        return "❌ Expirado"
    elif delta.days == 0:
        if delta.seconds > 0:
            hours = delta.seconds // 3600
            if hours > 0:
                return f"⏰ Expira em {hours} {'hora' if hours == 1 else 'horas'}"
            else:
                return "⏰ Expira hoje"
        else:
            return "❌ Expirado"
    elif delta.days == 1:
        return "⏰ Expira amanhã"
    elif delta.days <= 7:
        return f"⏰ {delta.days} dias restantes"
    elif delta.days <= 30:
        weeks = delta.days // 7
        return f"📅 {weeks} {'semana' if weeks == 1 else 'semanas'} restantes"
    else:
        months = delta.days // 30
        if months == 1:
            return "📅 1 mês restante"
        else:
            return f"📅 {months} meses restantes"


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