"""Initialize the configured SQLite database and registered ORM tables."""

from __future__ import annotations

from app.core.database import init_db


def main() -> None:
    engine = init_db()
    print(f"database initialized: {engine.url.render_as_string(hide_password=True)}")


if __name__ == "__main__":
    main()
