from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup


PROFILE_PATH = re.compile(r"/(?:u|user|users|profile|profiles|member|members|vendor|vendors|seller|sellers)/([^/?#]+)", re.I)
HREF = re.compile(r"href\s*=\s*['\"]([^'\"]+)['\"]", re.I)


def _clean(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class WorkspaceGraphBuilder:
    """Builds an in-memory evidence graph from the two page stores and profile store."""

    def __init__(self, profiles_path: Path, engine_paths: dict[str, Path]) -> None:
        self.profiles_path = profiles_path
        self.engine_paths = engine_paths
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.crawl_urls: set[str] = set()
        self.expanded: set[int] = set()
        self.max_nodes = 260

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA query_only=ON")
        return connection

    def _add_node(self, node: dict[str, Any]) -> bool:
        if node["id"] in self.nodes:
            return True
        if len(self.nodes) >= self.max_nodes:
            return False
        self.nodes[node["id"]] = node
        return True

    def _add_edge(self, source: str, target: str, relationship: str) -> None:
        key = f"{source}|{target}|{relationship}"
        self.edges[key] = {"id": key, "source": source, "target": target, "relationship": relationship}

    def _profile_by_id(self, profile_id: int) -> sqlite3.Row | None:
        with self._connect(self.profiles_path) as connection:
            return connection.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()

    def _profile_by_username(self, username: str, domain: str = "") -> sqlite3.Row | None:
        with self._connect(self.profiles_path) as connection:
            if domain:
                row = connection.execute(
                    "SELECT * FROM profiles WHERE LOWER(username)=LOWER(?) AND LOWER(source_domain)=LOWER(?) ORDER BY last_seen DESC LIMIT 1",
                    (username, domain),
                ).fetchone()
                if row:
                    return row
            return connection.execute(
                "SELECT * FROM profiles WHERE LOWER(username)=LOWER(?) ORDER BY last_seen DESC LIMIT 1",
                (username,),
            ).fetchone()

    def _derived_activities(self, profile: sqlite3.Row, maximum: int) -> list[dict[str, Any]]:
        username = str(profile["username"] or "").strip("@ ")
        domain = str(profile["source_domain"] or "")
        if not username:
            return []
        derived: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for engine, path in self.engine_paths.items():
            if not path.exists():
                continue
            try:
                with self._connect(path) as connection:
                    pages = connection.execute(
                        """SELECT id,url,COALESCE(title,'') AS title,COALESCE(html_content,'') AS html
                           FROM pages WHERE is_active=1 AND LOWER(domain)=LOWER(?)
                             AND url NOT LIKE '%/u/%' AND html_content LIKE ?
                           ORDER BY crawled_at DESC LIMIT 80""",
                        (domain, "%" + username + "%"),
                    ).fetchall()
            except sqlite3.DatabaseError:
                continue
            for page in pages:
                soup = BeautifulSoup(page["html"], "html.parser")
                matches = []
                for anchor in soup.select("a[href]"):
                    match = PROFILE_PATH.search(urlparse(urljoin(page["url"], anchor.get("href", ""))).path)
                    if match and unquote(match.group(1)).strip("@ ").lower() == username.lower():
                        matches.append(anchor)
                for position, anchor in enumerate(matches):
                    container = None
                    fallback = None
                    for parent in anchor.parents:
                        if getattr(parent, "name", "") in {"body", "html"}:
                            break
                        marker = " ".join((str(parent.get("id", "")), " ".join(parent.get("class", [])))).lower()
                        text = _clean(parent.get_text(" ", strip=True), 2000)
                        if fallback is None and getattr(parent, "name", "") in {"article", "li", "tr"} and len(text) > len(username) + 12:
                            fallback = parent
                        if any(word in marker for word in ("comment", "reply", "post", "message", "thread", "topic")) and len(text) > len(username) + 12:
                            container = parent
                            break
                    container = container or fallback
                    if container is None:
                        continue
                    marker = " ".join((str(container.get("id", "")), " ".join(container.get("class", [])))).lower()
                    kind = "comment" if "comment" in marker or "reply" in marker else "post"
                    title_node = container.select_one("h1,h2,h3,h4,.title,.subject,[class*='title']")
                    date_node = container.select_one("time,.date,.timestamp,[class*='date'],[class*='time']")
                    body_node = container.select_one(".body,.content,.text,.message-body,.post-body,.comment-body,[itemprop='text']")
                    body = _clean((body_node or container).get_text(" ", strip=True), 900)
                    title = _clean(title_node.get_text(" ", strip=True) if title_node else page["title"], 180)
                    if len(body) <= len(username) + 5:
                        continue
                    key = (page["url"], kind, body)
                    if key in seen:
                        continue
                    seen.add(key)
                    derived.append({
                        "id": f"derived:{engine}:{page['id']}:{position}", "activity_type": kind,
                        "title": title, "body": body, "community": domain,
                        "date_label": _clean(date_node.get_text(" ", strip=True) if date_node else "", 100),
                        "source_page_url": page["url"], "target_url": page["url"], "page_number": 1,
                        "position": position,
                    })
                    if len(derived) >= maximum:
                        return derived
        return derived

    def _activities(self, profile: sqlite3.Row, maximum: int) -> list[Any]:
        try:
            with self._connect(self.profiles_path) as connection:
                rows = connection.execute(
                    """SELECT id,activity_type,title,body,community,date_label,source_page_url,
                              COALESCE(target_url,'') AS target_url,page_number,position
                       FROM profile_activity WHERE profile_url=?
                       ORDER BY page_number,position""",
                    (profile["profile_url"],),
                ).fetchall()
        except sqlite3.DatabaseError:
            rows = []
        if len(rows) < maximum:
            rows = list(rows) + self._derived_activities(profile, maximum - len(rows))
        posts = [row for row in rows if row["activity_type"] == "post"]
        comments = [row for row in rows if row["activity_type"] == "comment"]
        per_side = max(1, maximum // 2)
        selected = posts[:per_side] + comments[:per_side]
        if len(selected) < maximum:
            used = {row["id"] for row in selected}
            selected += [row for row in rows if row["id"] not in used][: maximum - len(selected)]
        return selected[:maximum]

    def _page(self, raw_url: str) -> tuple[str, sqlite3.Row] | None:
        if not raw_url:
            return None
        target = raw_url.split("#", 1)[0].rstrip("/")
        for engine, path in self.engine_paths.items():
            if not path.exists():
                continue
            try:
                with self._connect(path) as connection:
                    row = connection.execute(
                        """SELECT id,url,COALESCE(title,'') AS title,COALESCE(html_content,'') AS html,
                                  COALESCE(content,'') AS content,COALESCE(threat_score,0) AS threat_score,
                                  COALESCE(threat_level,'') AS threat_level
                           FROM pages WHERE RTRIM(url,'/')=? OR url LIKE ? ORDER BY crawled_at DESC LIMIT 1""",
                        (target, target + "?%"),
                    ).fetchone()
                if row:
                    return engine, row
            except sqlite3.DatabaseError:
                continue
        return None

    @staticmethod
    def _profile_links(html: str, base_url: str) -> list[tuple[str, str]]:
        links: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for href in HREF.findall(html or ""):
            absolute = urljoin(base_url, href)
            match = PROFILE_PATH.search(urlparse(absolute).path)
            if not match:
                continue
            username = unquote(match.group(1)).strip("@ ")
            parsed = urlparse(absolute)
            profile_url = parsed._replace(path=parsed.path[:match.start()] + "/u/" + username, query="", fragment="").geturl().rstrip("/")
            key = (username.lower(), profile_url.lower())
            if username and key not in seen:
                seen.add(key)
                links.append((username, profile_url))
        return links

    def _add_profile(self, row: sqlite3.Row, profile_level: int, depth: int, max_activities: int, parent: str | None = None, relationship: str = "linked") -> str:
        profile_id = int(row["id"])
        node_id = f"profile:{profile_id}"
        username = row["username"] or row["display_name"] or f"Profile {profile_id}"
        self._add_node({
            "id": node_id, "type": "profile", "label": "@" + str(username).lstrip("@"),
            "subtitle": row["role"] or row["source_domain"] or "Known profile", "url": row["profile_url"],
            "depth": profile_level, "side": 0 if parent is None else 1, "known": True,
            "profile_id": profile_id, "metadata": {"territory": row["territory"] or "", "reputation": row["reputation"] or "", "last_seen": row["last_seen"] or ""},
        })
        if parent:
            self._add_edge(parent, node_id, relationship)
        if profile_id in self.expanded or profile_level >= depth or len(self.nodes) >= self.max_nodes:
            return node_id
        self.expanded.add(profile_id)
        owner = str(username).lstrip("@").lower()
        for activity in self._activities(row, max_activities):
            kind = activity["activity_type"]
            activity_id = f"activity:{activity['id']}"
            target_url = activity["target_url"] or activity["source_page_url"] or ""
            label = activity["title"] or activity["body"] or ("Post" if kind == "post" else "Comment")
            side = -1 if kind == "post" else 1
            if not self._add_node({
                "id": activity_id, "type": kind, "label": _clean(label, 90),
                "subtitle": _clean(activity["date_label"] or activity["community"] or kind.title(), 80),
                "url": target_url, "depth": profile_level + 1, "side": side, "known": True,
                "metadata": {"body": _clean(activity["body"], 600), "community": activity["community"] or "", "date": activity["date_label"] or ""},
            }):
                break
            self._add_edge(node_id, activity_id, "authored" if kind == "post" else "commented")
            page_match = self._page(target_url)
            if not page_match:
                continue
            _, page = page_match
            participants = self._profile_links(page["html"], page["url"])
            for related_username, related_url in participants[:10]:
                if related_username.lower() == owner:
                    continue
                related = self._profile_by_username(related_username, urlparse(related_url).hostname or "")
                if related:
                    related_id = self._add_profile(related, profile_level + 1, depth, max_activities, activity_id, "participated")
                    if profile_level + 1 < depth:
                        self._add_profile(related, profile_level + 1, depth, max_activities)
                else:
                    lead_id = "lead:" + (urlparse(related_url).hostname or "unknown") + ":" + related_username.lower()
                    if self._add_node({
                        "id": lead_id, "type": "lead", "label": "@" + related_username,
                        "subtitle": "Profile not collected", "url": related_url, "depth": profile_level + 1,
                        "side": side, "known": False, "metadata": {"status": "queued for discovery"},
                    }):
                        self._add_edge(activity_id, lead_id, "participated")
                        self.crawl_urls.add(related_url)
        return node_id

    def build(self, profile_ids: list[int], page_url: str, depth: int, max_activities: int) -> dict[str, Any]:
        depth = min(max(depth, 1), 4)
        max_activities = min(max(max_activities, 2), 30)
        roots: list[str] = []
        if self.profiles_path.exists():
            for profile_id in dict.fromkeys(profile_ids[:12]):
                row = self._profile_by_id(profile_id)
                if row:
                    roots.append(self._add_profile(row, 0, depth, max_activities))
        if page_url.strip():
            page_match = self._page(page_url.strip())
            if page_match:
                engine, page = page_match
                page_id = f"website:{engine}:{page['id']}"
                self._add_node({"id": page_id, "type": "website", "label": _clean(page["title"] or page["url"], 100), "subtitle": engine, "url": page["url"], "depth": 0, "side": 0, "known": True, "metadata": {"threat_level": page["threat_level"], "threat_score": page["threat_score"]}})
                roots.append(page_id)
                for username, profile_url in self._profile_links(page["html"], page["url"])[0:30]:
                    related = self._profile_by_username(username, urlparse(profile_url).hostname or "") if self.profiles_path.exists() else None
                    if related:
                        self._add_profile(related, 0, depth, max_activities, page_id, "contains profile")
                    else:
                        lead_id = "lead:" + (urlparse(profile_url).hostname or "unknown") + ":" + username.lower()
                        self._add_node({"id": lead_id, "type": "lead", "label": "@" + username, "subtitle": "Profile not collected", "url": profile_url, "depth": 1, "side": 1, "known": False, "metadata": {"status": "queued for discovery"}})
                        self._add_edge(page_id, lead_id, "contains profile")
                        self.crawl_urls.add(profile_url)
        return {
            "nodes": list(self.nodes.values()), "edges": list(self.edges.values()), "roots": roots,
            "crawl_urls": sorted(self.crawl_urls)[:60], "depth": depth,
            "truncated": len(self.nodes) >= self.max_nodes,
        }
