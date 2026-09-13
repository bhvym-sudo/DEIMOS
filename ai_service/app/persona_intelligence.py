from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler


TOKEN = re.compile(r"[A-Za-z][A-Za-z''-]{1,}")
URL = re.compile(r"https?://|www\.", re.I)
FUNCTION_WORDS = ("the", "and", "to", "of", "a", "i", "is", "it", "that", "for", "you", "in")


def _json_list(value: Any) -> list[Any]:
    try:
        parsed = json.loads(value or "[]") if isinstance(value, str) else value
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _item_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return " ".join(str(value.get(key) or "") for key in ("title", "body", "text", "content")).strip()
    return ""


def _sets(row: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "contacts": {str(value).strip().lower() for value in _json_list(row.get("contacts_json")) if str(value).strip()},
        "pgp": {str(value).strip().lower() for value in _json_list(row.get("pgp_identifiers_json")) if str(value).strip()},
        "wallets": {str(value).strip().lower() for value in _json_list(row.get("wallets_json")) if str(value).strip()},
    }


def _stylometry(text: str, samples: list[str], posts: int, comments: int) -> list[float]:
    tokens = TOKEN.findall(text.lower())
    words = max(1, len(tokens))
    lengths = [len(sample) for sample in samples if sample]
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    features = [
        mean(lengths) if lengths else 0.0,
        pstdev(lengths) if len(lengths) > 1 else 0.0,
        len(text) / words,
        words / sentences,
        len(set(tokens)) / words,
        text.count("!") / words,
        text.count("?") / words,
        text.count(".") / words,
        text.count(",") / words,
        sum(char.isupper() for char in text) / max(1, len(text)),
        sum(char.isdigit() for char in text) / max(1, len(text)),
        len(URL.findall(text)) / words,
        posts / max(1, posts + comments),
        comments / max(1, posts + comments),
    ]
    features.extend(tokens.count(word) / words for word in FUNCTION_WORDS)
    return features


class PersonaIntelligence:
    def __init__(self, root: Path) -> None:
        database_root = root / "phobos" / "databases"
        self.profiles_path = database_root / "profiles.db"
        self.database_path = database_root / "persona_ai.db"
        self.model_path = root / "phobos" / "models" / "persona_linker.joblib"
        self.calibration_path = root / "phobos" / "models" / "evolution_authorship_calibrator.joblib"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS model_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, trained_at TEXT NOT NULL,
                    profile_count INTEGER NOT NULL, usable_profiles INTEGER NOT NULL,
                    activity_count INTEGER NOT NULL, feature_count INTEGER NOT NULL,
                    match_count INTEGER NOT NULL, threshold REAL NOT NULL,
                    model_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profile_fingerprints (
                    profile_id INTEGER PRIMARY KEY, username TEXT, source_domain TEXT,
                    sample_count INTEGER, character_count INTEGER,
                    stylometry_json TEXT, behavior_json TEXT, identifiers_json TEXT,
                    analyzed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS persona_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    left_profile_id INTEGER NOT NULL, right_profile_id INTEGER NOT NULL,
                    left_username TEXT, right_username TEXT,
                    left_domain TEXT, right_domain TEXT,
                    left_profile_url TEXT, right_profile_url TEXT,
                    confidence REAL NOT NULL, classification TEXT NOT NULL,
                    stylometry_similarity REAL NOT NULL, semantic_similarity REAL NOT NULL,
                    behavioral_similarity REAL NOT NULL, identifier_similarity REAL NOT NULL,
                    alias_similarity REAL NOT NULL, evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(left_profile_id,right_profile_id)
                );
                CREATE INDEX IF NOT EXISTS idx_persona_confidence ON persona_matches(confidence DESC);
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(persona_matches)")}
            for column in ("left_profile_url", "right_profile_url"):
                if column not in columns:
                    connection.execute(f"ALTER TABLE persona_matches ADD COLUMN {column} TEXT")

    def _corpus(self) -> tuple[list[dict[str, Any]], int]:
        if not self.profiles_path.exists():
            return [], 0
        connection = sqlite3.connect(self.profiles_path, timeout=30)
        connection.row_factory = sqlite3.Row
        profiles = [dict(row) for row in connection.execute("SELECT * FROM profiles ORDER BY id")]
        activities: dict[str, list[str]] = defaultdict(list)
        activity_count = 0
        try:
            for row in connection.execute("SELECT profile_url,title,body FROM profile_activity ORDER BY profile_url,page_number,position"):
                text = " ".join(filter(None, (row["title"], row["body"]))).strip()
                if text:
                    activities[row["profile_url"]].append(text)
                    activity_count += 1
        except sqlite3.OperationalError:
            pass
        connection.close()
        records = []
        for row in profiles:
            posts = [_item_text(value) for value in _json_list(row.get("posts_json"))]
            comments = [_item_text(value) for value in _json_list(row.get("comments_json"))]
            samples = [value for value in activities.get(row.get("profile_url") or "", []) + posts + comments if value]
            # Only authored activity is valid stylometric evidence. Profile-page
            # text contains shared templates and previously caused false 100% matches.
            normalized: dict[str, str] = {}
            for sample in samples:
                key = re.sub(r"\s+", " ", sample).strip().lower()
                if len(key) >= 20:
                    normalized.setdefault(key, sample.strip())
            samples = list(normalized.values())
            document = "\n".join(samples)[:120000]
            if len(document) < 300 or len(samples) < 3:
                continue
            records.append({
                "row": row, "document": document, "samples": samples,
                "style": _stylometry(document, samples, len(posts), len(comments)),
                "identifiers": _sets(row),
            })
        return records, activity_count

    def train(self, threshold: float = 0.48, max_matches: int = 750) -> dict[str, Any]:
        records, activity_count = self._corpus()
        if len(records) < 2:
            raise ValueError("At least two profiles with 80 or more characters are required")
        documents = [record["document"] for record in records]
        minimum_df = 2 if len(records) >= 10 else 1
        char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=minimum_df, max_features=14000, sublinear_tf=True)
        word_vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=minimum_df, max_features=9000, sublinear_tf=True, strip_accents="unicode")
        char_matrix = char_vectorizer.fit_transform(documents)
        word_matrix = word_vectorizer.fit_transform(documents)
        raw_behavior = np.asarray([record["style"] for record in records], dtype=float)
        scaler = StandardScaler()
        behavior_matrix = scaler.fit_transform(raw_behavior)
        style_similarity = cosine_similarity(char_matrix)
        semantic_similarity = cosine_similarity(word_matrix)
        distances = np.linalg.norm(behavior_matrix[:, None, :] - behavior_matrix[None, :, :], axis=2)
        behavior_similarity = np.exp(-distances / max(1.0, math.sqrt(behavior_matrix.shape[1])))
        calibrator = joblib.load(self.calibration_path) if self.calibration_path.exists() else None
        now = datetime.now(timezone.utc).isoformat()
        candidates = []
        fingerprints = []
        for index, record in enumerate(records):
            row = record["row"]
            identifiers = {key: sorted(values) for key, values in record["identifiers"].items()}
            fingerprints.append((row["id"], row.get("username"), row.get("source_domain"), len(record["samples"]), len(record["document"]), json.dumps(record["style"]), json.dumps({"posts": len(_json_list(row.get("posts_json"))), "comments": len(_json_list(row.get("comments_json"))), "samples": len(record["samples"])}), json.dumps(identifiers), now))
            for other in range(index + 1, len(records)):
                left, right = record, records[other]
                left_row, right_row = left["row"], right["row"]
                shared = {key: sorted(left["identifiers"][key] & right["identifiers"][key]) for key in left["identifiers"]}
                union = set().union(*left["identifiers"].values(), *right["identifiers"].values())
                intersection = set().union(*[set(values) for values in shared.values()])
                identifier_score = len(intersection) / len(union) if union else 0.0
                alias_score = SequenceMatcher(None, str(left_row.get("username") or "").lower(), str(right_row.get("username") or "").lower()).ratio()
                style_score = float(style_similarity[index, other])
                semantic_score = float(semantic_similarity[index, other])
                behavior_score = float(behavior_similarity[index, other])
                evidence_characters = min(len(left["document"]), len(right["document"]))
                evidence_samples = min(len(left["samples"]), len(right["samples"]))
                reliability = min(1.0, math.sqrt(evidence_characters / 3000.0) * min(1.0, evidence_samples / 8.0))
                style_score = min(0.98, 0.5 + (style_score - 0.5) * reliability)
                semantic_score = min(0.98, 0.5 + (semantic_score - 0.5) * reliability)
                behavior_score = min(0.98, 0.5 + (behavior_score - 0.5) * reliability)
                signal_score = 0.42 * style_score + 0.30 * semantic_score + 0.20 * behavior_score + 0.08 * reliability
                if calibrator:
                    calibrated = float(calibrator["classifier"].predict_proba([[style_score, semantic_score, behavior_score, reliability]])[0, 1])
                    confidence = 0.55 * calibrated + 0.35 * signal_score + 0.07 * alias_score + 0.03 * identifier_score
                else:
                    confidence = 0.88 * signal_score + 0.08 * alias_score + 0.04 * identifier_score
                if intersection:
                    confidence = min(0.96, confidence + 0.15)
                if str(left_row.get("source_domain") or "").lower() == str(right_row.get("source_domain") or "").lower() and not intersection:
                    confidence *= 0.82
                if not intersection and signal_score < 0.52:
                    continue
                confidence = min(0.96, max(0.01, confidence))
                if confidence < threshold:
                    continue
                classification = "strong candidate" if confidence >= 0.78 else "possible match" if confidence >= 0.62 else "weak lead"
                evidence = []
                evidence.append(f"{len(left['samples'])} vs {len(right['samples'])} authored samples; evidence reliability {reliability:.0%}")
                if style_score >= 0.55: evidence.append(f"calibrated writing-pattern similarity {style_score:.0%}")
                if semantic_score >= 0.45: evidence.append(f"topic/language similarity {semantic_score:.0%}")
                if behavior_score >= 0.60: evidence.append(f"behaviour similarity {behavior_score:.0%}")
                for key, values in shared.items():
                    if values: evidence.append(f"shared {key}: {', '.join(values[:3])}")
                if alias_score >= 0.65: evidence.append(f"alias similarity {alias_score:.0%}")
                candidates.append({"left": left_row, "right": right_row, "confidence": confidence, "classification": classification, "style": style_score, "semantic": semantic_score, "behavior": behavior_score, "identifiers": identifier_score, "alias": alias_score, "evidence": evidence or ["multi-signal similarity above configured threshold"]})
        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        candidates = candidates[:max_matches]
        with self._connect() as connection:
            connection.execute("DELETE FROM profile_fingerprints")
            connection.execute("DELETE FROM persona_matches")
            connection.executemany("INSERT INTO profile_fingerprints(profile_id,username,source_domain,sample_count,character_count,stylometry_json,behavior_json,identifiers_json,analyzed_at) VALUES(?,?,?,?,?,?,?,?,?)", fingerprints)
            connection.executemany("""
                INSERT INTO persona_matches(left_profile_id,right_profile_id,left_username,right_username,left_domain,right_domain,left_profile_url,right_profile_url,confidence,classification,stylometry_similarity,semantic_similarity,behavioral_similarity,identifier_similarity,alias_similarity,evidence_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [(item["left"]["id"], item["right"]["id"], item["left"].get("username"), item["right"].get("username"), item["left"].get("source_domain"), item["right"].get("source_domain"), item["left"].get("profile_url"), item["right"].get("profile_url"), item["confidence"], item["classification"], item["style"], item["semantic"], item["behavior"], item["identifiers"], item["alias"], json.dumps(item["evidence"]), now) for item in candidates])
            connection.execute("INSERT INTO model_runs(trained_at,profile_count,usable_profiles,activity_count,feature_count,match_count,threshold,model_version) VALUES(?,?,?,?,?,?,?,?)", (now, len(records), len(records), activity_count, char_matrix.shape[1] + word_matrix.shape[1] + behavior_matrix.shape[1], len(candidates), threshold, "THEMIS-1.0"))
        joblib.dump({"version": "THEMIS-1.0", "trained_at": now, "profile_ids": [record["row"]["id"] for record in records], "char_vectorizer": char_vectorizer, "word_vectorizer": word_vectorizer, "behavior_scaler": scaler, "feature_names": list(FUNCTION_WORDS)}, self.model_path, compress=3)
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            run = connection.execute("SELECT * FROM model_runs ORDER BY id DESC LIMIT 1").fetchone()
        calibration = None
        if self.calibration_path.exists():
            try:
                calibration = joblib.load(self.calibration_path).get("metrics")
            except Exception:
                calibration = None
        return {"trained": bool(run and self.model_path.exists()), "model_path": str(self.model_path), "calibration": calibration, "run": dict(run) if run else None}

    def matches(self, limit: int = 100, minimum_confidence: float = 0.0) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM persona_matches WHERE confidence>=? ORDER BY confidence DESC LIMIT ?", (minimum_confidence, limit)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["evidence"] = _json_list(item.pop("evidence_json", "[]"))
            result.append(item)
        return result

    def clear(self) -> dict[str, int]:
        with self._connect() as connection:
            matches = connection.execute("SELECT COUNT(*) FROM persona_matches").fetchone()[0]
            fingerprints = connection.execute("SELECT COUNT(*) FROM profile_fingerprints").fetchone()[0]
            connection.execute("DELETE FROM persona_matches")
            connection.execute("DELETE FROM profile_fingerprints")
            connection.execute("DELETE FROM model_runs")
        if self.model_path.exists():
            self.model_path.unlink()
        return {"matches": int(matches), "fingerprints": int(fingerprints)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--threshold", type=float, default=0.48)
    args = parser.parse_args()
    print(json.dumps(PersonaIntelligence(Path(args.root)).train(args.threshold), indent=2))
