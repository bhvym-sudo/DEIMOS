from __future__ import annotations

import csv
import html
import json
import math
import random
import re
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, precision_recall_fscore_support, roc_auc_score
from sklearn.preprocessing import StandardScaler

from .persona_intelligence import _stylometry

csv.field_size_limit(min(sys.maxsize, 1024 * 1024 * 1024))


TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


def clean(value: str) -> str:
    return SPACE.sub(" ", html.unescape(TAG.sub(" ", value or ""))).strip()


def cosine_rows(matrix, left: int, right: int) -> float:
    return float(matrix[left].multiply(matrix[right]).sum())


def train(root: Path, dataset: Path, maximum_authors: int = 1600) -> dict:
    user_path = dataset / "forum" / "user.tsv"
    post_path = dataset / "forum" / "post.tsv"
    latest_counts = {}
    with user_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            uid = row.get("uid", "")
            try: count = int(row.get("num_posts") or 0)
            except ValueError: count = 0
            if count >= 8:
                latest_counts[uid] = max(count, latest_counts.get(uid, 0))
    selected = set(sorted(latest_counts, key=lambda uid: (-latest_counts[uid], int(uid)))[:maximum_authors])
    posts = {uid: [] for uid in selected}
    with post_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            uid = row.get("uid", "")
            if uid not in posts or len(posts[uid]) >= 30:
                continue
            text = clean(row.get("text", ""))
            if len(text) >= 40 and text not in posts[uid]:
                posts[uid].append(text)
    authors = [uid for uid, values in posts.items() if len(values) >= 8]
    halves = []
    kept_authors = []
    for uid in authors:
        values = posts[uid]
        left, right = " ".join(values[::2]), " ".join(values[1::2])
        if min(len(left), len(right)) >= 500:
            kept_authors.append(uid)
            halves.extend((left[:60000], right[:60000]))
    if len(kept_authors) < 50:
        raise RuntimeError("Evolution dataset yielded too few authors with sufficient text")
    char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=12000, sublinear_tf=True)
    word_vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=7000, sublinear_tf=True, strip_accents="unicode")
    char_matrix = char_vectorizer.fit_transform(halves)
    word_matrix = word_vectorizer.fit_transform(halves)
    raw_behavior = np.asarray([_stylometry(text, [text], 1, 0) for text in halves])
    behavior = StandardScaler().fit_transform(raw_behavior)
    rng = random.Random(26151)
    kept_authors_original = list(kept_authors)
    shuffled_authors = list(kept_authors)
    rng.shuffle(shuffled_authors)
    split = int(len(shuffled_authors) * 0.8)

    def examples(author_ids):
        # Map the retained author order to its two document rows.
        retained = {uid: index for index, uid in enumerate(kept_authors_original)}
        positive, negative = [], []
        for uid in author_ids:
            index = retained[uid]
            positive.append((2 * index, 2 * index + 1, 1))
        shuffled = list(author_ids)
        rng.shuffle(shuffled)
        if any(a == b for a, b in zip(author_ids, shuffled)):
            shuffled = shuffled[1:] + shuffled[:1]
        for left_uid, right_uid in zip(author_ids, shuffled):
            negative.append((2 * retained[left_uid], 2 * retained[right_uid] + 1, 0))
        return positive + negative

    train_authors, test_authors = shuffled_authors[:split], shuffled_authors[split:]

    def feature_rows(pairs):
        rows, labels = [], []
        for left, right, label in pairs:
            style = cosine_rows(char_matrix, left, right)
            semantic = cosine_rows(word_matrix, left, right)
            distance = np.linalg.norm(behavior[left] - behavior[right])
            behavioral = math.exp(-distance / math.sqrt(behavior.shape[1]))
            reliability = min(1.0, math.sqrt(min(len(halves[left]), len(halves[right])) / 3000.0))
            rows.append([style, semantic, behavioral, reliability])
            labels.append(label)
        return np.asarray(rows), np.asarray(labels)

    x_train, y_train = feature_rows(examples(train_authors))
    x_test, y_test = feature_rows(examples(test_authors))
    classifier = LogisticRegression(C=0.7, class_weight="balanced", max_iter=1000, random_state=26151)
    classifier.fit(x_train, y_train)
    probabilities = classifier.predict_proba(x_test)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(y_test, predictions, average="binary", zero_division=0)
    metrics = {
        "dataset": "Evolution cryptomarket forum (Zenodo 10171217)",
        "authors": len(kept_authors), "training_pairs": len(y_train), "validation_pairs": len(y_test),
        "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 4),
        "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
        "precision": round(float(precision), 4), "recall": round(float(recall), 4),
        "f1": round(float(f1), 4), "brier": round(float(brier_score_loss(y_test, probabilities)), 4),
        "author_disjoint_validation": True,
    }
    output = root / "phobos" / "models" / "evolution_authorship_calibrator.joblib"
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"classifier": classifier, "metrics": metrics, "feature_order": ["stylometry", "semantic", "behavior", "reliability"]}, output, compress=3)
    return metrics


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--maximum-authors", type=int, default=1600)
    args = parser.parse_args()
    print(json.dumps(train(Path(args.root), Path(args.dataset), args.maximum_authors), indent=2))
