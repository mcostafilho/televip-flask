"""
migrate_data.py - Migração de dados SQLite → PostgreSQL
Script de uso único para copiar dados do SQLite para Cloud SQL PostgreSQL.

Uso:
    DATABASE_URL=postgresql://televip:SENHA@IP/televip python migrate_data.py /opt/televip/instance/app.db
"""
import sys
import os
from sqlalchemy import create_engine, MetaData, text, inspect

# Ordem respeitando foreign keys (tabelas pai primeiro)
TABLES_ORDER = [
    'alembic_version',
    'creators',
    'groups',
    'pricing_plans',
    'subscriptions',
    'transactions',
    'withdrawals',
    'reports',
]


def migrate(sqlite_path, pg_url):
    """Copia todas as tabelas do SQLite para PostgreSQL."""
    if not os.path.exists(sqlite_path):
        print(f"ERRO: arquivo SQLite não encontrado: {sqlite_path}")
        sys.exit(1)

    sqlite_url = f'sqlite:///{os.path.abspath(sqlite_path)}'
    sqlite_engine = create_engine(sqlite_url)
    pg_engine = create_engine(pg_url)

    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    pg_inspector = inspect(pg_engine)
    pg_tables = pg_inspector.get_table_names()

    # Descobrir tabelas disponíveis no SQLite
    sqlite_tables = sqlite_meta.tables.keys()
    tables_to_migrate = [t for t in TABLES_ORDER if t in sqlite_tables and t in pg_tables]

    # Tabelas no SQLite que não estão na lista (segurança)
    extra = set(sqlite_tables) - set(TABLES_ORDER)
    if extra:
        print(f"AVISO: tabelas no SQLite ignoradas (não listadas): {extra}")

    missing_pg = [t for t in TABLES_ORDER if t in sqlite_tables and t not in pg_tables]
    if missing_pg:
        print(f"ERRO: tabelas existem no SQLite mas não no PostgreSQL: {missing_pg}")
        print("Execute 'flask db upgrade' antes de rodar este script.")
        sys.exit(1)

    total_rows = 0

    with sqlite_engine.connect() as sqlite_conn, pg_engine.connect() as pg_conn:
        for table_name in tables_to_migrate:
            # Ler dados do SQLite
            rows = sqlite_conn.execute(text(f'SELECT * FROM "{table_name}"')).fetchall()
            if not rows:
                print(f"  {table_name}: 0 linhas (vazia)")
                continue

            # Pegar nomes das colunas
            columns = sqlite_conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT 1')).keys()
            col_names = list(columns)

            # Filtrar colunas que existem no PostgreSQL
            pg_columns = [c['name'] for c in pg_inspector.get_columns(table_name)]
            valid_cols = [c for c in col_names if c in pg_columns]

            if not valid_cols:
                print(f"  {table_name}: SKIP (sem colunas em comum)")
                continue

            # Limpar tabela destino (caso re-execute)
            pg_conn.execute(text(f'DELETE FROM "{table_name}"'))

            # Inserir em lotes
            placeholders = ', '.join(f':{c}' for c in valid_cols)
            col_list = ', '.join(f'"{c}"' for c in valid_cols)
            insert_sql = text(f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})')

            batch = []
            for row in rows:
                row_dict = dict(zip(col_names, row))
                # Somente colunas válidas
                filtered = {c: row_dict[c] for c in valid_cols}
                batch.append(filtered)

                if len(batch) >= 500:
                    pg_conn.execute(insert_sql, batch)
                    batch = []

            if batch:
                pg_conn.execute(insert_sql, batch)

            total_rows += len(rows)
            print(f"  {table_name}: {len(rows)} linhas migradas")

        # Reset sequences do PostgreSQL (auto-increment)
        print("\nResetando sequences...")
        for table_name in tables_to_migrate:
            if table_name == 'alembic_version':
                continue
            # Verificar se a tabela tem coluna 'id'
            pg_columns = [c['name'] for c in pg_inspector.get_columns(table_name)]
            if 'id' not in pg_columns:
                continue

            result = pg_conn.execute(text(f'SELECT MAX(id) FROM "{table_name}"')).scalar()
            if result is not None:
                seq_name = f'{table_name}_id_seq'
                pg_conn.execute(text(f"SELECT setval('{seq_name}', :val)"), {'val': result})
                print(f"  {seq_name} → {result}")

        pg_conn.commit()

    print(f"\nMigração concluída! {total_rows} linhas migradas no total.")


if __name__ == '__main__':
    pg_url = os.getenv('DATABASE_URL')
    if not pg_url or not pg_url.startswith('postgresql'):
        print("ERRO: DATABASE_URL deve ser uma URL PostgreSQL.")
        print("Uso: DATABASE_URL=postgresql://user:pass@host/db python migrate_data.py <sqlite_path>")
        sys.exit(1)

    if len(sys.argv) < 2:
        sqlite_path = '/opt/televip/instance/app.db'
        print(f"Nenhum caminho informado, usando padrão: {sqlite_path}")
    else:
        sqlite_path = sys.argv[1]

    print(f"SQLite: {sqlite_path}")
    print(f"PostgreSQL: {pg_url.split('@')[0].rsplit(':', 1)[0]}@***")
    print()

    confirm = input("Continuar com a migração? (s/n): ").strip().lower()
    if confirm != 's':
        print("Cancelado.")
        sys.exit(0)

    print()
    migrate(sqlite_path, pg_url)
