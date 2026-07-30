from __future__ import annotations

import os
from pathlib import Path

from app.core.database import create_sqlite_engine
from app.models import Base


def main() -> None:
    data_dir = Path(os.environ.get("OS_AGENT_DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    database_file = data_dir / "memory.db"
    engine = create_sqlite_engine(f"sqlite:///{database_file.as_posix()}")
    Base.metadata.create_all(engine)
    if os.name != "nt":
        os.chmod(data_dir, 0o700)
        os.chmod(database_file, 0o600)
    print(f"SQLite initialized: {database_file}")
    print(f"Tables: {len(Base.metadata.tables)}")


if __name__ == "__main__":
    main()
