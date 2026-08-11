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
        if column_exists(conn, "idea", "short_group_size"):
            print("idea.short_group_size existe déjà — rien à faire.")
            return
        # DEFAULT 1 : les Shorts déjà catalogués restent sur le modèle
        # historique (un mot chacun), aucune vidéo déjà générée/publiée n'est
        # affectée par cette migration.
        conn.execute("ALTER TABLE idea ADD COLUMN short_group_size INTEGER NOT NULL DEFAULT 1")
        conn.commit()
        print("Colonne idea.short_group_size ajoutée (défaut 1 pour les lignes existantes).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
