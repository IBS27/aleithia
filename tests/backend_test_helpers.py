from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import shared_data
from database import Base
from routes import data_routes as data_routes_module
from routes.data_routes import router as data_router


def write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)


class LocalAccessor:
    def __init__(self, root: Path):
        self.root = root

    def _local(self, relative_path: str) -> Path:
        relative = Path(relative_path) if relative_path else Path(".")
        return (self.root / relative).resolve()

    def _entry(self, path: Path):
        if not path.exists():
            return None
        relative = path.relative_to(self.root).as_posix()
        stat = path.stat()
        return shared_data.SharedFileEntry(
            path="" if relative == "." else relative,
            is_file=path.is_file(),
            is_dir=path.is_dir(),
            mtime=stat.st_mtime,
            size=stat.st_size,
        )

    def get_entry(self, relative_path: str):
        return self._entry(self._local(relative_path))

    def list_entries(self, relative_path: str, *, recursive: bool = False):
        base = self._local(relative_path)
        if not base.exists():
            return []
        if base.is_file():
            entry = self._entry(base)
            return [entry] if entry is not None else []
        iterator = base.rglob("*") if recursive else base.iterdir()
        return [entry for item in iterator if (entry := self._entry(item)) is not None]

    def read_bytes(self, relative_path: str) -> bytes:
        return self._local(relative_path).read_bytes()


class CountingAccessor(LocalAccessor):
    def __init__(self, root: Path):
        super().__init__(root)
        self.list_entries_calls: list[tuple[str, bool]] = []
        self.get_entry_calls: list[str] = []

    def get_entry(self, relative_path: str):
        self.get_entry_calls.append(relative_path)
        return super().get_entry(relative_path)

    def list_entries(self, relative_path: str, *, recursive: bool = False):
        self.list_entries_calls.append((relative_path, recursive))
        return super().list_entries(relative_path, recursive=recursive)


class StrictRecursiveAccessor(CountingAccessor):
    def get_entry(self, relative_path: str):
        normalized = relative_path.replace("\\", "/")
        if normalized.endswith(".json") and "/" in normalized:
            raise AssertionError(f"unexpected child get_entry lookup for {normalized}")
        return super().get_entry(relative_path)


def reset_shared_data_state() -> None:
    shared_data._LAST_LOGGED_LAYOUT = None
    shared_data._VOLUME = None
    data_routes_module._DATA_SNAPSHOT_CACHE.clear()
    data_routes_module._DATA_SNAPSHOT_REFRESHING.clear()


def install_local_accessor(monkeypatch, data_root: Path) -> None:
    monkeypatch.setattr(shared_data, "_get_accessor", lambda: LocalAccessor(data_root))
    reset_shared_data_state()


def make_data_client(monkeypatch, data_root: Path) -> TestClient:
    install_local_accessor(monkeypatch, data_root)
    return make_router_client()


def make_router_client() -> TestClient:
    app = FastAPI()
    app.include_router(data_router, prefix="/api/data")
    return TestClient(app)


def make_user_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "user-data.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(data_router, prefix="/api/data")

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[data_routes_module.get_db] = override_get_db
    return TestClient(app)
