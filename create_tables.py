"""a simple script that creates necessary db tables"""

import sqlite3
import settings


# this isn't very dynamic, but it will do


queries = (
    """--sql
        CREATE TABLE IF NOT EXISTS tokens (
            title TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expiration_dt REAL NOT NULL
        );
    """,
    """--sql
        CREATE INDEX IF NOT EXISTS token_idx 
        ON tokens(title, expiration_dt);
    """,
    """--sql
        CREATE TABLE IF NOT EXISTS lmstasks (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            deadline REAL NOT NULL
        );
    """,
    """--sql
        CREATE INDEX IF NOT EXISTS lmstasks_idx 
        ON lmstasks(id, deadline, name);
    """,
    """--sql
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active = 0 OR is_active = 1),
            remind_interval REAL NOT NULL DEFAULT 86400
        );
    """,
    """--sql
        CREATE TABLE IF NOT EXISTS reminders (
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            last_reminded REAL DEFAULT 0 NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active = 0 OR is_active = 1),
            
            PRIMARY KEY (task_id, user_id),
            
            FOREIGN KEY (task_id)
                REFERENCES lmstasks(id)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE,
                    
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
        );
    """,
)


def main():
    with sqlite3.connect(settings.DB_PATH) as connection:
        cursor = connection.cursor()
        
        for query in queries:
            cursor.execute(query)
            
        cursor.close()
        

if __name__ == "__main__":
    main()
