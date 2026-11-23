"""Deterministic reranking of already-authorized evidence; never modifies originals."""
import re


def normalize(text):
    return re.sub(r"\s+", "", str(text or ""))


def section_label(section):
    text = str(section or "章节未知")
    match = re.match(r"第[零〇一二两三四五六七八九十百千万0-9]+[条章]", text)
    return match[0] if match else text[:60]


def display_groups(hits):
    """Merge exact adjacent overlap only for presentation; original hits stay intact."""
    groups = []
    for hit in hits:
        current = {**hit, "sourceChunkIds": [hit.get("chunkId")]}
        if groups:
            previous = groups[-1]
            if all(previous.get(k) == hit.get(k) for k in ("documentId", "revision")) and section_label(previous["section"]) == section_label(hit["section"]):
                a, b = previous["text"], hit["text"]
                overlap = next((n for n in range(min(len(a), len(b)), 19, -1) if a[-n:] == b[:n]), 0)
                if overlap:
                    previous["text"] = a + b[overlap:]
                    previous["sourceChunkIds"].append(hit.get("chunkId"))
                    continue
        groups.append(current)
    return groups


def rank_evidence(query, hits, limit=5):
    tokens = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2}", query))
    # Sliding Chinese bigrams retain phrases at arbitrary character boundaries.
    for run in re.findall(r"[\u4e00-\u9fff]+", query):
        tokens.update(run[i:i+2] for i in range(len(run)-1))
    ordered = sorted(hits, key=lambda h: (
        sum(token in h.get("text", "") or token in h.get("section", "") for token in tokens),
        h["score"],
        len(h.get("text", "")),
    ), reverse=True)
    selected, ids, texts = [], set(), set()
    for hit in ordered:
        # Standalone titles/chapter headings are metadata, not applicable clauses.
        if (hit.get("section") in {"标题", "目录"}
                or re.fullmatch(r"第[零一二三四五六七八九十百]+章[\s\u3000]*.{0,30}", hit.get("text", "").strip())):
            continue
        identity = (hit["documentId"], hit["revision"], hit.get("chunkId") or normalize(hit["text"]))
        text_key = (hit["documentId"], hit["revision"], normalize(hit["text"]))
        if identity in ids or text_key in texts:
            continue
        # Do not merge different articles merely because they share boilerplate.
        # A fully contained duplicate in the SAME section has no new legal text.
        if any(h["documentId"] == hit["documentId"] and h["revision"] == hit["revision"]
               and h["section"] == hit["section"] and normalize(hit["text"]) in normalize(h["text"])
               for h in selected):
            continue
        ids.add(identity)
        texts.add(text_key)
        selected = [h for h in selected if not (h["documentId"] == hit["documentId"]
                    and h["revision"] == hit["revision"] and h["section"] == hit["section"]
                    and normalize(h["text"]) in normalize(hit["text"]))]
        selected.append(hit)
    return selected[:min(max(limit, 1), 5)]
