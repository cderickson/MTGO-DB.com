import argparse
import os
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def get_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def copy_table(source_engine: Engine, target_engine: Engine, table: Table) -> int:
    rows_copied = 0
    with source_engine.connect() as src_conn, target_engine.begin() as tgt_conn:
        result = src_conn.execute(select(table))
        rows = [dict(row._mapping) for row in result]
        if rows:
            tgt_conn.execute(table.insert(), rows)
            rows_copied = len(rows)
    return rows_copied


def main():
    parser = argparse.ArgumentParser(description="Migrate data from SQLite to Postgres using SQLAlchemy models.")
    parser.add_argument("--sqlite-path", required=True, help="Path to the local SQLite .db file")
    parser.add_argument(
        "--postgres-url",
        default=os.environ.get("SQLALCHEMY_DATABASE_URI"),
        help="Target Postgres SQLAlchemy URL. If omitted, falls back to SQLALCHEMY_DATABASE_URI env var.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.sqlite_path):
        raise SystemExit(f"SQLite file not found: {args.sqlite_path}")
    if not args.postgres_url:
        raise SystemExit("Provide --postgres-url or set SQLALCHEMY_DATABASE_URI env var")

    # Import models to populate metadata
    from modules.extensions import db  # noqa: F401
    import modules.models  # noqa: F401

    metadata: MetaData = db.metadata

    sqlite_url = f"sqlite:///{os.path.abspath(args.sqlite_path)}"
    src_engine = get_engine(sqlite_url)
    tgt_engine = get_engine(args.postgres_url)

    # Ensure target schema exists
    metadata.create_all(tgt_engine)

    total = 0
    for table_name in metadata.tables:
        table = metadata.tables[table_name]
        copied = copy_table(src_engine, tgt_engine, table)
        print(f"Copied {copied:6d} rows -> {table_name}")
        total += copied

    print(f"Done. Total rows copied: {total}")


if __name__ == "__main__":
    main()


