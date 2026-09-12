import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from bs4 import BeautifulSoup


PROFILE_PATH = re.compile(r"/(?:u|user|users|profile|profiles|member|members|vendor|vendors|seller|sellers)/([^/?#]+)", re.I)
USERNAME = re.compile(r"\b(?:user(?:name)?|handle)\s*[:#]?\s*@?([a-z0-9_.-]{2,64})", re.I)
LABELED_FIELDS = {
    "role": re.compile(r"\b(?:type|role|rank)\s*:\s*(.{2,80}?)(?=\s+(?:territory|location|country|region|message|joined|member since|last active|last seen|reputation|trust|rating)\s*:|$)", re.I),
    "territory": re.compile(r"\b(?:territory|location|country|region)\s*:\s*(.{2,100}?)(?=\s+(?:message|joined|member since|last active|last seen|reputation|trust|rating)\s*:|$)", re.I),
    "joined_at": re.compile(r"\b(?:joined|member since|registered)\s*:\s*(.{2,100}?)(?=\s+(?:last active|last seen|reputation|trust|rating|message)\s*:|$)", re.I),
    "last_active": re.compile(r"\b(?:last active|last seen)\s*:\s*(.{2,100}?)(?=\s+(?:reputation|trust|rating|message)\s*:|$)", re.I),
    "reputation": re.compile(r"\b(?:reputation|trust|rating)\s*:\s*(.{1,80}?)(?=\s+message\s*:|$)", re.I),
}
EMAIL = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
PGP = re.compile(r"\b(?:[A-F0-9]{4}[\s:-]?){4,10}\b", re.I)
BTC = re.compile(r"\b(?:bc1[a-zA-HJ-NP-Z0-9]{25,62}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
XMR = re.compile(r"\b[48][0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b")


def _unique(values, limit=100):
    result, seen = [], set()
    for value in values:
        value = " ".join(str(value).split())
        if len(value) < 2 or len(value) > 4000 or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _node_text(node):
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _canonical_profile_url(raw_url):
    parsed = urlparse(raw_url)
    match = PROFILE_PATH.search(parsed.path)
    if not match:
        return raw_url
    path = parsed.path[:match.start()] + "/u/" + match.group(1).strip("@")
    return parsed._replace(path=path.rstrip("/"), query="", fragment="").geturl()


def _activity_text(activity):
    context = activity.get("title", "")
    body = activity.get("body", "")
    prefix = " · ".join(value for value in (activity.get("date", ""), activity.get("community", "")) if value)
    content = (("Re: " + context + " — ") if activity["type"] == "comment" and context else "") + body
    if activity["type"] == "post":
        content = context or body
    return (prefix + (" · " if prefix and content else "") + content).strip()


def _tenebris_profile(soup, raw_url, username):
    panel = soup.select_one("#user-main")
    if not panel:
        return None
    result = {"activities": [], "username": username, "role": "", "joined_at": "", "reputation": "", "avatar_url": ""}
    name_node = panel.select_one("#user-name")
    if name_node:
        direct_name = next((str(value).strip() for value in name_node.find_all(string=True, recursive=False) if str(value).strip()), "")
        if direct_name:
            result["username"] = direct_name
        tier = name_node.select_one("[data-tooltip], [title], [aria-label]")
        if tier:
            result["role"] = tier.get("data-tooltip") or tier.get("title") or tier.get("aria-label") or ""
    avatar = panel.select_one("#user-image img")
    if avatar and avatar.get("src"):
        result["avatar_url"] = urljoin(raw_url, avatar["src"])
    karma = panel.select_one("#user-karma span, #user-karma")
    if karma:
        result["reputation"] = _node_text(karma)
    for field in panel.select(".field"):
        label = _node_text(field.select_one(".field-label")).lower()
        value = _node_text(field.select_one(".field-text"))
        if label in {"member since", "joined", "registered"}:
            result["joined_at"] = value
    query = parse_qs(urlparse(raw_url).query)
    try:
        page_number = max(1, int(query.get("page", ["1"])[0]))
    except ValueError:
        page_number = 1
    for container in soup.select(".messages .message-container"):
        creator = container.select_one(".creator a[href*='/u/']")
        if creator:
            creator_match = PROFILE_PATH.search(creator.get("href", ""))
            if creator_match and result["username"] and creator_match.group(1).lower() != result["username"].lower():
                continue
        date = _node_text(container.select_one(".date")).replace(", in", "").strip(" ,")
        community = _node_text(container.select_one(".community-pill"))
        comment_wrapper = container.select_one(".user-comment-wrapper")
        if comment_wrapper:
            title_node = container.select_one(".user-comment-post-title")
            title = _node_text(title_node)
            body = _node_text(comment_wrapper.select_one(".user-comment-body"))
            if body:
                result["activities"].append({"type": "comment", "title": title, "body": body, "community": community, "date": date, "page_number": page_number, "target_url": urljoin(raw_url, title_node.get("href", "")) if title_node else ""})
            continue
        title_node = container.select_one(".content > .title a, .content > .title")
        title = _node_text(title_node)
        body = _node_text(container.select_one(".post-body, .post-content, .message-body"))
        if title or body:
            target = container.select_one(".post-link-overlay[href]") or (title_node if title_node and title_node.name == "a" else None)
            result["activities"].append({"type": "post", "title": title, "body": body, "community": community, "date": date, "page_number": page_number, "target_url": urljoin(raw_url, target.get("href", "")) if target else ""})
    return result


def _generic_activity(soup, page_number):
    activities, seen_nodes = [], set()
    selectors = {
        "comment": ("[data-comment-id]", "article.comment", ".comment-item", ".user-comment", "[itemprop='comment']"),
        "post": ("[data-post-id]", "article.post", ".post-item", ".user-post", "[itemtype*='DiscussionForumPosting']"),
    }
    for kind, kind_selectors in selectors.items():
        for selector in kind_selectors:
            for node in soup.select(selector):
                identity = id(node)
                if identity in seen_nodes:
                    continue
                seen_nodes.add(identity)
                body = _node_text(node.select_one(".body, .content, [itemprop='text']") or node)
                title = _node_text(node.select_one(".title, [itemprop='headline']"))
                if body or title:
                    target = node.select_one("a[href]")
                    activities.append({"type": kind, "title": title, "body": body, "community": "", "date": "", "page_number": page_number, "target_url": target.get("href", "") if target else ""})
    return activities


class ProfileHTMLParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.stack = []
        self.avatar_url = ""
        self.contacts = []
        self.candidates = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        marker = " ".join((values.get("id", ""), values.get("class", ""), values.get("itemprop", ""))).lower()
        kind = ""
        if any(word in marker for word in ("comment", "reply")):
            kind = "comment"
        elif any(word in marker for word in ("post", "message", "activity", "submission")):
            kind = "post"
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append({"tag": tag, "kind": kind, "text": []})
        if tag == "img" and not self.avatar_url:
            image_marker = marker + " " + values.get("alt", "").lower()
            if any(word in image_marker for word in ("avatar", "profile", "userpic", "portrait")):
                self.avatar_url = urljoin(self.base_url, values.get("src", ""))
        if tag == "a":
            href = values.get("href", "")
            if href.lower().startswith(("mailto:", "xmpp:", "jabber:")) or "t.me/" in href.lower() or "telegram.me/" in href.lower():
                self.contacts.append(href)

    def handle_endtag(self, tag):
        if not self.stack:
            return
        item = self.stack.pop()
        value = " ".join(" ".join(item["text"]).split())
        if item["kind"] and value:
            self.candidates.append((item["kind"], value))
        if self.stack and value:
            self.stack[-1]["text"].append(value)

    def handle_data(self, data):
        if self.stack and data.strip():
            self.stack[-1]["text"].append(data.strip())


class ProfileAnalyzer:
    def __init__(self, database_path="databases/profiles.db"):
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.database = sqlite3.connect(database_path, timeout=30)
        # Docker Desktop bind mounts on Windows do not reliably share SQLite WAL
        # state across containers. Rollback journaling keeps the API reader and
        # analysis worker on one portable database file.
        self.database.execute("PRAGMA journal_mode=DELETE")
        self.database.execute("PRAGMA busy_timeout=30000")
        self.database.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_url TEXT UNIQUE NOT NULL,
                source_engine TEXT,
                source_domain TEXT,
                username TEXT,
                display_name TEXT,
                role TEXT,
                territory TEXT,
                joined_at TEXT,
                last_active TEXT,
                reputation TEXT,
                bio TEXT,
                avatar_url TEXT,
                contacts_json TEXT,
                pgp_identifiers_json TEXT,
                wallets_json TEXT,
                posts_json TEXT,
                comments_json TEXT,
                ner_entities_json TEXT,
                profile_text TEXT,
                raw_html TEXT,
                detection_method TEXT,
                detection_confidence REAL DEFAULT 0,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                crawled_at TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_profiles_username ON profiles(username);
            CREATE INDEX IF NOT EXISTS idx_profiles_domain ON profiles(source_domain);
            CREATE INDEX IF NOT EXISTS idx_profiles_seen ON profiles(last_seen);
            CREATE TABLE IF NOT EXISTS profile_scan_state (
                source_engine TEXT PRIMARY KEY,
                last_page_id INTEGER DEFAULT 0,
                rescan_requested BOOLEAN DEFAULT 0,
                updated_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS profile_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_url TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                observed_at TIMESTAMP,
                UNIQUE(profile_url, content_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_profile_snapshots_url ON profile_snapshots(profile_url, observed_at);
            CREATE TABLE IF NOT EXISTS profile_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_url TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                title TEXT,
                body TEXT,
                community TEXT,
                date_label TEXT,
                source_page_url TEXT,
                target_url TEXT,
                page_number INTEGER DEFAULT 1,
                position INTEGER DEFAULT 0,
                content_hash TEXT NOT NULL,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                UNIQUE(profile_url, activity_type, content_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_profile_activity_owner ON profile_activity(profile_url, activity_type, page_number, position);
        """)
        try:
            self.database.execute("ALTER TABLE profile_scan_state ADD COLUMN rescan_requested BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            self.database.execute("ALTER TABLE profile_activity ADD COLUMN target_url TEXT")
        except sqlite3.OperationalError:
            pass
        self.database.commit()

    def analyze_and_save(self, url, html, text, engine, entities=None):
        profile = self.extract(url, html or "", text or "", engine, entities or {})
        if not profile:
            return None
        now = datetime.now(timezone.utc).isoformat()
        self.database.execute(
            "DELETE FROM profiles WHERE profile_url LIKE ? AND profile_url <> ?",
            (profile["profile_url"] + "?%", profile["profile_url"]),
        )
        self.database.execute("""
            INSERT INTO profiles (
                profile_url,source_engine,source_domain,username,display_name,role,territory,
                joined_at,last_active,reputation,bio,avatar_url,contacts_json,pgp_identifiers_json,
                wallets_json,posts_json,comments_json,ner_entities_json,profile_text,raw_html,
                detection_method,detection_confidence,first_seen,last_seen,crawled_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_url) DO UPDATE SET
                source_engine=excluded.source_engine,
                username=CASE WHEN excluded.username<>'' THEN excluded.username ELSE profiles.username END,
                display_name=CASE WHEN excluded.display_name<>'' THEN excluded.display_name ELSE profiles.display_name END,
                role=CASE WHEN excluded.role<>'' THEN excluded.role ELSE profiles.role END,
                territory=CASE WHEN excluded.territory<>'' THEN excluded.territory ELSE profiles.territory END,
                joined_at=CASE WHEN excluded.joined_at<>'' THEN excluded.joined_at ELSE profiles.joined_at END,
                last_active=CASE WHEN excluded.last_active<>'' THEN excluded.last_active ELSE profiles.last_active END,
                reputation=CASE WHEN excluded.reputation<>'' THEN excluded.reputation ELSE profiles.reputation END,
                bio=CASE WHEN excluded.bio<>'' THEN excluded.bio ELSE profiles.bio END,
                avatar_url=CASE WHEN excluded.avatar_url<>'' THEN excluded.avatar_url ELSE profiles.avatar_url END,
                contacts_json=excluded.contacts_json,pgp_identifiers_json=excluded.pgp_identifiers_json,
                wallets_json=excluded.wallets_json,posts_json=excluded.posts_json,
                comments_json=excluded.comments_json,ner_entities_json=excluded.ner_entities_json,
                profile_text=excluded.profile_text,raw_html=excluded.raw_html,
                detection_method=excluded.detection_method,detection_confidence=excluded.detection_confidence,
                last_seen=excluded.last_seen,crawled_at=excluded.crawled_at
        """, (
            profile["profile_url"], profile["source_engine"], profile["source_domain"],
            profile["username"], profile["display_name"], profile["role"], profile["territory"],
            profile["joined_at"], profile["last_active"], profile["reputation"], profile["bio"],
            profile["avatar_url"], json.dumps(profile["contacts"]), json.dumps(profile["pgp_identifiers"]),
            json.dumps(profile["wallets"]), json.dumps(profile["posts"]), json.dumps(profile["comments"]),
            json.dumps(profile["ner_entities"]), profile["profile_text"], profile["raw_html"],
            profile["detection_method"], profile["detection_confidence"], now, now, now,
        ))
        for position, activity in enumerate(profile.pop("activities", [])):
            activity_hash = hashlib.sha256(json.dumps({
                "type": activity["type"], "title": activity.get("title", ""),
                "body": activity.get("body", ""), "community": activity.get("community", ""),
            }, sort_keys=True).encode("utf-8")).hexdigest()
            self.database.execute("""
                INSERT INTO profile_activity(
                    profile_url,activity_type,title,body,community,date_label,source_page_url,
                    target_url,page_number,position,content_hash,first_seen,last_seen
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(profile_url,activity_type,content_hash) DO UPDATE SET
                    date_label=excluded.date_label,source_page_url=excluded.source_page_url,
                    target_url=excluded.target_url,
                    page_number=MIN(profile_activity.page_number,excluded.page_number),
                    position=MIN(profile_activity.position,excluded.position),last_seen=excluded.last_seen
            """, (
                profile["profile_url"], activity["type"], activity.get("title", ""),
                activity.get("body", ""), activity.get("community", ""), activity.get("date", ""),
                url, activity.get("target_url", ""), activity.get("page_number", 1), position, activity_hash, now, now,
            ))
        activities = self.database.execute("""
            SELECT activity_type,title,body,community,date_label
            FROM profile_activity WHERE profile_url=?
            ORDER BY page_number ASC,position ASC
        """, (profile["profile_url"],)).fetchall()
        profile["posts"] = _unique([
            _activity_text({"type": kind, "title": title, "body": body, "community": community, "date": date})
            for kind, title, body, community, date in activities if kind == "post"
        ], 500)
        profile["comments"] = _unique([
            _activity_text({"type": kind, "title": title, "body": body, "community": community, "date": date})
            for kind, title, body, community, date in activities if kind == "comment"
        ], 500)
        self.database.execute(
            "UPDATE profiles SET posts_json=?,comments_json=? WHERE profile_url=?",
            (json.dumps(profile["posts"]), json.dumps(profile["comments"]), profile["profile_url"]),
        )
        snapshot = json.dumps({
            "role": profile["role"], "territory": profile["territory"],
            "joined_at": profile["joined_at"], "last_active": profile["last_active"],
            "reputation": profile["reputation"], "contacts": profile["contacts"],
            "pgp_identifiers": profile["pgp_identifiers"], "wallets": profile["wallets"],
            "posts": profile["posts"], "comments": profile["comments"],
        }, sort_keys=True, ensure_ascii=False)
        self.database.execute("""
            INSERT OR IGNORE INTO profile_snapshots(profile_url,content_hash,snapshot_json,observed_at)
            VALUES(?,?,?,?)
        """, (profile["profile_url"], hashlib.sha256(snapshot.encode("utf-8")).hexdigest(), snapshot, now))
        self.database.commit()
        return profile

    def process_database(self, engine, source_path, limit=150):
        last_row = self.database.execute(
            "SELECT last_page_id, COALESCE(rescan_requested, 0) FROM profile_scan_state WHERE source_engine = ?", (engine,)
        ).fetchone()
        last_id = last_row[0] if last_row else 0
        if last_row and last_row[1]:
            last_id = 0
            self.database.execute(
                "UPDATE profile_scan_state SET last_page_id=0,rescan_requested=0,updated_at=? WHERE source_engine=?",
                (datetime.now(timezone.utc).isoformat(), engine),
            )
            self.database.commit()
            print(f"[PROFILE-RESCAN] {engine}: rebuilding profiles from stored pages")
        source = sqlite3.connect(source_path, timeout=30)
        source.execute("PRAGMA busy_timeout=30000")
        try:
            pages = source.execute("""
                SELECT id, url, COALESCE(html_content, ''), COALESCE(content, '')
                FROM pages WHERE is_active = 1 AND id > ?
                ORDER BY id ASC LIMIT ?
            """, (last_id, limit)).fetchall()
            profiles_found = 0
            for page_id, url, html, text in pages:
                entities = {}
                try:
                    row = source.execute(
                        "SELECT persons,organizations,locations,dates,money FROM ner_results WHERE page_id=?",
                        (page_id,),
                    ).fetchone()
                    if row:
                        entities = dict(zip(("persons", "organizations", "locations", "dates", "money"), (json.loads(value or "[]") for value in row)))
                except (sqlite3.OperationalError, json.JSONDecodeError):
                    pass
                if self.analyze_and_save(url, html, text, engine, entities):
                    profiles_found += 1
                self.database.execute("""
                    INSERT INTO profile_scan_state(source_engine,last_page_id,rescan_requested,updated_at) VALUES(?,?,0,?)
                    ON CONFLICT(source_engine) DO UPDATE SET last_page_id=excluded.last_page_id,rescan_requested=0,updated_at=excluded.updated_at
                """, (engine, page_id, datetime.now(timezone.utc).isoformat()))
            self.database.commit()
            return len(pages), profiles_found
        finally:
            source.close()

    def extract(self, url, html, text, engine, entities):
        parsed_url = urlparse(url)
        path_match = PROFILE_PATH.search(parsed_url.path)
        confidence = 0.62 if path_match else 0.0
        methods = ["url-pattern"] if path_match else []
        username = path_match.group(1).strip("@") if path_match else ""
        soup = BeautifulSoup(html, "html.parser")
        clean_text = " ".join(text.split())
        if not username:
            match = USERNAME.search(clean_text)
            username = match.group(1) if match else ""
        fields = {}
        for name, pattern in LABELED_FIELDS.items():
            match = pattern.search(clean_text)
            fields[name] = " ".join(match.group(1).split())[:200] if match else ""
        lower = clean_text.lower()
        for signal in ("send message", "last active", "joined", "member since", "reputation", "territory:", "user:", "username:", "vendor", "customer"):
            if signal in lower:
                confidence += 0.055
        is_tenebris = "tenebris.css" in html.lower() or bool(soup.select_one("#user-main"))
        tenebris = _tenebris_profile(soup, url, username) if is_tenebris else None
        if is_tenebris and not tenebris:
            return None
        query = parse_qs(parsed_url.query)
        try:
            page_number = max(1, int(query.get("page", ["1"])[0]))
        except ValueError:
            page_number = 1
        activities = tenebris["activities"] if tenebris else _generic_activity(soup, page_number)
        if tenebris:
            username = tenebris["username"] or username
            fields["role"] = tenebris["role"] or fields["role"]
            fields["joined_at"] = tenebris["joined_at"] or fields["joined_at"]
            fields["reputation"] = tenebris["reputation"] or fields["reputation"]
            confidence = max(confidence, 0.96)
            methods.append("tenebris-dom")
        avatar = tenebris["avatar_url"] if tenebris else ""
        if not avatar:
            avatar_node = soup.select_one("img.avatar, img[class*='avatar'], .avatar img, #user-image img")
            if avatar_node and avatar_node.get("src"):
                avatar = urljoin(url, avatar_node["src"])
        contacts = [
            anchor.get("href", "")
            for anchor in soup.select("a[href]")
            if anchor.get("href", "").lower().startswith(("mailto:", "xmpp:", "jabber:"))
            or "t.me/" in anchor.get("href", "").lower()
            or "telegram.me/" in anchor.get("href", "").lower()
        ]
        if avatar:
            confidence += 0.06
        if activities:
            confidence += 0.08
        if confidence < 0.58:
            return None
        focused_text = clean_text
        if tenebris:
            focused_text = " ".join(filter(None, (
                _node_text(soup.select_one("#user-main")),
                _node_text(soup.select_one(".messages")),
            )))
        posts = [_activity_text(activity) for activity in activities if activity["type"] == "post"]
        comments = [_activity_text(activity) for activity in activities if activity["type"] == "comment"]
        return {
            "profile_url": _canonical_profile_url(url),
            "source_engine": engine,
            "source_domain": parsed_url.hostname or "",
            "username": username,
            "display_name": username,
            "role": fields["role"],
            "territory": fields["territory"],
            "joined_at": fields["joined_at"],
            "last_active": fields["last_active"],
            "reputation": fields["reputation"],
            "bio": "",
            "avatar_url": avatar,
            "contacts": _unique(contacts + EMAIL.findall(focused_text), 50),
            "pgp_identifiers": _unique(PGP.findall(focused_text), 25),
            "wallets": _unique(BTC.findall(focused_text) + ETH.findall(focused_text) + XMR.findall(focused_text), 50),
            "posts": _unique(posts, 500),
            "comments": _unique(comments, 500),
            "activities": activities,
            "ner_entities": entities,
            "profile_text": focused_text,
            "raw_html": html,
            "detection_method": "+".join(dict.fromkeys(methods + ["html-signals"])),
            "detection_confidence": min(confidence, 0.99),
        }

    def close(self):
        self.database.close()
