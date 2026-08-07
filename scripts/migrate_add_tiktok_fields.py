import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "app" / "kidstube.db"


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return column in [row[1] for row in rows]


def main() -> None:
    if not DB_PATH.exists():
        print(f"Pas de base à migrer ({DB_PATH} n'existe pas encore) — rien à faire.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        if column_exists(conn, "idea", "tiktok_publish_id"):
            print("idea.tiktok_publish_id existe déjà — rien à faire.")
            return
        conn.execute("ALTER TABLE idea ADD COLUMN tiktok_publish_id VARCHAR(128)")
        conn.execute("ALTER TABLE idea ADD COLUMN tiktok_published_at DATETIME")
        conn.commit()
        print("Colonnes idea.tiktok_publish_id et idea.tiktok_published_at ajoutées.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
