
import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import joblib
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


PROFILE_ROUTE = re.compile(
    r"/(?:!userinfo|u|user|users|profile|profiles|member|members|vendor|vendors|seller|sellers)/([^/?#]+)",
    re.I,
)
EMAIL = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
PGP_FINGERPRINT = re.compile(r"\b(?:[A-F0-9]{4}[\s:-]?){4,10}\b", re.I)
PGP_BLOCK = re.compile(r"-----BEGIN PGP PUBLIC KEY BLOCK-----.*?-----END PGP PUBLIC KEY BLOCK-----", re.I | re.S)
BTC = re.compile(r"\b(?:bc1[a-zA-HJ-NP-Z0-9]{25,62}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
XMR = re.compile(r"\b[48][0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b")
DATE = re.compile(
    r"\b(?:created|posted|joined|registered|last seen|last active|member since)?\s*:?[ ]*"
    r"((?:\d{1,2}[./-]){2}\d{2,4}(?:[ ,T]+\d{1,2}:\d{2}(?::\d{2})?)?)",
    re.I,
)


PAGE_TRAINING = {
    "profile": [
        "/u/alice profile avatar joined reputation last seen send message",
        "/!userinfo/bob statistics for bob has written posts profile_avatar user_stat",
        "/member/carol about member registered messages reaction score",
        "/vendor/delta vendor profile trust rating pgp feedback",
    ],
    "thread": [
        "/topic/title thread post author created reply quote article post_text",
        "/forums/topic.12 discussion message user_name timestamp replies",
        "/board/thread.php?id=2 original post comments participants pagination",
        "thread_caption multi_content post_info user_info article",
    ],
    "listing": [
        "/forums categories topics latest posts pagination thread list",
        "/search results query users topics pages",
        "/members registered users member list",
        "board index forum rows topic listing next page",
    ],
    "marketplace": [
        "/market listing product vendor price escrow feedback buy",
        "/product/item offer cryptocurrency cart shipping stock",
        "marketplace category products sellers deals rating",
        "vendor shop listings orders price btc xmr",
    ],
    "login": [
        "/login username password sign in forgot password csrf",
        "/register create account captcha email password",
        "authentication two factor login form remember me",
        "access denied sign in required session",
    ],
    "other": [
        "/about privacy contact static page information",
        "/rules terms faq help documentation",
        "error not found unavailable maintenance",
        "homepage welcome navigation news links",
    ],
}

BLOCK_TRAINING = {
    "profile_header": [
        "user_profile avatar username joined reputation bio user_stat",
        "member-card profile-header display-name last-active",
        "vendor-profile trust rating pgp contact",
    ],
    "post": [
        "post original-post article author created post_info thread starter",
        "message first-message topic-body headline author timestamp",
        "submission post-content user_name permalink",
    ],
    "reply": [
        "comment reply response author timestamp comment-body",
        "post message quoted reply_to user_name created",
        "reaction comment-item nested-comment author date",
    ],
    "metadata": [
        "statistics joined last seen reputation posts count role location",
        "user_stat member since activity score rank",
        "profile fields territory trust feedback",
    ],
    "navigation": [
        "navigation menu footer breadcrumbs pagination tags sidebar",
        "header navbar categories login register search",
        "page links next previous home forum",
    ],
    "content": [
        "article text content paragraph information body",
        "main section description details",
        "document prose content",
    ],
}


def _compact(value, limit=12000):
    return " ".join(str(value or "").split())[:limit]


def _unique(values, limit=100):
    result, seen = [], set()
    for value in values:
        value = _compact(value, 8000)
        key = value.casefold()
        if len(value) < 2 or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= limit:
            break
    return result


class BootstrapClassifier:
    """Small persisted classifier that can later be replaced by a fine-tuned checkpoint."""

    def __init__(self, path: Path, examples: dict[str, list[str]]) -> None:
        self.path = path
        self.examples = examples
        self.model = self._load_or_train()

    def _load_or_train(self):
        if self.path.exists():
            try:
                payload = joblib.load(self.path)
                if payload.get("version") == 2:
                    return payload["model"]
            except Exception:
                pass
        texts, labels = [], []
        for label, samples in self.examples.items():
            texts.extend(samples)
            labels.extend([label] * len(samples))
        model = Pipeline([
            ("vectorizer", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)),
            ("classifier", LogisticRegression(max_iter=1200, class_weight="balanced", random_state=42)),
        ])
        model.fit(texts, labels)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"version": 2, "model": model}, self.path)
        return model

    def probabilities(self, text: str) -> dict[str, float]:
        probabilities = self.model.predict_proba([text])[0]
        return dict(zip(self.model.classes_, (float(value) for value in probabilities)))


@dataclass
class ForumBlock:
    block_id: str
    block_type: str
    author: str = ""
    author_url: str = ""
    title: str = ""
    body: str = ""
    date: str = ""
    permalink: str = ""
    parent_id: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class ForumDocument:
    url: str
    page_type: str
    page_confidence: float
    page_probabilities: dict[str, float]
    evidence: list[str]
    username: str = ""
    profile_url: str = ""
    profile_fields: dict = field(default_factory=dict)
    identifiers: dict = field(default_factory=dict)
    blocks: list[ForumBlock] = field(default_factory=list)
    discovered_profiles: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class ForumUnderstandingEngine:
    def __init__(self, model_dir: str | Path | None = None) -> None:
        root = Path(model_dir) if model_dir else Path(__file__).resolve().parents[1] / "models"
        self.page_model = BootstrapClassifier(root / "forum_page_classifier.joblib", PAGE_TRAINING)
        self.block_model = BootstrapClassifier(root / "forum_block_classifier.joblib", BLOCK_TRAINING)

    @staticmethod
    def canonical_profile_url(url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        clean_query = ""
        if not PROFILE_ROUTE.search(parsed.path) and query.get("user"):
            clean_query = "user=" + query["user"][0]
        return parsed._replace(path=parsed.path.rstrip("/") or "/", query=clean_query, fragment="").geturl()

    @staticmethod
    def _dom_signature(soup: BeautifulSoup, url: str, text: str) -> str:
        markers = []
        for node in soup.select("[id], [class]")[:500]:
            markers.append(str(node.get("id", "")))
            markers.extend(node.get("class", []))
        title = _compact(soup.title.get_text(" ", strip=True) if soup.title else "", 500)
        return _compact(f"{urlparse(url).path} {title} {' '.join(markers)} {text[:5000]}", 18000)

    @staticmethod
    def _rule_page_scores(url: str, soup: BeautifulSoup, text: str):
        path = urlparse(url).path.lower()
        title = (soup.title.get_text(" ", strip=True) if soup.title else "").lower()
        scores = {label: 0.0 for label in PAGE_TRAINING}
        evidence = []
        if PROFILE_ROUTE.search(path):
            scores["profile"] += 0.9
            evidence.append("profile-route")
        if "/!userinfo/" in path or soup.select_one(".user_profile, #user-main, [itemtype*='Person']"):
            scores["profile"] += 0.9
            evidence.append("profile-dom")
        if "profile for:" in title or re.search(r"\b(?:statistics for|member since|last seen)\b", text, re.I):
            scores["profile"] += 0.55
            evidence.append("profile-text")
        post_nodes = soup.select(".post, article.post, article.comment, .message, [data-post-id], [data-comment-id]")
        if post_nodes:
            scores["thread"] += min(1.2, 0.45 + len(post_nodes) * 0.08)
            evidence.append(f"discussion-blocks:{len(post_nodes)}")
        if soup.select_one(".thread_caption, .thread, [itemtype*='DiscussionForumPosting']"):
            scores["thread"] += 0.45
            evidence.append("thread-dom")
        if soup.select_one("input[type='password']"):
            scores["login"] += 1.0
            evidence.append("password-form")
        if soup.select_one(".product, .listing, [itemtype*='Product']"):
            scores["marketplace"] += 0.8
            evidence.append("marketplace-dom")
        if re.search(r"/(?:search|forums?|boards?|members?|users?)(?:/|$)", path):
            scores["listing"] += 0.45
            evidence.append("listing-route")
        return scores, evidence

    def classify_page(self, url: str, soup: BeautifulSoup, text: str):
        probabilities = self.page_model.probabilities(self._dom_signature(soup, url, text))
        rule_scores, evidence = self._rule_page_scores(url, soup, text)
        combined = {
            label: probabilities.get(label, 0.0) * 0.45 + min(1.0, rule_scores[label]) * 0.55
            for label in PAGE_TRAINING
        }
        label = max(combined, key=combined.get)
        confidence = combined[label]
        if confidence < 0.34:
            label = "other"
        normalized = sum(combined.values()) or 1.0
        return label, min(0.99, confidence), {key: round(value / normalized, 4) for key, value in combined.items()}, evidence

    @staticmethod
    def _extract_identifiers(text: str, soup: BeautifulSoup) -> dict:
        contacts = [
            node.get("href", "") for node in soup.select("a[href]")
            if node.get("href", "").lower().startswith(("mailto:", "xmpp:", "jabber:"))
            or "t.me/" in node.get("href", "").lower()
            or "telegram.me/" in node.get("href", "").lower()
        ]
        return {
            "emails": _unique(EMAIL.findall(text), 50),
            "contacts": _unique(contacts, 50),
            "pgp_fingerprints": _unique(PGP_FINGERPRINT.findall(text), 25),
            "pgp_blocks": _unique(PGP_BLOCK.findall(text), 5),
            "wallets": _unique(BTC.findall(text) + ETH.findall(text) + XMR.findall(text), 50),
        }

    @staticmethod
    def _author(node, url):
        anchor = node.select_one(
            "a.user_name[href], a.username[href], .author a[href], .creator a[href], "
            "a[href*='/!userinfo/'], a[href*='/u/'], a[href*='/profile/'], a[href*='/member/']"
        )
        if not anchor:
            return "", ""
        return _compact(anchor.get_text(" ", strip=True), 128).lstrip("@"), urljoin(url, anchor.get("href", ""))

    def _classify_block(self, node, default="content"):
        marker = " ".join([node.name or "", str(node.get("id", "")), " ".join(node.get("class", [])), _compact(node.get_text(" ", strip=True), 1600)])
        probabilities = self.block_model.probabilities(marker)
        label = max(probabilities, key=probabilities.get)
        confidence = probabilities[label]
        return (label if confidence >= 0.30 else default), confidence

    def _asmbb_profile(self, soup: BeautifulSoup, url: str):
        panel = soup.select_one(".user_profile")
        if not panel:
            return None
        heading = panel.select_one(".user_desc h1") or panel.select_one("h1")
        username = _compact(heading.get_text(" ", strip=True) if heading else "", 128)
        avatar = panel.select_one("img.profile_avatar, img.avatar")
        stat_node = panel.select_one(".user_stat")
        statistics = _compact(stat_node.get_text(" ", strip=True) if stat_node else "")
        last_seen = ""
        match = re.search(r"last seen(?: on)?\s+(.+?)(?=\s+Can\b|\s+Has written\b|$)", statistics, re.I)
        if match:
            last_seen = _compact(match.group(1), 100)
        post_count = ""
        match = re.search(r"has written\s+(\d+)\s+posts?", statistics, re.I)
        if match:
            post_count = match.group(1)
        history = panel.select_one("a[href*='/!search/']")
        return {
            "username": username, "display_name": username,
            "avatar_url": urljoin(url, avatar.get("src", "")) if avatar else "",
            "last_active": last_seen, "post_count": post_count,
            "activity_url": urljoin(url, history.get("href", "")) if history else "",
            "profile_text": statistics, "adapter": "asmbb",
        }

    def _generic_profile(self, soup: BeautifulSoup, url: str, text: str):
        match = PROFILE_ROUTE.search(urlparse(url).path)
        username = match.group(1) if match else ""
        heading = soup.select_one(".username, .user-name, .member-name, .profile-name, h1")
        if heading and not username:
            username = _compact(heading.get_text(" ", strip=True), 128).lstrip("@")
        avatar = soup.select_one("img.profile_avatar, img.avatar, img[class*='avatar'], .avatar img, #user-image img")
        date = DATE.search(text)
        return {
            "username": username,
            "display_name": _compact(heading.get_text(" ", strip=True), 128) if heading else username,
            "avatar_url": urljoin(url, avatar.get("src", "")) if avatar else "",
            "last_active": date.group(1) if date else "", "profile_text": _compact(text),
            "adapter": "generic-dom-model",
        }

    def _asmbb_blocks(self, soup: BeautifulSoup, url: str):
        result = []
        nodes = soup.select(".multi_content > .post, div.post")
        parsed = urlparse(url)
        thread_segment = next(
            (segment for segment in reversed(parsed.path.split("/")) if re.search(r"\.\d+$", segment)),
            "",
        )
        canonical_thread = parsed._replace(
            path=f"/{thread_segment}/" if thread_segment else parsed.path,
            query="", fragment="",
        ).geturl()
        caption_node = soup.select_one(".thread_caption, h1")
        thread_title = _compact(caption_node.get_text(" ", strip=True) if caption_node else "", 500)
        for index, node in enumerate(nodes):
            author, author_url = self._author(node, url)
            body_node = node.select_one(".post_text article") or node.select_one("article") or node.select_one(".post_text")
            info_node = node.select_one(".last_edit")
            info = _compact(info_node.get_text(" ", strip=True) if info_node else "", 500)
            date_match = re.search(r"created\s+(.+?)(?=,?\s+read:|$)", info, re.I)
            raw_id = node.get("id") or hashlib.sha1(f"{url}:{index}:{author}".encode()).hexdigest()[:12]
            kind = "post" if index == 0 else "reply"
            result.append(ForumBlock(
                block_id=str(raw_id), block_type=kind, author=author, author_url=author_url,
                title=thread_title if index == 0 else "",
                body=_compact(body_node.get_text(" ", strip=True) if body_node else ""),
                date=_compact(date_match.group(1), 100) if date_match else "",
                permalink=f"{canonical_thread.split('#')[0]}#{raw_id}", parent_id="" if index == 0 else str(nodes[0].get("id", "")),
                confidence=0.99, evidence=["asmbb:.post", "author:.user_name", "body:article"],
            ))
        return result

    def _generic_blocks(self, soup: BeautifulSoup, url: str):
        selectors = (
            "[data-post-id], [data-comment-id], article.post, article.comment, .post-item, .comment-item, "
            ".message, .reply, [itemtype*='DiscussionForumPosting'], [itemprop='comment']"
        )
        result, accepted = [], []
        for node in soup.select(selectors):
            if any(parent in accepted for parent in node.parents):
                continue
            text = _compact(node.get_text(" ", strip=True))
            if len(text) < 12:
                continue
            label, confidence = self._classify_block(node)
            if label not in {"post", "reply"}:
                marker = " ".join(node.get("class", [])).lower()
                label = "reply" if "comment" in marker or "reply" in marker else "post"
            author, author_url = self._author(node, url)
            body_node = node.select_one("[itemprop='text'], .message-body, .post-body, .comment-body, .content, article") or node
            title_node = node.select_one("[itemprop='headline'], .title, h1, h2, h3")
            time_node = node.select_one("time, [datetime], .date, .timestamp, .created")
            anchor = node.select_one("a.permalink[href], a[href*='#']")
            raw_id = node.get("data-post-id") or node.get("data-comment-id") or node.get("id") or hashlib.sha1(f"{url}:{len(result)}:{text[:200]}".encode()).hexdigest()[:12]
            result.append(ForumBlock(
                block_id=str(raw_id), block_type=label, author=author, author_url=author_url,
                title=_compact(title_node.get_text(" ", strip=True), 500) if title_node else "",
                body=_compact(body_node.get_text(" ", strip=True) if body_node else text),
                date=_compact(time_node.get("datetime") or time_node.get_text(" ", strip=True), 100) if time_node else "",
                permalink=urljoin(url, anchor.get("href", "")) if anchor else f"{url.split('#')[0]}#{raw_id}",
                confidence=round(max(0.55, confidence), 4), evidence=["dom-block-model"],
            ))
            accepted.append(node)
        return result

    def analyze(self, url: str, html: str, text: str = "") -> ForumDocument:
        soup = BeautifulSoup(html or "", "html.parser")
        for node in soup.select("script, style, noscript, template"):
            node.decompose()
        visible = _compact(text or soup.get_text(" ", strip=True))
        page_type, confidence, probabilities, evidence = self.classify_page(url, soup, visible)
        document = ForumDocument(
            url=url, page_type=page_type, page_confidence=confidence,
            page_probabilities=probabilities, evidence=evidence,
            identifiers=self._extract_identifiers(visible, soup),
        )
        profile = self._asmbb_profile(soup, url) if "/!userinfo/" in urlparse(url).path.lower() else None
        if page_type == "profile":
            profile = profile or self._generic_profile(soup, url, visible)
            document.username = profile.get("username", "")
            document.profile_url = self.canonical_profile_url(url)
            document.profile_fields = profile
        if soup.select_one("link[href*='posts.css']") or soup.select_one(".multi_content > .post"):
            document.blocks = self._asmbb_blocks(soup, url)
            if document.blocks:
                document.page_type = "thread"
                document.page_confidence = max(document.page_confidence, 0.98)
                document.evidence.append("asmbb-thread-adapter")
        elif page_type in {"thread", "listing", "profile"}:
            document.blocks = self._generic_blocks(soup, url)
        profiles = []
        for anchor in soup.select("a[href]"):
            resolved = urljoin(url, anchor.get("href", ""))
            match = PROFILE_ROUTE.search(urlparse(resolved).path)
            if match:
                profiles.append({"username": match.group(1), "profile_url": self.canonical_profile_url(resolved)})
        for block in document.blocks:
            if block.author and block.author_url:
                profiles.append({"username": block.author, "profile_url": self.canonical_profile_url(block.author_url)})
        keyed = {(item["profile_url"].casefold(), item["username"].casefold()): item for item in profiles}
        document.discovered_profiles = list(keyed.values())[:500]
        return document
