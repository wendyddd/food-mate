"""
记忆条目相似合并与冲突消解。

规则：
- 仅当两条是同一事实的近义改写时才合并（保留较早创建的 id，内容去重拼接）
- 同类但主题不同（如喜欢吃辣 vs 喜欢吃酸）必须保持独立条目
- 同类且内容冲突 → 以 updated_at 较新的为准
- 短关键词句与长解释句描述同一事实时视为相似，合并时优先保留短词
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.memory_schema import MEMORY_CATEGORIES, MemoryEntry

# 相似度阈值：达到则视为「类似」
SIMILARITY_THRESHOLD = 0.55

# 否定/对立前缀（用于冲突检测）
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

# 分句分隔
_SPLIT_RE = re.compile(r"[;；。！？!\?\n]+|(?<=[,，])\s*|\s*[—–]\s+")

# 原子关键词拆分：仅按分号/换行，避免拆坏 Lidl/Aldi、逗号列举等
_ATOMIC_SPLIT_RE = re.compile(r"[;；]+|\n+")

# 括号说明
_PAREN_RE = re.compile(r"\([^)]*\)|（[^）]*）")

# 比较相似度前去掉的程度修饰（特别喜欢吃辣 → 喜欢吃辣）
_LEAD_MODIFIER_RE = re.compile(
    r"^(?:really|very|especially|particularly|pretty|"
    r"特别|非常|很|超|比较|有点儿|有点)\s*",
    re.IGNORECASE,
)

# 比较相似度前去掉的常见谓语前缀（避免 Prefers A ≈ Prefers B）
# 中文前缀不依赖空白；长前缀（喜欢吃）必须排在短前缀（喜欢）之前
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

# 去掉主题核心末尾的虚词/泛化名词，便于「辣」对齐「辣的」/「spicy food」
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
    去掉程度修饰、谓语前缀和泛化后缀后得到主题核心，用于相似度比较。

    例如「喜欢吃辣」→「辣」，「likes sour food」→「sour」，
    避免句式相同但对象不同的偏好被误判为同一条。

    参数:
        text (str): 原始或规范化前文本

    返回:
        str: 主题核心（仍含空白，供 normalize）
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
    将记忆正文拆成原子关键词事实（一张卡片一条）。

    仅按分号与换行拆分；不含分号的长句保持为一条，避免误拆。

    参数:
        content (str): 原始记忆正文

    返回:
        list[str]: 去重后的原子事实列表；无法拆分时返回单元素列表
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
        # 过短碎片（如拆坏的 "Aldi"）丢弃，除非整段原本就很短
        if len(cleaned) < 3:
            continue
        seen.add(key)
        facts.append(cleaned)

    return facts if facts else [raw]


def expand_multi_fact_entries(
    entries: list[MemoryEntry],
) -> tuple[list[MemoryEntry], bool]:
    """
    将含多个关键词的条目拆成多条（保留首条原 id，其余新生成 id）。

    参数:
        entries (list[MemoryEntry]): 原始条目

    返回:
        tuple[list[MemoryEntry], bool]: (拆分后列表, 是否有变更)
    """
    import secrets

    result: list[MemoryEntry] = []
    changed = False
    for entry in entries:
        facts = split_atomic_facts(entry.content)
        if len(facts) <= 1:
            # 仍规范化单条（去掉括号赘述）
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
    规范化记忆文本，便于相似度比较。

    参数:
        text (str): 原始内容

    返回:
        str: 小写、去空白后的文本
    """
    cleaned = (text or "").strip().lower()
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def _strip_elaboration(text: str) -> str:
    """
    去掉括号说明等修饰，便于短词与长句对齐。

    参数:
        text (str): 原始分句

    返回:
        str: 去掉修饰后的文本
    """
    return _PAREN_RE.sub("", text or "").strip()


def _memory_clauses(text: str) -> list[str]:
    """
    将记忆正文拆成规范化分句（去修饰、去空白）。

    参数:
        text (str): 原始内容

    返回:
        list[str]: 规范化分句列表
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
    计算短句列表被长句列表覆盖的比例（子串或模糊匹配）。

    参数:
        short_clauses (list[str]): 较短一方的分句
        long_clauses (list[str]): 较长一方的分句

    返回:
        float: 0~1 覆盖率
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
        # 短分句与某长分句足够相似也算命中
        best = max(
            (SequenceMatcher(None, clause, lc).ratio() for lc in long_clauses),
            default=0.0,
        )
        if best >= 0.72:
            hits += 1
    return hits / len(short_clauses)


def memory_similarity(a: str, b: str) -> float:
    """
    计算两条记忆文本的相似度（0~1）。

    先抽取主题核心再比较，因此「喜欢吃辣」与「喜欢吃酸的」会因核心
    「辣」vs「酸」而得到低分，不会被当成同一条。

    参数:
        a (str): 文本 A
        b (str): 文本 B

    返回:
        float: SequenceMatcher 比率；包含关系或分句高覆盖时提高得分
    """
    # 用去掉「Prefers/喜欢」等前缀后的主题比较，避免不同事实被误判为相似
    core_a, core_b = _core_topic(a), _core_topic(b)
    na, nb = normalize_memory_text(core_a), normalize_memory_text(core_b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    # 短文本被长文本包含时视为高度相似
    if na in nb or nb in na:
        ratio = max(ratio, 0.85)

    # 分句覆盖：短词条 vs 长解释
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
    去掉否定词后得到主题骨架，用于冲突对齐。

    参数:
        text (str): 原始内容

    返回:
        str: 去除否定后的规范化文本
    """
    stripped = _NEGATION_RE.sub("", text or "")
    return normalize_memory_text(stripped)


def is_memory_conflict(a: str, b: str) -> bool:
    """
    判断两条记忆是否冲突（同一主题但极性相反）。

    参数:
        a (str): 内容 A
        b (str): 内容 B

    返回:
        bool: 冲突则 True
    """
    if not (a or "").strip() or not (b or "").strip():
        return False
    # 先要求主题足够接近
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
    # 一方有否定、另一方没有 → 冲突；或双方都有否定但主题不同则不算
    return has_neg_a != has_neg_b


def is_same_memory_fact(a: str, b: str) -> bool:
    """
    判断两条记忆是否描述同一事实（近义改写或极性冲突）。

    用于区分「应合并/覆盖」与「应各自独立成条」。

    参数:
        a (str): 内容 A
        b (str): 内容 B

    返回:
        bool: 同一事实则 True；不同偏好（如辣 vs 酸）则 False
    """
    if not (a or "").strip() or not (b or "").strip():
        return False
    if is_memory_conflict(a, b):
        return True
    return memory_similarity(a, b) >= SIMILARITY_THRESHOLD


def merge_memory_contents(existing: str, incoming: str) -> str:
    """
    合并两条互补记忆内容，去重分句后拼接；同类长短句优先保留短关键词。

    参数:
        existing (str): 已有内容
        incoming (str): 新内容

    返回:
        str: 合并后的内容
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
        return a  # 短词已被长句覆盖 → 保留短词
    if nb in na:
        return b

    # 高覆盖时优先保留更短的关键词写法
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
        # 已有完全相同分句
        if key in keys:
            continue
        replaced = False
        for i, old_key in enumerate(keys):
            # 长句包含短句主题 → 保留更短的关键词句
            if old_key in key and old_key != key:
                replaced = True
                break
            if key in old_key and key != old_key:
                ordered[i] = clause
                keys[i] = key
                replaced = True
                break
            # 去修饰后相同 → 保留更短
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
    在同类条目中查找与给定内容最相似的一条。

    参数:
        entries (list[MemoryEntry]): 现有条目
        category (str): 分类
        content (str): 待比较内容
        threshold (float): 相似度阈值
        exclude_id (str | None): 排除的条目 ID

    返回:
        MemoryEntry | None: 最相似且超过阈值的条目，否则 None
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
    消解一对相似/冲突条目，返回应保留的单条。

    参数:
        older (MemoryEntry): 创建时间较早（或任意）的一条
        newer (MemoryEntry): 另一条

    返回:
        MemoryEntry: 合并或择优后的条目（保留较早 created_at 的 id）
    """
    # 按 updated_at 判定谁更新；相等则按 created_at
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
        # 来源跟最新一条
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
    先将多关键词条目拆成原子卡片，再对同类近义/冲突条目合并消解。

    不同事实（即使句式相似，如喜欢吃辣 vs 喜欢吃酸）不会被合并。

    参数:
        entries (list[MemoryEntry]): 原始条目列表
        threshold (float): 相似阈值

    返回:
        tuple[list[MemoryEntry], bool]: (消解后列表, 是否有变更)
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
        # 反复合并，直到没有可合并对
        while True:
            pair: tuple[int, int] | None = None
            best_sim = 0.0
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    sim = memory_similarity(group[i].content, group[j].content)
                    # 冲突即使相似度略低也处理（主题骨架接近）
                    conflict = is_memory_conflict(group[i].content, group[j].content)
                    if conflict and sim < threshold:
                        # 冲突时用较低阈值的主题相似度已在 is_memory_conflict 内判断
                        sim = max(sim, threshold)
                    if sim >= threshold and sim > best_sim:
                        best_sim = sim
                        pair = (i, j)
            if pair is None:
                break
            i, j = pair
            a, b = group[i], group[j]
            merged = resolve_pair(a, b)
            # 删掉原对，放入合并结果
            group = [e for k, e in enumerate(group) if k not in (i, j)]
            group.append(merged)
            changed = True
        result.extend(group)

    result.extend(extras)
    return result, changed
