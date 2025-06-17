"""
Corrigir indentação definitivamente
"""

# Ler arquivo
with open('bot/handlers/start.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("Corrigindo indentação...")

# Fazer backup
with open('bot/handlers/start.py.backup_final', 'w', encoding='utf-8') as f:
    f.writelines(lines)

# Corrigir linha 73 (índice 72) - adicionar indentação ao comentário
if len(lines) > 72:
    # A linha 73 precisa estar indentada
    if not lines[72].startswith('            '):
        lines[72] = '                ' + lines[72].lstrip()
        print("Linha 73 indentada")

# Verificar e mostrar resultado
print("\nLinhas 72-76 após correção:")
for i in range(71, min(76, len(lines))):
    print(f"{i+1}: {repr(lines[i])}")

# Salvar
with open('bot/handlers/start.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("\n✅ Arquivo corrigido!")