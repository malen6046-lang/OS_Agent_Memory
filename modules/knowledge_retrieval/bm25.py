"""BM25Retriever — 中文分词 + BM25 评分。"""
from collections import defaultdict
import math


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(text):
        b = text[i].encode("utf-8", errors="ignore")
        if len(b) >= 3:
            tokens.append(text[i])
            if i + 1 < len(text):
                tokens.append(text[i : i + 2])
            i += 1
        elif b.isalpha():
            j = i + 1
            while j < len(text) and text[j].encode("utf-8", errors="ignore").isalpha():
                j += 1
            tok = text[i:j].lower()
            if len(tok) >= 2:
                tokens.append(tok)
            i = j
        else:
            i += 1
    return tokens


class BM25Retriever:
    def __init__(self, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self._docs: dict[str, dict] = {}
        self._tokens: dict[str, list[str]] = {}
        self._df: dict[str, int] = defaultdict(int)
        self._avgdl = 0.0

    def index(self, docs: list[dict]) -> None:
        for d in docs:
            did = d["doc_id"]
            text = d.get("text", "") or d.get("content_text", "")
            self._docs[did] = d
            self._tokens[did] = _tokenize(text)
            for tok in set(self._tokens[did]):
                self._df[tok] += 1
        if self._docs:
            self._avgdl = sum(len(t) for t in self._tokens.values()) / len(self._docs)

    def remove(self, doc_id: str) -> None:
        if doc_id not in self._docs:
            return
        for tok in set(self._tokens.get(doc_id, [])):
            self._df[tok] = max(0, self._df[tok] - 1)
        del self._docs[doc_id]
        del self._tokens[doc_id]

    def search(self, query: str, top_k: int = 10, filter_user_id: str | None = None,
               filter_status: str | None = "active") -> list[dict]:
        qtokens = _tokenize(query)
        if not qtokens or not self._docs:
            return []
        n = len(self._docs)
        scores: dict[str, float] = {}
        for did, doc in self._docs.items():
            if filter_user_id and doc.get("user_id", "") != filter_user_id:
                continue
            if filter_status and doc.get("status", "") != filter_status:
                continue
            tf: dict[str, int] = defaultdict(int)
            for t in self._tokens[did]:
                tf[t] += 1
            dl = len(self._tokens[did])
            score = 0.0
            for qt in set(qtokens):
                f = tf[qt]
                if f == 0:
                    continue
                df = self._df.get(qt, 0)
                idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
                score += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / max(self._avgdl, 1)))
            scores[did] = score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [{"doc_id": did, "score": s, "meta": dict(self._docs[did])} for did, s in ranked[:top_k]]
