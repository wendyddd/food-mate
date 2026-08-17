"""
FoodMate 结构化记忆系统，以 user.json 为主存储，兼容 user.md 迁移与 Markdown 导出。
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from pathlib import Path

from src.config import MEMORY_DIR
from src.memory_merge import (
    find_similar_entry,
    is_memory_conflict,
    is_same_memory_fact,
    merge_memory_contents,
    reconcile_entries,
    split_atomic_facts,
)
from src.memory_schema import (
    EMPTY_PLACEHOLDERS,
    MEMORY_CATEGORIES,
    ApplyResult,
    MemoryEntry,
    MemoryOperation,
    MemoryRevision,
    MemorySourceContext,
    MemoryStore,
    normalize_category,
)

# 多用户记忆根目录：memory/users/{uid}/
USERS_DIR = MEMORY_DIR / "users"

# 按用户串行化读写，避免 Judge 与 Agent 工具并行写入产生重复条目
_STORE_LOCKS: dict[str, threading.Lock] = {}
_STORE_LOCKS_GUARD = threading.Lock()


def _uid_lock(uid: str) -> threading.Lock:
    """
    获取指定用户的记忆存储锁。

    参数:
        uid (str): 用户 ID

    返回:
        threading.Lock: 该用户的互斥锁
    """
    with _STORE_LOCKS_GUARD:
        lock = _STORE_LOCKS.get(uid)
        if lock is None:
            lock = threading.Lock()
            _STORE_LOCKS[uid] = lock
        return lock


# 画像 Markdown 文件头模板（迁移与导出用）
USER_MD_HEADER = """# User Food Profile

> Maintained by FoodMate — long-term health constraints, taste habits, household context, kitchen setup, and related cooking preferences.
"""

USER_TEMPLATE = USER_MD_HEADER + "\n".join(
    f"\n## {cat}\n\n(None yet)" for cat in MEMORY_CATEGORIES
)

# 从 assistant 回复中解析记忆引用的正则（匹配 [mem_xxxxxx]）
MEMORY_REF_PATTERN = re.compile(r"\[(mem_[a-zA-Z0-9]+)\]")


def get_user_memory_dir(uid: str) -> Path:
    """
    获取指定 uid 的记忆根目录。

    参数:
        uid (str): 用户 ID

    返回:
        Path: memory/users/{uid} 绝对路径
    """
    safe_uid = "".join(c for c in uid if c.isalnum())
    if not safe_uid:
        raise ValueError("Invalid uid")
    return USERS_DIR / safe_uid


def get_user_path(uid: str) -> Path:
    """
    获取指定 uid 的 user.md 路径（兼容/备份）。

    参数:
        uid (str): 用户 ID

    返回:
        Path: user.md 文件路径
    """
    return get_user_memory_dir(uid) / "user.md"


def get_user_json_path(uid: str) -> Path:
    """
    获取指定 uid 的 user.json 路径（主存储）。

    参数:
        uid (str): 用户 ID

    返回:
        Path: user.json 文件路径
    """
    return get_user_memory_dir(uid) / "user.json"


def get_user_sessions_dir(uid: str) -> Path:
    """
    获取指定 uid 的 Web 聊天会话目录。

    参数:
        uid (str): 用户 ID

    返回:
        Path: sessions 目录路径
    """
    return get_user_memory_dir(uid) / "sessions"


def _generate_entry_id() -> str:
    """
    生成短随机记忆条目 ID。

    返回:
        str: 格式 mem_xxxxxx
    """
    return f"mem_{secrets.token_hex(3)}"


def _truncate_quote(text: str, max_len: int = 200) -> str:
    """
    截断用户原话摘录，避免过长。

    参数:
        text (str): 原始文本
        max_len (int): 最大字符数

    返回:
        str: 截断后的摘录
    """
    cleaned = (text or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def _build_updated_entry(
    entry: MemoryEntry,
    *,
    content: str,
    category: str | None = None,
    changed_at: float | None = None,
    change_source: str | None = None,
    source_session_id: str | None = None,
    source_quote: str | None = None,
) -> MemoryEntry:
    """
    基于现有条目生成更新后的条目，并追加一条修改记录。

    参数:
        entry (MemoryEntry): 原条目
        content (str): 新正文
        category (str | None): 新分类；为 None 时保持原分类
        changed_at (float | None): 修改时间；默认当前时间
        change_source (str | None): 本次修改来源类型
        source_session_id (str | None): 触发本次修改的会话 ID
        source_quote (str | None): 触发本次修改的用户原话

    返回:
        MemoryEntry: 带 revisions 的新条目；无实质变更则返回原条目
    """
    new_category = category if category is not None else entry.category
    if content == entry.content and new_category == entry.category:
        return entry

    ts = changed_at if changed_at is not None else time.time()
    quote = _truncate_quote(source_quote) if source_quote else None
    revision = MemoryRevision(
        content=entry.content,
        category=entry.category,
        changed_at=ts,
        new_content=content,
        new_category=new_category,
        source_type=change_source,
        source_session_id=source_session_id,
        source_quote=quote,
    )
    return MemoryEntry(
        id=entry.id,
        category=new_category,
        content=content,
        created_at=entry.created_at,
        updated_at=ts,
        source_type=entry.source_type,
        source_session_id=entry.source_session_id,
        source_quote=entry.source_quote,
        revisions=[*entry.revisions, revision],
    )


def _apply_source_to_entry(
    entry: MemoryEntry,
    source: MemorySourceContext | None,
    *,
    on_update: bool = False,
) -> MemoryEntry:
    """
    将来源上下文写入记忆条目。

    参数:
        entry (MemoryEntry): 目标条目
        source (MemorySourceContext | None): 来源上下文
        on_update (bool): 是否为更新操作（保留原 created_at 与首次来源可选）

    返回:
        MemoryEntry: 带来源信息的条目
    """
    if not source:
        return entry
    quote = _truncate_quote(source.source_quote) if source.source_quote else None
    return MemoryEntry(
        id=entry.id,
        category=entry.category,
        content=entry.content,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        source_type=source.source_type,
        source_session_id=source.source_session_id,
        source_quote=quote or entry.source_quote,
        revisions=list(entry.revisions),
    )


def _add_fact_to_store(
    store: MemoryStore,
    cat: str,
    content: str,
    now: float,
    source: MemorySourceContext | None,
    added_ids: list[str],
    updated_ids: list[str],
    *,
    exclude_id: str | None = None,
) -> None:
    """
    将一条原子事实写入 store：与已有近义条合并，否则新增独立条目。

    参数:
        store (MemoryStore): 当前记忆存储
        cat (str): 分类
        content (str): 原子事实正文
        now (float): 写入时间戳
        source (MemorySourceContext | None): 来源上下文
        added_ids (list[str]): 本次新增 id 列表（就地追加）
        updated_ids (list[str]): 本次更新 id 列表（就地追加）
        exclude_id (str | None): 查找相似条时排除的 id（避免把不同事实合并回原条）
    """
    similar = find_similar_entry(store.entries, cat, content, exclude_id=exclude_id)
    if similar:
        if is_memory_conflict(similar.content, content):
            new_content = content
        else:
            new_content = merge_memory_contents(similar.content, content)
        for i, entry in enumerate(store.entries):
            if entry.id != similar.id:
                continue
            updated = _build_updated_entry(
                entry,
                content=new_content,
                changed_at=now,
                change_source=source.source_type if source else None,
                source_session_id=(source.source_session_id if source else None),
                source_quote=source.source_quote if source else None,
            )
            if source:
                updated = _apply_source_to_entry(updated, source, on_update=True)
            store.entries[i] = updated
            if entry.id not in updated_ids:
                updated_ids.append(entry.id)
            break
        return

    entry = MemoryEntry(
        id=_generate_entry_id(),
        category=cat,
        content=content,
        created_at=now,
        updated_at=now,
    )
    if source:
        entry = _apply_source_to_entry(entry, source)
    store.entries.append(entry)
    added_ids.append(entry.id)


def _strip_mem_ref_from_line(line: str) -> str:
    """
    去除列表项行首可能存在的 [mem:xxx] 标记。

    参数:
        line (str): 原始列表项文本

    返回:
        str: 纯内容文本
    """
    return re.sub(r"^\[mem_[a-zA-Z0-9]+\]\s*", "", line.strip()).strip()


def _parse_user_md_to_entries(md_content: str) -> list[MemoryEntry]:
    """
    将 user.md 解析为结构化条目列表。

    参数:
        md_content (str): user.md 全文

    返回:
        list[MemoryEntry]: 解析出的记忆条目
    """
    now = time.time()
    entries: list[MemoryEntry] = []
    current_category: str | None = None

    for raw_line in md_content.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            heading = line[3:].strip()
            normalized = normalize_category(heading)
            current_category = normalized if normalized in MEMORY_CATEGORIES else None
            continue
        if not current_category or not line.startswith("- "):
            continue
        item_text = _strip_mem_ref_from_line(line[2:])
        if not item_text or item_text in EMPTY_PLACEHOLDERS:
            continue
        # 尝试保留行内已有 mem ID
        mem_match = re.search(r"\[(mem_[a-zA-Z0-9]+)\]", line)
        entry_id = mem_match.group(1) if mem_match else _generate_entry_id()
        entries.append(
            MemoryEntry(
                id=entry_id,
                category=current_category,
                content=item_text,
                created_at=now,
                updated_at=now,
            )
        )
    return entries


def _entries_to_markdown(entries: list[MemoryEntry]) -> str:
    """
    将结构化条目渲染为带 ID 的 user.md Markdown。

    参数:
        entries (list[MemoryEntry]): 记忆条目列表

    返回:
        str: 完整 Markdown 文本
    """
    lines = [USER_MD_HEADER.rstrip()]
    by_category: dict[str, list[MemoryEntry]] = {c: [] for c in MEMORY_CATEGORIES}
    for entry in entries:
        if entry.category in by_category:
            by_category[entry.category].append(entry)

    for category in MEMORY_CATEGORIES:
        lines.append(f"\n## {category}\n")
        cat_entries = by_category[category]
        if not cat_entries:
            lines.append("(None yet)")
        else:
            for e in cat_entries:
                lines.append(f"- [{e.id}] {e.content}")
    return "\n".join(lines) + "\n"


def _maybe_migrate_categories(uid: str, store: MemoryStore) -> MemoryStore:
    """
    Migrate legacy Chinese category names to English and persist if changed.

    参数:
        uid (str): User ID
        store (MemoryStore): Current store

    返回:
        MemoryStore: Store with normalized categories
    """
    changed = False
    new_entries: list[MemoryEntry] = []
    for entry in store.entries:
        norm = normalize_category(entry.category)
        if norm != entry.category:
            changed = True
        new_entries.append(
            MemoryEntry(
                id=entry.id,
                category=norm,
                content=entry.content,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
                source_type=entry.source_type,
                source_session_id=entry.source_session_id,
                source_quote=entry.source_quote,
                revisions=list(entry.revisions),
            )
        )
    if changed:
        store = MemoryStore(version=store.version, entries=new_entries)
        _write_store(uid, store)
    return store


def _read_store(uid: str) -> MemoryStore:
    """
    从磁盘读取 user.json；不存在时尝试从 user.md 迁移。

    参数:
        uid (str): 用户 ID

    返回:
        MemoryStore: 记忆存储
    """
    ensure_memory_dirs(uid)
    json_path = get_user_json_path(uid)
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            store = MemoryStore.from_dict(data)
            return _maybe_migrate_categories(uid, store)
        except Exception:
            pass

    # 迁移：从 user.md 解析
    user_path = get_user_path(uid)
    md_content = ""
    if user_path.exists():
        try:
            md_content = user_path.read_text(encoding="utf-8")
        except Exception:
            md_content = ""
    if not md_content.strip():
        md_content = USER_TEMPLATE

    entries = _parse_user_md_to_entries(md_content)
    store = MemoryStore(version=1, entries=entries)
    _write_store(uid, store)
    return _maybe_migrate_categories(uid, store)


def _write_store(uid: str, store: MemoryStore) -> None:
    """
    将记忆存储写入 user.json，并同步备份 user.md。

    参数:
        uid (str): 用户 ID
        store (MemoryStore): 记忆存储

    返回:
        None
    """
    ensure_memory_dirs(uid)
    json_path = get_user_json_path(uid)
    json_path.write_text(
        json.dumps(store.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md = _entries_to_markdown(store.entries)
    get_user_path(uid).write_text(md, encoding="utf-8")


def ensure_memory_dirs(uid: str) -> None:
    """
    确保指定用户的记忆目录与初始文件存在。

    参数:
        uid (str): 用户 ID

    返回:
        None
    """
    user_dir = get_user_memory_dir(uid)
    sessions_dir = get_user_sessions_dir(uid)
    user_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    if not get_user_json_path(uid).exists() and not get_user_path(uid).exists():
        get_user_path(uid).write_text(USER_TEMPLATE, encoding="utf-8")


def entries_to_context(entries: list[MemoryEntry]) -> str:
    """
    将给定记忆条目渲染为可注入系统提示的 Markdown。

    仅输出有条目的分类，避免未召回的分类被渲染成「(None yet)」造成误导。

    参数:
        entries (list[MemoryEntry]): 记忆条目列表（可为空）

    返回:
        str: 画像 Markdown 文本；无条目时返回空字符串
    """
    if not entries:
        return ""
    lines = [USER_MD_HEADER.rstrip()]
    by_category: dict[str, list[MemoryEntry]] = {c: [] for c in MEMORY_CATEGORIES}
    for entry in entries:
        if entry.category in by_category:
            by_category[entry.category].append(entry)

    for category in MEMORY_CATEGORIES:
        cat_entries = by_category[category]
        if not cat_entries:
            continue
        lines.append(f"\n## {category}\n")
        for e in cat_entries:
            lines.append(f"- [{e.id}] {e.content}")
    return "\n".join(lines).strip()


def load_context(uid: str) -> str:
    """
    加载用户长期画像 Markdown（含 [mem:xxx] ID），用于注入系统提示。

    参数:
        uid (str): 用户 ID

    返回:
        str: 画像 Markdown 文本
    """
    store = _read_store(uid)
    return entries_to_context(store.entries)


def save_user(content: str, uid: str) -> None:
    """
    从 Markdown 覆盖写入记忆（解析为 entries 后存 user.json，保留已有来源）。

    写入前会做同类相似合并；冲突条目以 updated_at 较新者为准。

    参数:
        content (str): 完整 user.md Markdown
        uid (str): 用户 ID

    返回:
        None
    """
    old_store = _read_store(uid)
    old_by_id = {e.id: e for e in old_store.entries}
    entries = _parse_user_md_to_entries(content)
    merged: list[MemoryEntry] = []
    for e in entries:
        old = old_by_id.get(e.id)
        if old:
            # 内容有变则刷新 updated_at，便于冲突时按时间择优
            content_changed = (old.content or "").strip() != (e.content or "").strip()
            if content_changed:
                merged.append(
                    _build_updated_entry(
                        old,
                        content=e.content,
                        category=e.category,
                        changed_at=e.updated_at,
                        change_source="migrate",
                    )
                )
            else:
                merged.append(
                    MemoryEntry(
                        id=e.id,
                        category=e.category,
                        content=e.content,
                        created_at=old.created_at,
                        updated_at=old.updated_at,
                        source_type=old.source_type,
                        source_session_id=old.source_session_id,
                        source_quote=old.source_quote,
                        revisions=list(old.revisions),
                    )
                )
        else:
            merged.append(
                MemoryEntry(
                    id=e.id,
                    category=e.category,
                    content=e.content,
                    created_at=e.created_at,
                    updated_at=e.updated_at,
                    source_type="migrate",
                )
            )
    reconciled, _ = reconcile_entries(merged)
    store = MemoryStore(version=1, entries=reconciled)
    _write_store(uid, store)


def list_entries(uid: str) -> list[MemoryEntry]:
    """
    列出用户全部结构化记忆条目。

    会将「辣；酸」这类多事实旧条目拆成独立卡片，并只合并真正的近义改写。

    参数:
        uid (str): 用户 ID

    返回:
        list[MemoryEntry]: 条目列表
    """
    with _uid_lock(uid):
        store = _read_store(uid)
        reconciled, changed = reconcile_entries(store.entries)
        if changed:
            store = MemoryStore(version=store.version, entries=reconciled)
            _write_store(uid, store)
        return list(store.entries)


def get_entry(uid: str, entry_id: str) -> MemoryEntry | None:
    """
    按 ID 获取单条记忆。

    参数:
        uid (str): 用户 ID
        entry_id (str): 条目 ID

    返回:
        MemoryEntry | None: 找到则返回条目，否则 None
    """
    for entry in _read_store(uid).entries:
        if entry.id == entry_id:
            return entry
    return None


def get_entries_by_ids(uid: str, entry_ids: list[str]) -> list[MemoryEntry]:
    """
    批量按 ID 获取记忆条目（保持请求顺序，跳过不存在 ID）。

    参数:
        uid (str): 用户 ID
        entry_ids (list[str]): 条目 ID 列表

    返回:
        list[MemoryEntry]: 匹配到的条目
    """
    id_set = set(entry_ids)
    store = _read_store(uid)
    by_id = {e.id: e for e in store.entries}
    result: list[MemoryEntry] = []
    for eid in entry_ids:
        if eid in by_id:
            result.append(by_id[eid])
    return result


def add_entry(
    uid: str,
    category: str,
    content: str,
    *,
    source: MemorySourceContext | None = None,
) -> MemoryEntry:
    """
    新增一条记忆条目；若同类已有类似条目则合并或冲突覆盖。

    参数:
        uid (str): 用户 ID
        category (str): 分区名称
        content (str): 记忆正文
        source (MemorySourceContext | None): 来源上下文

    返回:
        MemoryEntry: 新建或合并后的条目

    Raises:
        ValueError: 分区不合法或内容为空
    """
    category = normalize_category(category)
    if category not in MEMORY_CATEGORIES:
        raise ValueError(f"Invalid category: {category}")
    content = content.strip()
    if not content:
        raise ValueError("Content cannot be empty")

    # 走统一操作路径，复用相似合并 / 冲突消解
    result = apply_operations(
        uid,
        [MemoryOperation(action="add", category=category, content=content)],
        source=source or MemorySourceContext(source_type="manual"),
    )
    if result.updated_ids:
        for e in result.entries:
            if e.id == result.updated_ids[0]:
                return e
    if result.added_ids:
        for e in result.entries:
            if e.id == result.added_ids[0]:
                return e
    # 回退：返回同类中与内容最相关的一条
    similar = find_similar_entry(result.entries, category, content)
    if similar:
        return similar
    raise RuntimeError("Failed to add memory entry")


def update_entry(
    uid: str,
    entry_id: str,
    content: str,
    category: str | None = None,
    source: MemorySourceContext | None = None,
) -> MemoryEntry:
    """
    更新指定记忆条目内容（可选修改分类），并按来源记录本次修改。

    参数:
        uid (str): 用户 ID
        entry_id (str): 条目 ID
        content (str): 新正文
        category (str | None): 可选新分类；为 None 时保持原分类
        source (MemorySourceContext | None): 本次修改来源；为 None 时视为用户手动编辑

    返回:
        MemoryEntry: 更新后的条目

    Raises:
        ValueError: 条目不存在、内容为空或分类非法
    """
    content = content.strip()
    if not content:
        raise ValueError("Content cannot be empty")

    new_category: str | None = None
    if category is not None:
        new_category = normalize_category(category)
        if new_category not in MEMORY_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

    # 未显式传入来源时，视为记忆页手动编辑
    change_source = source.source_type if source else "manual"
    source_session_id = source.source_session_id if source else None
    source_quote = source.source_quote if source else None

    with _uid_lock(uid):
        store = _read_store(uid)
        for i, entry in enumerate(store.entries):
            if entry.id == entry_id:
                updated = _build_updated_entry(
                    entry,
                    content=content,
                    category=new_category,
                    change_source=change_source,
                    source_session_id=source_session_id,
                    source_quote=source_quote,
                )
                store.entries[i] = updated
                # 改完再 reconcile，清掉因此产生的近重复
                reconciled, _ = reconcile_entries(store.entries)
                store.entries = reconciled
                _write_store(uid, store)
                for e in store.entries:
                    if e.id == entry_id:
                        return e
                # 若被合并进其他条目，返回合并结果中最相似的一条
                similar = find_similar_entry(
                    store.entries, updated.category, updated.content
                )
                return similar or updated
        raise ValueError(f"Entry not found: {entry_id}")


def delete_entry(uid: str, entry_id: str) -> bool:
    """
    删除指定记忆条目。

    参数:
        uid (str): 用户 ID
        entry_id (str): 条目 ID

    返回:
        bool: 是否成功删除
    """
    with _uid_lock(uid):
        store = _read_store(uid)
        original_len = len(store.entries)
        store.entries = [e for e in store.entries if e.id != entry_id]
        if len(store.entries) == original_len:
            return False
        _write_store(uid, store)
        return True


def apply_operations(
    uid: str,
    operations: list[MemoryOperation],
    *,
    source: MemorySourceContext | None = None,
) -> ApplyResult:
    """
    批量应用记忆变更操作（add / update / delete）。

    add 时若同类已有类似条目：互补则合并内容，冲突则以新内容为准（更新已有条目）。
    全部操作结束后再做一轮同类 reconcile。
    同一用户的写入串行执行，避免 Judge 与 Agent 工具并行写出重复条目。

    参数:
        uid (str): 用户 ID
        operations (list[MemoryOperation]): 操作列表
        source (MemorySourceContext | None): 写入来源上下文

    返回:
        ApplyResult: 应用结果
    """
    with _uid_lock(uid):
        return _apply_operations_unlocked(uid, operations, source=source)


def _apply_operations_unlocked(
    uid: str,
    operations: list[MemoryOperation],
    *,
    source: MemorySourceContext | None = None,
) -> ApplyResult:
    """
    在已持有用户锁的前提下应用记忆操作。

    参数:
        uid (str): 用户 ID
        operations (list[MemoryOperation]): 操作列表
        source (MemorySourceContext | None): 写入来源上下文

    返回:
        ApplyResult: 应用结果
    """
    if not operations:
        store = _read_store(uid)
        return ApplyResult(changed=False, entries=list(store.entries))

    store = _read_store(uid)
    added_ids: list[str] = []
    updated_ids: list[str] = []
    deleted_ids: list[str] = []
    now = time.time()

    # 多关键词内容拆成多条 add，保证一事实一张卡片
    normalized_ops: list[MemoryOperation] = []
    for op in operations:
        if op.action == "add" and (op.content or "").strip():
            facts = split_atomic_facts(op.content or "")
            if len(facts) > 1:
                for fact in facts:
                    normalized_ops.append(
                        MemoryOperation(
                            action="add",
                            category=op.category,
                            content=fact,
                        )
                    )
                continue
        if op.action == "update" and (op.content or "").strip():
            facts = split_atomic_facts(op.content or "")
            if len(facts) > 1:
                cat = op.category
                if not cat and op.entry_id:
                    for e in store.entries:
                        if e.id == op.entry_id:
                            cat = e.category
                            break
                normalized_ops.append(
                    MemoryOperation(
                        action="update",
                        entry_id=op.entry_id,
                        category=cat,
                        content=facts[0],
                    )
                )
                for fact in facts[1:]:
                    normalized_ops.append(
                        MemoryOperation(
                            action="add",
                            category=cat,
                            content=fact,
                        )
                    )
                continue
        normalized_ops.append(op)

    for op in normalized_ops:
        if op.action == "add":
            cat = normalize_category(op.category or "")
            if not cat or cat not in MEMORY_CATEGORIES:
                continue
            content = (op.content or "").strip()
            if not content:
                continue
            _add_fact_to_store(store, cat, content, now, source, added_ids, updated_ids)
        elif op.action == "update":
            if not op.entry_id:
                continue
            content = (op.content or "").strip()
            if not content:
                continue
            for i, entry in enumerate(store.entries):
                if entry.id != op.entry_id:
                    continue
                # Judge 常把「同类不同事实」误发成 update；不同事实应独立成条
                if not is_same_memory_fact(entry.content, content):
                    cat = normalize_category(op.category or entry.category)
                    if cat not in MEMORY_CATEGORIES:
                        cat = entry.category
                    _add_fact_to_store(
                        store,
                        cat,
                        content,
                        now,
                        source,
                        added_ids,
                        updated_ids,
                        exclude_id=entry.id,
                    )
                    break
                updated = _build_updated_entry(
                    entry,
                    content=content,
                    changed_at=now,
                    change_source=source.source_type if source else None,
                    source_session_id=(source.source_session_id if source else None),
                    source_quote=source.source_quote if source else None,
                )
                if source:
                    updated = _apply_source_to_entry(updated, source, on_update=True)
                store.entries[i] = updated
                updated_ids.append(entry.id)
                break
        elif op.action == "delete":
            if not op.entry_id:
                continue
            before = len(store.entries)
            store.entries = [e for e in store.entries if e.id != op.entry_id]
            if len(store.entries) < before:
                deleted_ids.append(op.entry_id)

    reconciled, reconciled_changed = reconcile_entries(store.entries)
    store.entries = reconciled

    changed = bool(added_ids or updated_ids or deleted_ids or reconciled_changed)
    if changed:
        _write_store(uid, store)
    return ApplyResult(
        changed=changed,
        entries=list(store.entries),
        added_ids=added_ids,
        updated_ids=updated_ids,
        deleted_ids=deleted_ids,
    )


def patch_entries_source(
    uid: str,
    entry_ids: list[str],
    source: MemorySourceContext,
) -> None:
    """
    为指定条目补写来源信息（仅当尚未有 source_session_id 时）。

    参数:
        uid (str): 用户 ID
        entry_ids (list[str]): 条目 ID 列表
        source (MemorySourceContext): 来源上下文

    返回:
        None
    """
    if not entry_ids:
        return
    id_set = set(entry_ids)
    store = _read_store(uid)
    changed = False
    for i, entry in enumerate(store.entries):
        if entry.id in id_set and not entry.source_session_id:
            store.entries[i] = _apply_source_to_entry(entry, source)
            changed = True
    if changed:
        _write_store(uid, store)


def extract_memory_ref_ids(text: str) -> list[str]:
    """
    从 assistant 回复文本中提取记忆引用 ID 列表（去重保序）。

    参数:
        text (str): 助手回复正文

    返回:
        list[str]: mem ID 列表
    """
    seen: set[str] = set()
    result: list[str] = []
    for match in MEMORY_REF_PATTERN.finditer(text):
        mem_id = match.group(1)
        if mem_id not in seen:
            seen.add(mem_id)
            result.append(mem_id)
    return result


def _normalize_rel_path(rel_path: str) -> str:
    """
    规范化前端传入的相对路径字符串。

    参数:
        rel_path (str): 相对路径

    返回:
        str: POSIX 风格路径
    """
    return rel_path.replace("\\", "/").strip()


def _validate_memory_rel_path(rel_path: str, uid: str) -> Path:
    """
    校验并解析 memory 相对路径，限定只能访问 user.md。

    参数:
        rel_path (str): 前端相对路径
        uid (str): 用户 ID

    返回:
        Path: 磁盘绝对路径

    Raises:
        ValueError: 路径非法
    """
    normalized = _normalize_rel_path(rel_path).lstrip("./")
    if not normalized.startswith("memory/"):
        raise ValueError(f"Access denied: {rel_path}")
    rel_under_memory = normalized[len("memory/") :]
    if rel_under_memory != "user.md":
        raise ValueError(f"Access denied: {rel_path}")
    user_memory_dir = get_user_memory_dir(uid).resolve()
    full_path = get_user_path(uid).resolve()
    if not str(full_path).startswith(str(user_memory_dir)):
        raise ValueError("Path traversal detected")
    return full_path


def list_memory_files(uid: str) -> list[dict]:
    """
    列出可编辑的记忆文件元信息。

    参数:
        uid (str): 用户 ID

    返回:
        list[dict]: 文件元信息列表
    """
    ensure_memory_dirs(uid)
    json_path = get_user_json_path(uid)
    mtime = int(json_path.stat().st_mtime) if json_path.exists() else 0
    entry_count = len(_read_store(uid).entries)
    return [
        {
            "path": "memory/user.json",
            "updated_at": mtime,
            "label": "User Food Profile",
            "description": f"Structured memory ({entry_count} entries)",
        }
    ]


def read_memory_file(rel_path: str, uid: str) -> str:
    """
    安全读取 memory 目录下的文本文件（user.md 导出视图）。

    参数:
        rel_path (str): 相对路径
        uid (str): 用户 ID

    返回:
        str: 文件内容
    """
    _validate_memory_rel_path(rel_path, uid)
    return load_context(uid)


def save_memory_file(rel_path: str, content: str, uid: str) -> None:
    """
    安全写入 memory 目录（解析 md 写入 user.json）。

    参数:
        rel_path (str): 相对路径
        content (str): Markdown 内容
        uid (str): 用户 ID

    返回:
        None
    """
    _validate_memory_rel_path(rel_path, uid)
    save_user(content, uid)
