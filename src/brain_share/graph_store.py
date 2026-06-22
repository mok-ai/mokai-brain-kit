import sqlite3
import threading

class SqliteGraphStore:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (name TEXT PRIMARY KEY, count REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS edges (
                a TEXT NOT NULL, b TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 0, count REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (a, b)
            );
            CREATE INDEX IF NOT EXISTS idx_edges_a ON edges(a);
            CREATE INDEX IF NOT EXISTS idx_edges_b ON edges(b);
            CREATE TABLE IF NOT EXISTS processed (uid TEXT PRIMARY KEY);
            """
        )
        self.conn.commit()
        self._lock = threading.Lock()

    @staticmethod
    def _order(a, b):
        return (a, b) if a <= b else (b, a)

    def bump_node(self, name, inc=1.0):
        with self._lock:
            self.conn.execute(
                "INSERT INTO nodes(name,count) VALUES(?,?) "
                "ON CONFLICT(name) DO UPDATE SET count=count+excluded.count",
                (name, inc))
            self.conn.commit()

    def get_node_count(self, name):
        with self._lock:
            r = self.conn.execute("SELECT count FROM nodes WHERE name=?", (name,)).fetchone()
            return float(r["count"]) if r else 0.0

    def total_node_count(self):
        with self._lock:
            r = self.conn.execute("SELECT COALESCE(SUM(count),0) AS t FROM nodes").fetchone()
            return float(r["t"])

    def upsert_edge(self, a, b, inc=1.0):
        a, b = self._order(a, b)
        with self._lock:
            self.conn.execute(
                "INSERT INTO edges(a,b,weight,count) VALUES(?,?,?,?) "
                "ON CONFLICT(a,b) DO UPDATE SET weight=weight+excluded.weight, count=count+excluded.count",
                (a, b, inc, inc))
            self.conn.commit()

    def get_edge(self, a, b):
        a, b = self._order(a, b)
        with self._lock:
            r = self.conn.execute("SELECT a,b,weight,count FROM edges WHERE a=? AND b=?", (a, b)).fetchone()
            return {"a": r["a"], "b": r["b"], "weight": float(r["weight"]), "count": float(r["count"])} if r else None

    def decay_all(self, factor):
        with self._lock:
            self.conn.execute("UPDATE edges SET weight=weight*?", (factor,))
            self.conn.commit()

    def prune(self, min_weight):
        with self._lock:
            cur = self.conn.execute("DELETE FROM edges WHERE weight < ?", (min_weight,))
            self.conn.commit()
            return cur.rowcount

    def neighbors(self, node, top_k=10):
        with self._lock:
            rows = self.conn.execute(
                "SELECT CASE WHEN a=? THEN b ELSE a END AS node, weight, count "
                "FROM edges WHERE a=? OR b=? ORDER BY weight DESC LIMIT ?",
                (node, node, node, top_k)).fetchall()
            return [{"node": r["node"], "weight": float(r["weight"]), "count": float(r["count"])} for r in rows]

    def is_processed(self, uid):
        with self._lock:
            return self.conn.execute("SELECT 1 FROM processed WHERE uid=?", (uid,)).fetchone() is not None

    def mark_processed(self, uid):
        with self._lock:
            self.conn.execute("INSERT OR IGNORE INTO processed(uid) VALUES(?)", (uid,))
            self.conn.commit()

    def close(self):
        self.conn.close()
