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
        if column_exists(conn, "idea", "video_pipeline"):
            print("idea.video_pipeline existe déjà — rien à faire.")
            return
        conn.execute(
            "ALTER TABLE idea ADD COLUMN video_pipeline VARCHAR(20) NOT NULL DEFAULT 'flashcards'"
        )
        conn.commit()
        print("Colonne idea.video_pipeline ajoutée.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
