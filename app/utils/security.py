import os
import jwt
import hmac
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from flask import current_app, request
from functools import wraps


def _get_secret_key() -> str:
    """
    Obter SECRET_KEY do contexto da aplicação Flask ou do ambiente.
    Raises RuntimeError se nenhuma chave estiver disponível.
    """
    try:
        key = current_app.config['SECRET_KEY']
        if key:
            return key
    except RuntimeError:
        pass  # Fora do contexto Flask (ex: bot)

    key = os.getenv('SECRET_KEY')
    if key:
        return key

    raise RuntimeError('SECRET_KEY não configurada. Defina a variável de ambiente SECRET_KEY.')

def generate_reset_token(user_id: int, password_hash: str = None, expires_in: int = 86400) -> str:
    """
    Gerar token JWT para reset de senha.
    Includes password_hash prefix so token auto-invalidates when password changes.

    Args:
        user_id: ID do usuário
        password_hash: Current password hash (first 8 chars embedded in token)
        expires_in: Tempo de expiração em segundos (padrão: 24 horas)

    Returns:
        Token JWT
    """
    secret_key = _get_secret_key()

    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow(),
        'purpose': 'password_reset'
    }

    # Embed password hash prefix for single-use enforcement
    if password_hash:
        payload['phash'] = password_hash[:16]

    token = jwt.encode(
        payload,
        secret_key,
        algorithm='HS256'
    )

    return token

def verify_reset_token(token: str, current_password_hash: str = None) -> Optional[int]:
    """
    Verificar e decodificar token de reset.
    If current_password_hash is provided, verifies token hasn't been used
    (password hasn't changed since token was issued).

    Args:
        token: Token JWT
        current_password_hash: Current password hash to verify against

    Returns:
        user_id se válido, None se inválido/expirado
    """
    secret_key = _get_secret_key()

    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=['HS256']
        )

        # Verificar se é token de reset
        if payload.get('purpose') != 'password_reset':
            return None

        # Verify password hash hasn't changed (token reuse prevention)
        token_phash = payload.get('phash')
        if token_phash and current_password_hash:
            # Support both old 8-char and new 16-char tokens
            prefix_len = len(token_phash)
            if current_password_hash[:prefix_len] != token_phash:
                return None

        return payload.get('user_id')

    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
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
    secret_key = _get_secret_key()
    
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

def verify_confirmation_token(token: str) -> Optional[str]:
    """
    Verificar token de confirmação de email
    
    Args:
        token: Token JWT
    
    Returns:
        email se válido, None se inválido/expirado
    """
    secret_key = _get_secret_key()
    
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=['HS256']
        )
        
        # Verificar se é token de confirmação
        if payload.get('purpose') != 'email_confirmation':
            return None
            
        return payload.get('email')
        
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None

def generate_api_token(user_id: int, expires_in: int = 2592000) -> str:
    """
    Gerar token de API para autenticação
    
    Args:
        user_id: ID do usuário
        expires_in: Tempo de expiração em segundos (padrão: 30 dias)
    
    Returns:
        Token JWT
    """
    secret_key = _get_secret_key()
    
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow(),
        'purpose': 'api_access'
    }
    
    token = jwt.encode(
        payload,
        secret_key,
        algorithm='HS256'
    )
    
    return token

def verify_api_token(token: str) -> Optional[int]:
    """
    Verificar token de API
    
    Args:
        token: Token JWT
    
    Returns:
        user_id se válido, None se inválido/expirado
    """
    secret_key = _get_secret_key()
    
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=['HS256']
        )
        
        # Verificar se é token de API
        if payload.get('purpose') != 'api_access':
            return None
            
        return payload.get('user_id')
        
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None

def generate_secure_token(length: int = 32) -> str:
    """
    Gerar token aleatório seguro
    
    Args:
        length: Tamanho do token em bytes
    
    Returns:
        Token hexadecimal
    """
    return secrets.token_hex(length)

def generate_webhook_signature(payload: bytes, secret: str) -> str:
    """
    Gerar assinatura HMAC para webhooks
    
    Args:
        payload: Dados do webhook
        secret: Chave secreta
    
    Returns:
        Assinatura HMAC
    """
    return hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verificar assinatura de webhook
    
    Args:
        payload: Dados recebidos
        signature: Assinatura recebida
        secret: Chave secreta
    
    Returns:
        True se válido, False caso contrário
    """
    expected_signature = generate_webhook_signature(payload, secret)
    return secrets.compare_digest(signature, expected_signature)

def hash_password(password: str) -> str:
    """
    Hash de senha usando bcrypt
    
    Args:
        password: Senha em texto plano
    
    Returns:
        Hash da senha
    """
    import bcrypt
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """
    Verificar senha contra hash
    
    Args:
        password: Senha em texto plano
        password_hash: Hash armazenado
    
    Returns:
        True se corresponde, False caso contrário
    """
    import bcrypt
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2MB

# Magic bytes for image formats
_IMAGE_SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': 'png',
    b'\xff\xd8\xff': 'jpg',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
}


def validate_and_sanitize_image(file, max_size=MAX_IMAGE_SIZE):
    """
    Validate uploaded image file for security:
    1. Check extension is allowed
    2. Check file size
    3. Verify magic bytes match claimed extension
    4. Re-process with Pillow to strip metadata and validate pixel data
    5. Return sanitized image bytes

    Args:
        file: werkzeug FileStorage object
        max_size: Maximum file size in bytes

    Returns:
        (sanitized_bytes, extension) tuple on success

    Raises:
        ValueError with user-friendly message on any validation failure
    """
    from PIL import Image
    import io

    if not file or file.filename == '':
        raise ValueError('Nenhum arquivo selecionado.')

    # 1. Extension check
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError('Formato inválido. Use PNG, JPG ou GIF.')

    # Normalize jpg/jpeg
    if ext == 'jpeg':
        ext = 'jpg'

    # 2. Size check
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > max_size:
        raise ValueError(f'Arquivo muito grande. Máximo {max_size // (1024*1024)}MB.')
    if size < 100:
        raise ValueError('Arquivo muito pequeno ou corrompido.')

    # 3. Magic byte validation
    header = file.read(16)
    file.seek(0)
    magic_match = False
    detected_type = None
    for signature, sig_type in _IMAGE_SIGNATURES.items():
        if header.startswith(signature):
            magic_match = True
            detected_type = sig_type
            break

    if not magic_match:
        raise ValueError('Arquivo não é uma imagem válida.')

    # Cross-check: detected type must match extension
    ext_normalized = 'jpg' if ext in ('jpg', 'jpeg') else ext
    detected_normalized = 'jpg' if detected_type in ('jpg', 'jpeg') else detected_type
    if ext_normalized != detected_normalized:
        raise ValueError('Extensão não corresponde ao conteúdo do arquivo.')

    # 4. Re-process with Pillow (strips EXIF, validates pixel data, prevents polyglot files)
    try:
        img = Image.open(file)
        img.verify()  # Check for corruption
        file.seek(0)
        img = Image.open(file)  # Re-open after verify

        # Limit dimensions to prevent decompression bombs
        max_dimension = 4096
        if img.width > max_dimension or img.height > max_dimension:
            raise ValueError(f'Dimensões muito grandes. Máximo {max_dimension}x{max_dimension}px.')

        # Re-save to clean buffer (strips metadata, prevents embedded scripts)
        output = io.BytesIO()
        save_format = 'PNG' if ext == 'png' else ('GIF' if ext == 'gif' else 'JPEG')

        # Convert RGBA to RGB for JPEG (JPEG doesn't support alpha)
        if save_format == 'JPEG' and img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')

        img.save(output, format=save_format, quality=90)
        output.seek(0)
        return output.read(), ext

    except ValueError:
        raise  # Re-raise our own ValueErrors
    except Exception:
        raise ValueError('Arquivo de imagem corrompido ou inválido.')


def sanitize_filename(filename: str) -> str:
    """
    Sanitizar nome de arquivo para upload seguro
    
    Args:
        filename: Nome original do arquivo
    
    Returns:
        Nome sanitizado
    """
    import re
    # Remove caracteres perigosos
    filename = re.sub(r'[^\w\s\-\.]', '', filename)
    # Remove espaços múltiplos
    filename = re.sub(r'\s+', '-', filename)
    # Limita tamanho
    name, ext = os.path.splitext(filename)
    if len(name) > 50:
        name = name[:50]
    return f"{name}{ext}".lower()

def rate_limit_key(identifier: str) -> str:
    """
    Gerar chave para rate limiting
    
    Args:
        identifier: IP ou user_id
    
    Returns:
        Chave formatada
    """
    return f"rate_limit:{identifier}"

def generate_csrf_token() -> str:
    """
    Gerar token CSRF
    
    Returns:
        Token CSRF
    """
    return secrets.token_urlsafe(32)

def verify_csrf_token(token: str, session_token: str) -> bool:
    """
    Verificar token CSRF
    
    Args:
        token: Token recebido
        session_token: Token da sessão
    
    Returns:
        True se válido
    """
    return secrets.compare_digest(token, session_token)

_LEGACY_SALT = b'televip-salt'


def _derive_fernet_key(secret: str, salt: bytes = _LEGACY_SALT) -> bytes:
    """Derive a proper Fernet key from a secret using PBKDF2."""
    import base64
    key_bytes = hashlib.pbkdf2_hmac(
        'sha256', secret.encode('utf-8'), salt, 100000
    )
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_data(data: str, key: Optional[str] = None) -> str:
    """
    Criptografar dados sensíveis com salt aleatório por valor.

    Formato: salt_hex$ciphertext

    Args:
        data: Dados para criptografar
        key: Chave de criptografia (usa SECRET_KEY se não fornecida)

    Returns:
        Dados criptografados no formato salt_hex$ciphertext
    """
    from cryptography.fernet import Fernet

    if not key:
        key = _get_secret_key()

    salt = os.urandom(16)
    fernet_key = _derive_fernet_key(key, salt)
    fernet = Fernet(fernet_key)
    encrypted = fernet.encrypt(data.encode('utf-8'))

    return salt.hex() + '$' + encrypted.decode('utf-8')

def decrypt_data(encrypted_data: str, key: Optional[str] = None) -> Optional[str]:
    """
    Descriptografar dados. Suporta formato novo (salt$ciphertext) e legado.

    Args:
        encrypted_data: Dados criptografados
        key: Chave de descriptografia

    Returns:
        Dados descriptografados ou None se falhar
    """
    from cryptography.fernet import Fernet, InvalidToken

    if not key:
        key = _get_secret_key()

    try:
        # Novo formato: salt_hex$ciphertext
        if '$' in encrypted_data:
            salt_hex, ciphertext = encrypted_data.split('$', 1)
            salt = bytes.fromhex(salt_hex)
            fernet_key = _derive_fernet_key(key, salt)
            fernet = Fernet(fernet_key)
            return fernet.decrypt(ciphertext.encode('utf-8')).decode('utf-8')

        # Formato legado: salt fixo
        fernet_key = _derive_fernet_key(key, _LEGACY_SALT)
        fernet = Fernet(fernet_key)
        return fernet.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError, Exception):
        return None

def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """
    Mascarar dados sensíveis (ex: tokens, cartões)
    
    Args:
        data: Dados para mascarar
        visible_chars: Número de caracteres visíveis no final
    
    Returns:
        Dados mascarados
    """
    if len(data) <= visible_chars:
        return '*' * len(data)
    
    masked_length = len(data) - visible_chars
    return '*' * masked_length + data[-visible_chars:]

def is_safe_url(target: str) -> bool:
    """
    Verificar se URL é segura para redirecionamento
    
    Args:
        target: URL alvo
    
    Returns:
        True se segura
    """
    from urllib.parse import urlparse, urljoin
    
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    
    return (test_url.scheme in ('http', 'https') and 
            ref_url.netloc == test_url.netloc)

def require_api_key(f):
    """
    Decorator para exigir API key válida
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return {'error': 'API key required'}, 401
        
        # Verificar API key no banco ou cache
        # Exemplo simplificado:
        valid_keys = os.getenv('VALID_API_KEYS', '').split(',')
        if api_key not in valid_keys:
            return {'error': 'Invalid API key'}, 401
        
        return f(*args, **kwargs)
    return decorated_function

# Funções auxiliares para JWT
def decode_token(token: str, purpose: str = None) -> Optional[Dict[Any, Any]]:
    """
    Decodificar token JWT genérico
    
    Args:
        token: Token JWT
        purpose: Propósito esperado (opcional)
    
    Returns:
        Payload se válido, None caso contrário
    """
    secret_key = _get_secret_key()
    
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=['HS256']
        )
        
        # Verificar propósito se fornecido
        if purpose and payload.get('purpose') != purpose:
            return None
            
        return payload
        
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
        return None

def create_token(payload: Dict[Any, Any], expires_in: int = 3600) -> str:
    """
    Criar token JWT genérico
    
    Args:
        payload: Dados do token
        expires_in: Tempo de expiração em segundos
    
    Returns:
        Token JWT
    """
    secret_key = _get_secret_key()
    
    # Adicionar timestamps
    payload['iat'] = datetime.utcnow()
    payload['exp'] = datetime.utcnow() + timedelta(seconds=expires_in)
    
    return jwt.encode(
        payload,
        secret_key,
        algorithm='HS256'
    )