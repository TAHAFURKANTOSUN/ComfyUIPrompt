"""Sohbet oturumlarının kalıcı saklanması (SQLite — Python standart kütüphanesi).

Her tur için iki satır tutulur (kullanıcı + asistan). Her satırda iki ayrı bilgi
bulunur:
  - role/content: LLM'e geçmiş olarak geri gönderilen metin (görsel analizi
    tarifi dahil, <think> blokları hariç),
  - ui: arayüzün sohbeti yeniden çizmesi için gereken JSON (kullanıcının yazdığı
    asıl metin, eklediği görsel, üretilen prompt paketi).

Bir oturum yalnızca ilk tur BAŞARIYLA tamamlandığında oluşturulur; iptal edilen
veya hata alan istekler veritabanında iz bırakmaz.

Veritabanı yolu config.json -> sessions.db_path (varsayılan data/sessions.db) veya
SESSIONS_DB ortam değişkeniyle belirlenir. ":memory:" kalıcı olmayan mod sağlar.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    created    REAL NOT NULL,
    updated    REAL NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    format_id  TEXT,
    family_id  TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    ui         TEXT,
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated);
"""

TITLE_CHARS = 80


class SessionStore:
    def __init__(self, path: str | Path, max_sessions: int = 500):
        self.path = str(path)
        self.max_sessions = max(1, int(max_sessions))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # FastAPI async uçları tek olay döngüsünde çalışır ama TestClient ve
        # olası iş parçacıkları için bağlantı paylaşımı bir kilitle korunur.
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA foreign_keys = ON")
            if self.path != ":memory:":
                self._db.execute("PRAGMA journal_mode = WAL")
            self._db.executescript(SCHEMA)

    # ------------------------------------------------------------------ okuma
    def history(self, sid: str, limit: int) -> list:
        """LLM'e gönderilecek son `limit` mesaj (eskiden yeniye)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT role, content FROM (SELECT id, role, content FROM messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
                (sid, int(limit)),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def get(self, sid: str) -> dict | None:
        """Arayüz için oturum + mesajlar; yoksa None."""
        with self._lock:
            s = self._db.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
            if s is None:
                return None
            rows = self._db.execute(
                "SELECT ui FROM messages WHERE session_id = ? ORDER BY id", (sid,)
            ).fetchall()
        messages = []
        for r in rows:
            try:
                ui = json.loads(r["ui"]) if r["ui"] else None
            except ValueError:
                ui = None
            if isinstance(ui, dict):
                messages.append(ui)
        return {**self._session_dict(s), "messages": messages}

    def list_sessions(self, limit: int = 100) -> list:
        with self._lock:
            rows = self._db.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS n "
                "FROM sessions s ORDER BY s.updated DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [{**self._session_dict(r), "message_count": r["n"]} for r in rows]

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    # ------------------------------------------------------------------ yazma
    def append_turn(
        self,
        sid: str,
        user_content: str,
        assistant_content: str,
        ui_user: dict,
        ui_assistant: dict,
        title: str,
        format_id: str | None,
        family_id: str | None,
    ) -> None:
        """Bir kullanıcı+asistan turunu atomik olarak ekler (oturum yoksa açar)."""
        now = time.time()
        title = " ".join((title or "").split())[:TITLE_CHARS] or "Görsel"
        with self._lock:
            with self._tx():
                self._db.execute(
                    "INSERT INTO sessions (id, created, updated, title, format_id, family_id) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET updated = excluded.updated, "
                    "format_id = excluded.format_id, family_id = excluded.family_id",
                    (sid, now, now, title, format_id, family_id),
                )
                self._db.executemany(
                    "INSERT INTO messages (session_id, role, content, ui, ts) VALUES (?, ?, ?, ?, ?)",
                    [
                        (sid, "user", user_content, json.dumps(ui_user, ensure_ascii=False), now),
                        (sid, "assistant", assistant_content,
                         json.dumps(ui_assistant, ensure_ascii=False), now),
                    ],
                )
                self._prune()

    def delete(self, sid: str) -> bool:
        with self._lock:
            with self._tx():
                cur = self._db.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        return cur.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ iç
    def _tx(self):
        db = self._db

        class _Tx:
            def __enter__(self_inner):
                db.execute("BEGIN IMMEDIATE")

            def __exit__(self_inner, exc_type, exc, tb):
                db.execute("ROLLBACK" if exc_type else "COMMIT")
                return False

        return _Tx()

    def _prune(self) -> None:
        """En eski oturumları siler (kilit ve işlem içinde çağrılır)."""
        self._db.execute(
            "DELETE FROM sessions WHERE id IN (SELECT id FROM sessions "
            "ORDER BY updated DESC LIMIT -1 OFFSET ?)",
            (self.max_sessions,),
        )

    @staticmethod
    def _session_dict(row) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "created": row["created"],
            "updated": row["updated"],
            "format_id": row["format_id"],
            "family_id": row["family_id"],
        }


_STORE: SessionStore | None = None
_STORE_LOCK = threading.Lock()


def get_store() -> SessionStore:
    """Yapılandırmaya göre tekil depo (ilk kullanımda açılır)."""
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                from .config import ROOT, load_config

                cfg = load_config().get("sessions", {})
                raw = str(cfg.get("db_path") or "data/sessions.db")
                path = raw if raw == ":memory:" else (
                    Path(raw) if Path(raw).is_absolute() else ROOT / raw
                )
                _STORE = SessionStore(path, cfg.get("max_sessions", 500))
    return _STORE
