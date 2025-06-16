import os
import jwt
from datetime import datetime, timedelta
from flask import current_app

def generate_reset_token(user_id: int, expires_in: int = 86400) -> str:
    """
    Gerar token JWT para reset de senha
    
    Args:
        user_id: ID do usuário
        expires_in: Tempo de expiração em segundos (padrão: 24 horas)
    
    Returns:
        Token JWT
    """
    secret_key = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow(),
        'purpose': 'password_reset'
    }
    
    token = jwt.encode(
        payload,
        secret_key,
        algorithm='HS256'
    )
    
    return token

def verify_reset_token(token: str) -> int:
    """
    Verificar e decodificar token de reset
    
    Args:
        token: Token JWT
    
    Returns:
        user_id se válido, None se inválido/expirado
    """
    secret_key = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=['HS256']
        )
        
        # Verificar se é token de reset
        if payload.get('purpose') != 'password_reset':
            return None
            
        return payload.get('user_id')
        
    except jwt.ExpiredSignatureError:
        # Token expirado
        return None
    except jwt.InvalidTokenError:
        # Token inválido
        return None
    except Exception:
        # Qualquer outro erro
        return None

def generate_confirmation_token(email: str, expires_in: int = 86400) -> str:
    """
    Gerar token para confirmação de email
    
    Args:
        email: Email a ser confirmado
        expires_in: Tempo de expiração em segundos
    
    Returns:
        Token JWT
    """
    secret_key = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    
    payload = {
        'email': email,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow(),
        'purpose': 'email_confirmation'
    }
    
    token = jwt.encode(
        payload,
        secret_key,
        algorithm='HS256'
    )
    
    return token

def verify_confirmation_token(token: str) -> str:
    """
    Verificar token de confirmação de email
    
    Args:
        token: Token JWT
    
    Returns:
        email se válido, None se inválido/expirado
    """
    secret_key = os.getenv('SECRET_KEY', 'dev-key-change-