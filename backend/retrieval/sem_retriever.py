from __future__ import annotations

from typing import List, Optional

import numpy as np
import chromadb


def retrieve(
    collection: chromadb.Collection,
    query_text: str,
    k: int = 5,
    fetch_k: int = 20,
    lambda_mult: float = 0.5,
    where: Optional[dict] = None,
) -> List[dict]:
    """Return the top-k most relevant and diverse chunks using MMR reranking.

    Fetches fetch_k candidates by vector similarity, then applies Maximal
    Marginal Relevance to balance relevance (lambda_mult) against redundancy
    (1 - lambda_mult).  Returns dicts with keys: text, metadata, distance.
    """
    count = collection.count()
    if count == 0:
        return []

    n = min(fetch_k, count)
    kwargs: dict = {
        "query_texts": [query_text],
        "n_results": n,
        "include": ["embeddings", "documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    docs: List[str] = results["documents"][0]
    metas: List[dict] = results["metadatas"][0]
    distances: List[float] = results["distances"][0]
    raw_embs = results.get("embeddings") or [[]]
    embeddings: List[List[float]] = raw_embs[0] if raw_embs else []

    if not docs:
        return []

    # Convert L2 distances to [0,1] similarity scores (higher = more similar)
    query_sims = [1.0 / (1.0 + d) for d in distances]

    if len(embeddings) > 0:
        selected = _mmr(embeddings, query_sims, min(k, len(docs)), lambda_mult)
    else:
        # Embeddings unavailable — fall back to top-k by distance rank
        selected = list(range(min(k, len(docs))))

    return [
        {"text": docs[i], "metadata": metas[i], "distance": distances[i]}
        for i in selected
    ]


def _mmr(
    embeddings: List[List[float]],
    query_sims: List[float],
    k: int,
    lambda_mult: float,
) -> List[int]:
    """Return indices of k documents selected by Maximal Marginal Relevance.

    MMR score = lambda_mult * relevance - (1 - lambda_mult) * max_redundancy
    where relevance is similarity to the query and max_redundancy is the
    maximum cosine similarity to any already-selected document.
    """
    n = len(embeddings)
    if n == 0:
        return []

    embs = np.array(embeddings, dtype=float)          # (n, d)
    q_sims = np.array(query_sims, dtype=float)        # (n,)

    # Normalise for cosine similarity; avoid division by zero
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    embs_norm = embs / norms                           # (n, d) unit vectors

    selected: List[int] = []
    mask = np.ones(n, dtype=bool)

    for _ in range(min(k, n)):
        remaining = np.where(mask)[0]

        if not selected:
            best = int(remaining[np.argmax(q_sims[remaining])])
        else:
            sel_norm = embs_norm[selected]             # (s, d)
            rem_norm = embs_norm[remaining]            # (r, d)
            cos_to_sel = rem_norm @ sel_norm.T         # (r, s)
            max_redundancy = cos_to_sel.max(axis=1)    # (r,)
            mmr_scores = (
                lambda_mult * q_sims[remaining]
                - (1.0 - lambda_mult) * max_redundancy
            )
            best = int(remaining[np.argmax(mmr_scores)])

        selected.append(best)
        mask[best] = False

    return selected
