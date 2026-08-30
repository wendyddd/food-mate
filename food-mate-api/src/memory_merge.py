"""
Similar-entry merge and conflict resolution for memory entries.

Rules:
- Merge only when two entries are near-paraphrases of the same fact
  (keep the earlier-created id; concatenate content after deduping clauses)
- Same category but different topics (e.g. likes spicy vs likes sour) must stay separate
- Same category and conflicting content → keep the one with newer updated_at
- A short keyword and a long explanation of the same fact count as similar;
  prefer the short wording when merging
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.memory_schema import MEMORY_CATEGORIES, MemoryEntry

# Similarity threshold: scores at or above this count as "similar"
SIMILARITY_THRESHOLD = 0.55

# Negation / opposing prefixes (for conflict detection)
_NEGATION_PATTERNS = (
    r"不(?:喜欢|爱|想|吃|用|做|能|要|含)",
    r"别(?:放|加|用)",
    r"避免",
    r"忌(?:口|食)?",
    r"过敏",
    r"讨厌",
    r"无(?:法|需)",
    r"少(?:放|用|油|盐|糖)",
    r"\b(?:no|not|never|avoid|dislike|hate|allergic|without|less)\b",
    r"can't|cannot|won't|doesn't",
)

_NEGATION_RE = re.compile("|".join(_NEGATION_PATTERNS), re.IGNORECASE)

# Clause split delimiters
_SPLIT_RE = re.compile(r"[;；。！？!\?\n]+|(?<=[,，])\s*|\s*[—–]\s+")

# Atomic keyword split: semicolon/newline only, to avoid breaking Lidl/Aldi or comma lists
_ATOMIC_SPLIT_RE = re.compile(r"[;；]+|\n+")

# Parenthetical notes
_PAREN_RE = re.compile(r"\([^)]*\)|（[^）]*）")

# Degree modifiers stripped before similarity compare (e.g. "really likes spicy" → "likes spicy")
_LEAD_MODIFIER_RE = re.compile(
    r"^(?:really|very|especially|particularly|pretty|"
    r"特别|非常|很|超|比较|有点儿|有点)\s*",
    re.IGNORECASE,
)

# Common predicate prefixes stripped before similarity compare (avoids Prefers A ≈ Prefers B)
# Chinese prefixes do not rely on whitespace; longer prefixes must come before shorter ones
_LEAD_PREFIX_RE = re.compile(
    r"^(?:"
    r"does\s+not\s+like|doesn't\s+like|"
    r"likes?\s+to\s+eat|likes?\s+eating|loves?\s+to\s+eat|loves?\s+eating|"
    r"aims?\s+for|cooks?(?:\s+for)?|"
    r"prefers?|likes?|loves?|wants?|needs?|usually|always|often|"
    r"dislikes?|hates?|avoids?|has|have|"
    r"不喜欢吃|不太喜欢|不爱吃|喜欢吃|爱吃|偏好吃|"
    r"不喜欢|喜欢|偏好|希望|需要|通常|总是|经常|避免|讨厌|"
    r"做饭给|有|吃"
    r")\s*",
    re.IGNORECASE,
)

# Strip trailing filler/generic nouns so "spicy" aligns with "spicy food"
_TRAILING_GENERIC_RE = re.compile(
    r"(?:"
    r"的东西|的食物|的食品|的菜肴|的菜|的口味|的味道|"
    r"食物|食品|菜肴|口味|味道|"
    r"\s+foods?|\s+dishes?|\s+flavou?rs?|\s+tastes?"
    r"|的|了"
    r")+$",
    re.IGNORECASE,
)


def _core_topic(text: str) -> str:
    """
    Strip degree modifiers, predicate prefixes, and generic suffixes to get a topic core
    for similarity comparison.

    Examples: "likes spicy food" → "spicy", "likes sour food" → "sour",
    so preferences with the same sentence pattern but different objects are not treated as one fact.

    Args:
        text (str): Original or pre-normalized text

    Returns:
        str: Topic core (may still contain whitespace, for normalize)
    """
    cleaned = _PAREN_RE.sub("", text or "").strip()
    prev = None
    while cleaned and cleaned != prev:
        prev = cleaned
        cleaned = _LEAD_MODIFIER_RE.sub("", cleaned).strip()
        cleaned = _LEAD_PREFIX_RE.sub("", cleaned).strip()
    stripped = _TRAILING_GENERIC_RE.sub("", cleaned).strip()
    if stripped:
        cleaned = stripped
    return cleaned or (text or "").strip()


def split_atomic_facts(content: str) -> list[str]:
    """
    Split memory content into atomic keyword facts (one fact per card).

    Split only on semicolons and newlines; long sentences without semicolons stay as one
    fact to avoid false splits.

    Args:
        content (str): Original memory content

    Returns:
        list[str]: Deduped atomic facts; a single-item list if it cannot be split
    """
    raw = (content or "").strip()
    if not raw:
        return []

    parts = [p.strip() for p in _ATOMIC_SPLIT_RE.split(raw) if p and p.strip()]

    seen: set[str] = set()
    facts: list[str] = []
    for part in parts:
        cleaned = _PAREN_RE.sub("", part).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"[,，.。;；:：!！?？]+$", "", cleaned).strip()
        if not cleaned:
            continue
        key = normalize_memory_text(cleaned)
        if not key or key in seen:
            continue
        # Drop fragments that are too short (e.g. a broken "Aldi"), unless the whole text was already short
        if len(cleaned) < 3:
            continue
        seen.add(key)
        facts.append(cleaned)

    return facts if facts else [raw]


def expand_multi_fact_entries(
    entries: list[MemoryEntry],
) -> tuple[list[MemoryEntry], bool]:
    """
    Split entries that contain multiple keywords (keep the original id on the first;
    generate new ids for the rest).

    Args:
        entries (list[MemoryEntry]): Original entries

    Returns:
        tuple[list[MemoryEntry], bool]: (split list, whether anything changed)
    """
    import secrets

    result: list[MemoryEntry] = []
    changed = False
    for entry in entries:
        facts = split_atomic_facts(entry.content)
        if len(facts) <= 1:
            # Still normalize a single fact (strip parenthetical elaboration)
            if facts and facts[0] != entry.content:
                changed = True
                result.append(
                    MemoryEntry(
                        id=entry.id,
                        category=entry.category,
                        content=facts[0],
                        created_at=entry.created_at,
                        updated_at=entry.updated_at,
                        source_type=entry.source_type,
                        source_session_id=entry.source_session_id,
                        source_quote=entry.source_quote,
                        revisions=list(entry.revisions or []),
                    )
                )
            else:
                result.append(entry)
            continue

        changed = True
        result.append(
            MemoryEntry(
                id=entry.id,
                category=entry.category,
                content=facts[0],
                created_at=entry.created_at,
                updated_at=entry.updated_at,
                source_type=entry.source_type,
                source_session_id=entry.source_session_id,
                source_quote=entry.source_quote,
                revisions=list(entry.revisions or []),
            )
        )
        for fact in facts[1:]:
            result.append(
                MemoryEntry(
                    id=f"mem_{secrets.token_hex(3)}",
                    category=entry.category,
                    content=fact,
                    created_at=entry.created_at,
                    updated_at=entry.updated_at,
                    source_type=entry.source_type,
                    source_session_id=entry.source_session_id,
                    source_quote=entry.source_quote,
                    revisions=[],
                )
            )
    return result, changed


def normalize_memory_text(text: str) -> str:
    """
    Normalize memory text for similarity comparison.

    Args:
        text (str): Original content

    Returns:
        str: Lowercased text with whitespace removed
    """
    cleaned = (text or "").strip().lower()
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def _strip_elaboration(text: str) -> str:
    """
    Strip parenthetical notes so short keywords can align with long sentences.

    Args:
        text (str): Original clause

    Returns:
        str: Text with decorations removed
    """
    return _PAREN_RE.sub("", text or "").strip()


def _memory_clauses(text: str) -> list[str]:
    """
    Split memory content into normalized clauses (strip decorations and whitespace).

    Args:
        text (str): Original content

    Returns:
        list[str]: Normalized clause list
    """
    parts = [p.strip() for p in _SPLIT_RE.split(text or "") if p and p.strip()]
    clauses: list[str] = []
    for part in parts or ([text.strip()] if (text or "").strip() else []):
        key = normalize_memory_text(_strip_elaboration(part))
        if key:
            clauses.append(key)
    return clauses


def _clause_coverage(short_clauses: list[str], long_clauses: list[str]) -> float:
    """
    Fraction of short clauses covered by the long-clause list (substring or fuzzy match).

    Args:
        short_clauses (list[str]): Clauses from the shorter side
        long_clauses (list[str]): Clauses from the longer side

    Returns:
        float: Coverage in 0~1
    """
    if not short_clauses:
        return 0.0
    long_blob = " ".join(long_clauses)
    hits = 0
    for clause in short_clauses:
        if not clause:
            continue
        if clause in long_blob or any(
            clause in lc or lc in clause for lc in long_clauses
        ):
            hits += 1
            continue
        # A short clause that is similar enough to a long clause also counts as a hit
        best = max(
            (SequenceMatcher(None, clause, lc).ratio() for lc in long_clauses),
            default=0.0,
        )
        if best >= 0.72:
            hits += 1
    return hits / len(short_clauses)


def memory_similarity(a: str, b: str) -> float:
    """
    Compute similarity of two memory texts (0~1).

    Topic cores are compared first, so "likes spicy" and "likes sour" score low
    because the cores are "spicy" vs "sour", and are not treated as the same fact.

    Args:
        a (str): Text A
        b (str): Text B

    Returns:
        float: SequenceMatcher ratio; boosted for containment or high clause coverage
    """
    # Compare topics after stripping prefixes like "prefers"/"likes", so different facts are not treated as similar
    core_a, core_b = _core_topic(a), _core_topic(b)
    na, nb = normalize_memory_text(core_a), normalize_memory_text(core_b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    # Short text contained in long text counts as highly similar
    if na in nb or nb in na:
        ratio = max(ratio, 0.85)

    # Clause coverage: short keyword vs long explanation
    ca, cb = _memory_clauses(core_a), _memory_clauses(core_b)
    if ca and cb:
        if len(na) <= len(nb):
            coverage = _clause_coverage(ca, cb)
        else:
            coverage = _clause_coverage(cb, ca)
        if coverage >= 0.6:
            ratio = max(ratio, 0.55 + 0.4 * coverage)

    return min(ratio, 1.0)


def _strip_negation(text: str) -> str:
    """
    Strip negation words to get a topic skeleton for conflict alignment.

    Args:
        text (str): Original content

    Returns:
        str: Normalized text with negation removed
    """
    stripped = _NEGATION_RE.sub("", text or "")
    return normalize_memory_text(stripped)


def is_memory_conflict(a: str, b: str) -> bool:
    """
    Decide whether two memories conflict (same topic, opposite polarity).

    Args:
        a (str): Content A
        b (str): Content B

    Returns:
        bool: True if they conflict
    """
    if not (a or "").strip() or not (b or "").strip():
        return False
    # Require the topics to be close enough first
    topic_a, topic_b = _strip_negation(a), _strip_negation(b)
    if not topic_a or not topic_b:
        return False
    topic_sim = SequenceMatcher(None, topic_a, topic_b).ratio()
    if topic_a in topic_b or topic_b in topic_a:
        topic_sim = max(topic_sim, 0.8)
    if topic_sim < 0.55:
        return False
    has_neg_a = bool(_NEGATION_RE.search(a))
    has_neg_b = bool(_NEGATION_RE.search(b))
    # One side negated and the other not → conflict; both negated with different topics does not count
    return has_neg_a != has_neg_b


def is_same_memory_fact(a: str, b: str) -> bool:
    """
    Decide whether two memories describe the same fact (near-paraphrase or polarity conflict).

    Used to distinguish "should merge/overwrite" from "should stay as separate entries".

    Args:
        a (str): Content A
        b (str): Content B

    Returns:
        bool: True if the same fact; False for different preferences (e.g. spicy vs sour)
    """
    if not (a or "").strip() or not (b or "").strip():
        return False
    if is_memory_conflict(a, b):
        return True
    return memory_similarity(a, b) >= SIMILARITY_THRESHOLD


def merge_memory_contents(existing: str, incoming: str) -> str:
    """
    Merge two complementary memory texts: dedupe clauses then join;
    for same-topic short vs long, prefer the short keyword.

    Args:
        existing (str): Existing content
        incoming (str): New content

    Returns:
        str: Merged content
    """
    a = (existing or "").strip()
    b = (incoming or "").strip()
    if not a:
        return b
    if not b:
        return a
    na, nb = normalize_memory_text(a), normalize_memory_text(b)
    if na == nb:
        return a if len(a) <= len(b) else b
    if na in nb:
        return a  # Short keyword already covered by the long sentence → keep the short one
    if nb in na:
        return b

    # On high coverage, prefer the shorter keyword wording
    ca, cb = _memory_clauses(a), _memory_clauses(b)
    if ca and cb:
        if len(na) <= len(nb) and _clause_coverage(ca, cb) >= 0.6:
            return a
        if len(nb) <= len(na) and _clause_coverage(cb, ca) >= 0.6:
            return b

    def _raw_clauses(text: str) -> list[str]:
        parts = [p.strip() for p in _SPLIT_RE.split(text) if p and p.strip()]
        return parts or [text.strip()]

    ordered: list[str] = []
    keys: list[str] = []
    for clause in _raw_clauses(a) + _raw_clauses(b):
        key = normalize_memory_text(_strip_elaboration(clause))
        if not key:
            continue
        # Identical clause already present
        if key in keys:
            continue
        replaced = False
        for i, old_key in enumerate(keys):
            # Long sentence contains the short-clause topic → keep the shorter keyword
            if old_key in key and old_key != key:
                replaced = True
                break
            if key in old_key and key != old_key:
                ordered[i] = clause
                keys[i] = key
                replaced = True
                break
            # Same after stripping decorations → keep the shorter one
            if key == old_key:
                if len(clause) < len(ordered[i]):
                    ordered[i] = clause
                replaced = True
                break
        if replaced:
            continue
        ordered.append(clause)
        keys.append(key)

    if not ordered:
        return b if len(b) <= len(a) else a
    joiner = "；" if any("\u4e00" <= ch <= "\u9fff" for ch in a + b) else "; "
    return joiner.join(ordered)


def find_similar_entry(
    entries: list[MemoryEntry],
    category: str,
    content: str,
    *,
    threshold: float = SIMILARITY_THRESHOLD,
    exclude_id: str | None = None,
) -> MemoryEntry | None:
    """
    Find the most similar same-category entry for the given content.

    Args:
        entries (list[MemoryEntry]): Existing entries
        category (str): Category
        content (str): Content to compare
        threshold (float): Similarity threshold
        exclude_id (str | None): Entry ID to exclude

    Returns:
        MemoryEntry | None: Most similar entry above the threshold, otherwise None
    """
    best: MemoryEntry | None = None
    best_score = 0.0
    for entry in entries:
        if entry.category != category:
            continue
        if exclude_id and entry.id == exclude_id:
            continue
        score = memory_similarity(entry.content, content)
        if score >= threshold and score > best_score:
            best_score = score
            best = entry
    return best


def resolve_pair(older: MemoryEntry, newer: MemoryEntry) -> MemoryEntry:
    """
    Resolve a similar/conflicting pair and return the single entry to keep.

    Args:
        older (MemoryEntry): The earlier-created entry (or either one)
        newer (MemoryEntry): The other entry

    Returns:
        MemoryEntry: Merged or preferred entry (keeps the earlier created_at id)
    """
    # Decide which is newer by updated_at; tie-break with created_at
    if newer.updated_at > older.updated_at or (
        newer.updated_at == older.updated_at and newer.created_at > older.created_at
    ):
        latest, other = newer, older
    else:
        latest, other = older, newer

    keep_id = older.id if older.created_at <= newer.created_at else newer.id
    keep_created = min(older.created_at, newer.created_at)

    if is_memory_conflict(older.content, newer.content):
        content = latest.content
        source_type = latest.source_type
        source_session_id = latest.source_session_id
        source_quote = latest.source_quote
    else:
        content = merge_memory_contents(other.content, latest.content)
        # Source follows the latest entry
        source_type = latest.source_type or other.source_type
        source_session_id = latest.source_session_id or other.source_session_id
        source_quote = latest.source_quote or other.source_quote

    return MemoryEntry(
        id=keep_id,
        category=older.category,
        content=content,
        created_at=keep_created,
        updated_at=max(older.updated_at, newer.updated_at),
        source_type=source_type,
        source_session_id=source_session_id,
        source_quote=source_quote,
        revisions=[*(older.revisions or []), *(newer.revisions or [])],
    )


def reconcile_entries(
    entries: list[MemoryEntry],
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[list[MemoryEntry], bool]:
    """
    Split multi-keyword entries into atomic cards, then merge/resolve similar or
    conflicting same-category entries.

    Distinct facts (even with similar sentence patterns, e.g. likes spicy vs likes sour)
    are not merged.

    Args:
        entries (list[MemoryEntry]): Original entry list
        threshold (float): Similarity threshold

    Returns:
        tuple[list[MemoryEntry], bool]: (resolved list, whether anything changed)
    """
    expanded, expand_changed = expand_multi_fact_entries(list(entries))
    if len(expanded) < 2:
        return expanded, expand_changed

    by_category: dict[str, list[MemoryEntry]] = {c: [] for c in MEMORY_CATEGORIES}
    extras: list[MemoryEntry] = []
    for e in expanded:
        if e.category in by_category:
            by_category[e.category].append(e)
        else:
            extras.append(e)

    result: list[MemoryEntry] = []
    changed = expand_changed

    for category in MEMORY_CATEGORIES:
        group = list(by_category[category])
        # Repeatedly merge until no mergeable pair remains
        while True:
            pair: tuple[int, int] | None = None
            best_sim = 0.0
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    sim = memory_similarity(group[i].content, group[j].content)
                    # Handle conflicts even if similarity is a bit low (topic skeletons are close)
                    conflict = is_memory_conflict(group[i].content, group[j].content)
                    if conflict and sim < threshold:
                        # For conflicts, topic closeness is already judged inside is_memory_conflict
                        sim = max(sim, threshold)
                    if sim >= threshold and sim > best_sim:
                        best_sim = sim
                        pair = (i, j)
            if pair is None:
                break
            i, j = pair
            a, b = group[i], group[j]
            merged = resolve_pair(a, b)
            # Drop the original pair and insert the merged result
            group = [e for k, e in enumerate(group) if k not in (i, j)]
            group.append(merged)
            changed = True
        result.extend(group)

    result.extend(extras)
    return result, changed
