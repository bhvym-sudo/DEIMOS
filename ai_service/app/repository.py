from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


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
        }
        self.profiles_path = root / "phobos" / "config_files" / "profiles.json"

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
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

    def profiles(self) -> list[dict[str, Any]]:
        if not self.profiles_path.exists():
            return []
        payload = json.loads(self.profiles_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else list(payload.values()) if isinstance(payload, dict) else []
