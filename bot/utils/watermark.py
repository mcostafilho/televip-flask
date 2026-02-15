"""
Marca d'água invisível usando caracteres Unicode zero-width.
Permite identificar vazadores ao embalar o ID do assinante no texto.
"""

# Caracteres invisíveis usados como "bits"
ZWS = '\u200b'   # zero-width space        = 0
ZWNJ = '\u200c'  # zero-width non-joiner   = 1
ZWJ = '\u200d'   # zero-width joiner       = separador/delimitador


def encode_watermark(subscriber_id: int) -> str:
    """Converte subscriber_id em sequência invisível de zero-width chars."""
    binary = bin(subscriber_id)[2:]  # ex: "1101"
    chars = ZWJ  # marcador de início
    for bit in binary:
        chars += ZWNJ if bit == '1' else ZWS
    chars += ZWJ  # marcador de fim
    return chars


def watermark_text(text: str, subscriber_id: int) -> str:
    """Insere marca d'água invisível no texto após a primeira palavra."""
    wm = encode_watermark(subscriber_id)
    parts = text.split(' ', 1)
    if len(parts) == 2:
        return parts[0] + wm + ' ' + parts[1]
    return text + wm


def decode_watermark(text: str) -> int | None:
    """Extrai subscriber_id do texto com marca d'água. Retorna None se não encontrar."""
    start = text.find(ZWJ)
    if start == -1:
        return None
    end = text.find(ZWJ, start + 1)
    if end == -1:
        return None
    sequence = text[start + 1:end]
    binary = ''
    for ch in sequence:
        if ch == ZWNJ:
            binary += '1'
        elif ch == ZWS:
            binary += '0'
    if not binary:
        return None
    return int(binary, 2)
