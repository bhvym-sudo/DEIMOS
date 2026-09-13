from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .workspace_graph import WorkspaceGraphBuilder


def _read_json(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


class IntelligenceRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        database_root = root / "phobos" / "databases"
        self.engine_paths = {
            "crawler": database_root / "crawler.db",
            "phobos-search": database_root / "phobos_search.db",
            "workspace-crawler": database_root / "workspace.db",
        }
        self.profiles_path = database_root / "profiles.db"

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _connect_profile(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA query_only=ON")
        return connection

    def _paths(self, engine: str | None = None) -> list[tuple[str, Path]]:
        if engine:
            path = self.engine_paths.get(engine)
            return [(engine, path)] if path and path.exists() else []
        return [(name, path) for name, path in self.engine_paths.items() if path.exists()]

    def stats(self, engine: str | None = None) -> dict[str, int]:
        totals = {"analyzed_pages": 0, "critical_findings": 0, "high_findings": 0, "entities_found": 0}
        for _, path in self._paths(engine):
            try:
                with self._connect(path) as analysis:
                    totals["analyzed_pages"] += analysis.execute("SELECT COUNT(*) FROM threat_analysis").fetchone()[0]
                    totals["critical_findings"] += analysis.execute("SELECT COUNT(*) FROM threat_analysis WHERE risk_classification = 'CRITICAL_THREAT' OR threat_level = 'CRITICAL'").fetchone()[0]
                    totals["high_findings"] += analysis.execute("SELECT COUNT(*) FROM threat_analysis WHERE risk_classification = 'HIGH_THREAT' OR threat_level = 'HIGH'").fetchone()[0]
                    rows = analysis.execute("SELECT persons, organizations, locations, dates, money FROM ner_results").fetchall()
                    totals["entities_found"] += sum(len(_read_json(row[column])) for row in rows for column in ("persons", "organizations", "locations", "dates", "money"))
            except sqlite3.OperationalError:
                continue
        return totals

    def reports(self, limit: int = 50) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for engine, path in self._paths():
            try:
                with self._connect(path) as connection:
                    records = connection.execute("SELECT id, page_id, url, threat_score, threat_level, matched_keywords, analyzed_at, risk_classification, origin_country FROM threat_analysis ORDER BY analyzed_at DESC LIMIT ?", (limit,)).fetchall()
                rows.extend({"id": f"{engine}:{row['id']}", "engine": engine, "page_id": row["page_id"], "url": row["url"], "threat_score": row["threat_score"] or 0, "threat_level": row["threat_level"] or "LOW", "risk_classification": row["risk_classification"], "origin_country": row["origin_country"], "matched_keywords": _read_json(row["matched_keywords"]), "analyzed_at": row["analyzed_at"]} for row in records)
            except sqlite3.OperationalError:
                continue
        return sorted(rows, key=lambda row: row.get("analyzed_at") or "", reverse=True)[:limit]

    def entities(self, limit: int = 100) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for engine, path in self._paths():
            try:
                with self._connect(path) as connection:
                    records = connection.execute("SELECT page_id, url, persons, organizations, locations, dates, money, processed_at FROM ner_results ORDER BY processed_at DESC LIMIT ?", (limit,)).fetchall()
                rows.extend({"engine": engine, "page_id": row["page_id"], "url": row["url"], "persons": _read_json(row["persons"]), "organizations": _read_json(row["organizations"]), "locations": _read_json(row["locations"]), "dates": _read_json(row["dates"]), "money": _read_json(row["money"]), "processed_at": row["processed_at"]} for row in records)
            except sqlite3.OperationalError:
                continue
        return sorted(rows, key=lambda row: row.get("processed_at") or "", reverse=True)[:limit]

    def profiles(self, limit: int = 100, query: str = "") -> list[dict[str, Any]]:
        if not self.profiles_path.exists():
            return []
        pattern = f"%{query.strip()}%"
        where = ""
        parameters: tuple[Any, ...] = (limit,)
        if query.strip():
            where = "WHERE profile_url LIKE ? OR username LIKE ? OR display_name LIKE ? OR source_domain LIKE ?"
            parameters = (pattern, pattern, pattern, pattern, limit)
        try:
            with self._connect_profile(self.profiles_path) as connection:
                rows = connection.execute(f"""
                    SELECT id,profile_url,source_engine,source_domain,username,display_name,role,
                           territory,joined_at,last_active,reputation,avatar_url,
                           posts_json,comments_json,detection_method,detection_confidence,
                           first_seen,last_seen,crawled_at,
                           (SELECT COUNT(*) FROM profile_snapshots s WHERE s.profile_url=profiles.profile_url) AS observation_count
                    FROM profiles {where} ORDER BY last_seen DESC LIMIT ?
                """, parameters).fetchall()
            return [
                {
                    **dict(row),
                    "posts": _read_json(row["posts_json"]),
                    "comments": _read_json(row["comments_json"]),
                }
                for row in rows
            ]
        except sqlite3.DatabaseError:
            return []

    def profile_count(self) -> int:
        if not self.profiles_path.exists():
            return 0
        try:
            with self._connect_profile(self.profiles_path) as connection:
                return int(connection.execute("SELECT COUNT(*) FROM profiles").fetchone()[0])
        except sqlite3.DatabaseError:
            return 0

    def profile(self, profile_id: int) -> dict[str, Any] | None:
        if not self.profiles_path.exists():
            return None
        with self._connect_profile(self.profiles_path) as connection:
            row = connection.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        for source, target in (
            ("contacts_json", "contacts"),
            ("pgp_identifiers_json", "pgp_identifiers"),
            ("wallets_json", "wallets"),
            ("posts_json", "posts"),
            ("comments_json", "comments"),
        ):
            result[target] = _read_json(result.get(source))
        try:
            result["ner_entities"] = json.loads(result.get("ner_entities_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            result["ner_entities"] = {}
        with self._connect_profile(self.profiles_path) as connection:
            try:
                activity = connection.execute("""
                    SELECT activity_type,title,body,community,date_label,source_page_url,
                           COALESCE(target_url,'') AS target_url_safe,page_number,position,first_seen,last_seen
                    FROM profile_activity WHERE profile_url=?
                    ORDER BY page_number ASC,position ASC
                """, (result["profile_url"],)).fetchall()
            except sqlite3.OperationalError:
                activity = []
            snapshots = connection.execute(
                "SELECT snapshot_json,observed_at FROM profile_snapshots WHERE profile_url=? ORDER BY observed_at DESC LIMIT 25",
                (result["profile_url"],),
            ).fetchall()
        result["activity"] = [
            {
                "type": row["activity_type"], "title": row["title"] or "",
                "body": row["body"] or "", "community": row["community"] or "",
                "date_label": row["date_label"] or "", "source_page_url": row["source_page_url"] or "",
                "target_url": row["target_url_safe"] or "", "page_number": row["page_number"],
                "position": row["position"], "first_seen": row["first_seen"], "last_seen": row["last_seen"],
            }
            for row in activity
        ]
        result["history"] = [
            {"observed_at": snapshot["observed_at"], **json.loads(snapshot["snapshot_json"])}
            for snapshot in snapshots
        ]
        result["observation_count"] = len(result["history"])
        return result

    def clear_profiles(self) -> int:
        if not self.profiles_path.exists():
            return 0
        connection = sqlite3.connect(self.profiles_path, timeout=30)
        try:
            result = connection.execute("DELETE FROM profiles")
            connection.execute("DELETE FROM profile_snapshots")
            try:
                connection.execute("DELETE FROM profile_activity")
            except sqlite3.OperationalError:
                pass
            connection.execute("DELETE FROM profile_scan_state")
            connection.execute("DELETE FROM sqlite_sequence WHERE name IN ('profiles','profile_snapshots','profile_activity')")
            for engine, path in self._paths():
                try:
                    with self._connect(path) as source:
                        last_page_id = source.execute("SELECT COALESCE(MAX(id), 0) FROM pages").fetchone()[0]
                    connection.execute(
                        "INSERT INTO profile_scan_state(source_engine,last_page_id,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)",
                        (engine, last_page_id),
                    )
                except sqlite3.OperationalError:
                    continue
            connection.commit()
            return result.rowcount
        finally:
            connection.close()

    def request_profile_rescan(self, engine: str) -> None:
        if engine not in self.engine_paths:
            raise ValueError("Unknown engine")
        connection = sqlite3.connect(self.profiles_path, timeout=30)
        try:
            connection.execute("PRAGMA busy_timeout=30000")
            try:
                connection.execute("ALTER TABLE profile_scan_state ADD COLUMN rescan_requested BOOLEAN DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            connection.execute("""
                INSERT INTO profile_scan_state(source_engine,last_page_id,rescan_requested,updated_at)
                VALUES(?,0,1,CURRENT_TIMESTAMP)
                ON CONFLICT(source_engine) DO UPDATE SET rescan_requested=1,updated_at=CURRENT_TIMESTAMP
            """, (engine,))
            connection.commit()
        finally:
            connection.close()

    def workspace_graph(self, profile_ids: list[int], page_url: str, depth: int, max_activities: int) -> dict[str, Any]:
        builder = WorkspaceGraphBuilder(self.profiles_path, self.engine_paths)
        return builder.build(profile_ids, page_url, depth, max_activities)
