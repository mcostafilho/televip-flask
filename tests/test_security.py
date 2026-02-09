# tests/test_security.py
"""
Testes das funções de segurança
"""
import pytest
import time
from app.utils.security import (
    generate_reset_token, verify_reset_token,
    generate_confirmation_token, verify_confirmation_token,
    generate_api_token, verify_api_token,
    generate_secure_token, generate_webhook_signature,
    verify_webhook_signature, sanitize_filename,
    rate_limit_key, generate_csrf_token, verify_csrf_token,
    encrypt_data, decrypt_data, mask_sensitive_data,
    is_safe_url, create_token, decode_token,
    hash_password, verify_password,
)


class TestResetToken:
    """Testes de token de reset de senha"""

    def test_generate_and_verify(self, app_context):
        token = generate_reset_token(42)
        assert token is not None
        assert isinstance(token, str)
        user_id = verify_reset_token(token)
        assert user_id == 42

    def test_expired_token(self, app_context):
        token = generate_reset_token(42, expires_in=0)
        time.sleep(1)
        assert verify_reset_token(token) is None

    def test_invalid_token(self, app_context):
        assert verify_reset_token('invalid.token.here') is None

    def test_empty_token(self, app_context):
        assert verify_reset_token('') is None

    def test_different_user_ids(self, app_context):
        token1 = generate_reset_token(1)
        token2 = generate_reset_token(2)
        assert verify_reset_token(token1) == 1
        assert verify_reset_token(token2) == 2
        assert token1 != token2

    def test_wrong_purpose_token(self, app_context):
        """Token de confirmação não deve funcionar como reset"""
        token = generate_confirmation_token('test@test.com')
        assert verify_reset_token(token) is None


class TestConfirmationToken:
    """Testes de token de confirmação de email"""

    def test_generate_and_verify(self, app_context):
        token = generate_confirmation_token('user@test.com')
        assert token is not None
        email = verify_confirmation_token(token)
        assert email == 'user@test.com'

    def test_expired_token(self, app_context):
        token = generate_confirmation_token('user@test.com', expires_in=0)
        time.sleep(1)
        assert verify_confirmation_token(token) is None

    def test_invalid_token(self, app_context):
        assert verify_confirmation_token('garbage') is None

    def test_wrong_purpose(self, app_context):
        """Token de reset não deve funcionar como confirmação"""
        token = generate_reset_token(1)
        assert verify_confirmation_token(token) is None


class TestApiToken:
    """Testes de token de API"""

    def test_generate_and_verify(self, app_context):
        token = generate_api_token(10)
        assert token is not None
        user_id = verify_api_token(token)
        assert user_id == 10

    def test_expired_token(self, app_context):
        token = generate_api_token(10, expires_in=0)
        time.sleep(1)
        assert verify_api_token(token) is None

    def test_invalid_token(self, app_context):
        assert verify_api_token('bad_token') is None

    def test_wrong_purpose(self, app_context):
        token = generate_reset_token(10)
        assert verify_api_token(token) is None


class TestGenericToken:
    """Testes de create_token e decode_token"""

    def test_create_and_decode(self, app_context):
        token = create_token({'action': 'test', 'data': 123})
        payload = decode_token(token)
        assert payload is not None
        assert payload['action'] == 'test'
        assert payload['data'] == 123

    def test_decode_with_purpose_match(self, app_context):
        token = create_token({'purpose': 'custom', 'val': 1})
        payload = decode_token(token, purpose='custom')
        assert payload is not None
        assert payload['val'] == 1

    def test_decode_with_purpose_mismatch(self, app_context):
        token = create_token({'purpose': 'custom', 'val': 1})
        assert decode_token(token, purpose='other') is None

    def test_expired_generic_token(self, app_context):
        token = create_token({'data': 1}, expires_in=0)
        time.sleep(1)
        assert decode_token(token) is None


class TestSecureToken:
    """Testes de geração de token aleatório"""

    def test_default_length(self, app_context):
        token = generate_secure_token()
        assert len(token) == 64  # 32 bytes = 64 hex chars

    def test_custom_length(self, app_context):
        token = generate_secure_token(16)
        assert len(token) == 32  # 16 bytes = 32 hex chars

    def test_uniqueness(self, app_context):
        tokens = set(generate_secure_token() for _ in range(100))
        assert len(tokens) == 100  # Todos devem ser únicos


class TestWebhookSignature:
    """Testes de assinatura HMAC para webhooks"""

    def test_generate_signature(self, app_context):
        sig = generate_webhook_signature(b'payload data', 'secret123')
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex digest

    def test_verify_valid_signature(self, app_context):
        payload = b'test payload'
        secret = 'my-secret'
        sig = generate_webhook_signature(payload, secret)
        assert verify_webhook_signature(payload, sig, secret) is True

    def test_verify_invalid_signature(self, app_context):
        payload = b'test payload'
        assert verify_webhook_signature(payload, 'wrong_sig', 'secret') is False

    def test_verify_tampered_payload(self, app_context):
        secret = 'my-secret'
        sig = generate_webhook_signature(b'original', secret)
        assert verify_webhook_signature(b'tampered', sig, secret) is False

    def test_different_secrets_different_signatures(self, app_context):
        payload = b'same payload'
        sig1 = generate_webhook_signature(payload, 'secret1')
        sig2 = generate_webhook_signature(payload, 'secret2')
        assert sig1 != sig2

    def test_consistent_signature(self, app_context):
        payload = b'data'
        secret = 'key'
        sig1 = generate_webhook_signature(payload, secret)
        sig2 = generate_webhook_signature(payload, secret)
        assert sig1 == sig2


class TestPasswordHashing:
    """Testes de hash de senha com bcrypt"""

    def test_hash_password(self, app_context):
        hashed = hash_password('MyPassword123')
        assert hashed is not None
        assert hashed != 'MyPassword123'

    def test_verify_correct_password(self, app_context):
        hashed = hash_password('MyPassword123')
        assert verify_password('MyPassword123', hashed) is True

    def test_verify_wrong_password(self, app_context):
        hashed = hash_password('MyPassword123')
        assert verify_password('WrongPassword', hashed) is False

    def test_different_hashes_same_password(self, app_context):
        h1 = hash_password('Same123')
        h2 = hash_password('Same123')
        assert h1 != h2  # bcrypt usa salt diferente

    def test_verify_both_hashes(self, app_context):
        h1 = hash_password('Same123')
        h2 = hash_password('Same123')
        assert verify_password('Same123', h1) is True
        assert verify_password('Same123', h2) is True


class TestEncryption:
    """Testes de criptografia Fernet"""

    def test_encrypt_decrypt(self, app_context):
        original = 'sensitive data 12345'
        encrypted = encrypt_data(original)
        assert encrypted != original
        decrypted = decrypt_data(encrypted)
        assert decrypted == original

    def test_decrypt_invalid_data(self, app_context):
        result = decrypt_data('not-valid-encrypted-data')
        assert result is None

    def test_encrypt_empty_string(self, app_context):
        encrypted = encrypt_data('')
        decrypted = decrypt_data(encrypted)
        assert decrypted == ''

    def test_encrypt_unicode(self, app_context):
        original = 'Dados sensíveis com acentuação ñ ü'
        encrypted = encrypt_data(original)
        decrypted = decrypt_data(encrypted)
        assert decrypted == original

    def test_encrypt_with_custom_key(self, app_context):
        key = 'custom-key-for-encryption-test!'
        encrypted = encrypt_data('data', key=key)
        decrypted = decrypt_data(encrypted, key=key)
        assert decrypted == 'data'

    def test_decrypt_with_wrong_key(self, app_context):
        encrypted = encrypt_data('data', key='correct-key-1234567890123!')
        result = decrypt_data(encrypted, key='wrong-key-12345678901234!')
        assert result is None


class TestSanitizeFilename:
    """Testes de sanitização de nomes de arquivo"""

    def test_normal_filename(self, app_context):
        assert sanitize_filename('photo.jpg') == 'photo.jpg'

    def test_special_characters(self, app_context):
        result = sanitize_filename('file<>:"|?*.jpg')
        assert '<' not in result
        assert '>' not in result
        assert ':' not in result
        assert '"' not in result
        assert '|' not in result
        assert '?' not in result
        assert '*' not in result

    def test_spaces_replaced(self, app_context):
        result = sanitize_filename('my photo file.jpg')
        assert ' ' not in result
        assert '-' in result

    def test_long_filename_truncated(self, app_context):
        long_name = 'a' * 100 + '.jpg'
        result = sanitize_filename(long_name)
        name, ext = result.rsplit('.', 1)
        assert len(name) <= 50

    def test_lowercase(self, app_context):
        assert sanitize_filename('PHOTO.JPG') == 'photo.jpg'

    def test_path_traversal(self, app_context):
        result = sanitize_filename('../../etc/passwd')
        # Should remove dangerous path components
        assert '/' not in result


class TestCsrfToken:
    """Testes de token CSRF"""

    def test_generate_csrf_token(self, app_context):
        token = generate_csrf_token()
        assert token is not None
        assert len(token) > 20

    def test_verify_csrf_match(self, app_context):
        token = generate_csrf_token()
        assert verify_csrf_token(token, token) is True

    def test_verify_csrf_mismatch(self, app_context):
        assert verify_csrf_token('token1', 'token2') is False

    def test_csrf_uniqueness(self, app_context):
        tokens = set(generate_csrf_token() for _ in range(50))
        assert len(tokens) == 50


class TestMaskSensitiveData:
    """Testes de mascaramento de dados"""

    def test_mask_card_number(self, app_context):
        result = mask_sensitive_data('4111111111111111')
        assert result.endswith('1111')
        assert result.startswith('****')

    def test_mask_short_data(self, app_context):
        result = mask_sensitive_data('abc')
        assert result == '***'

    def test_mask_custom_visible(self, app_context):
        result = mask_sensitive_data('1234567890', visible_chars=2)
        assert result.endswith('90')
        assert len(result) == 10

    def test_mask_equal_to_visible(self, app_context):
        result = mask_sensitive_data('abcd', visible_chars=4)
        # When visible_chars == len(data), no masking needed
        assert len(result) == 4


class TestIsSafeUrl:
    """Testes de validação de URL segura"""

    def test_relative_url_safe(self, app_context):
        with app_context.test_request_context('/'):
            assert is_safe_url('/dashboard') is True

    def test_absolute_same_host_safe(self, app_context):
        with app_context.test_request_context('/'):
            assert is_safe_url('http://localhost/dashboard') is True

    def test_external_url_unsafe(self, app_context):
        with app_context.test_request_context('/'):
            assert is_safe_url('https://evil.com/steal') is False

    def test_javascript_url_unsafe(self, app_context):
        with app_context.test_request_context('/'):
            result = is_safe_url('javascript:alert(1)')
            assert result is False

    def test_empty_url(self, app_context):
        with app_context.test_request_context('/'):
            # Empty URL resolves to same host
            result = is_safe_url('')
            assert result is True


class TestRateLimitKey:
    """Testes de formatação de chave rate limit"""

    def test_format_ip(self):
        assert rate_limit_key('192.168.1.1') == 'rate_limit:192.168.1.1'

    def test_format_user_id(self):
        assert rate_limit_key('user_42') == 'rate_limit:user_42'
