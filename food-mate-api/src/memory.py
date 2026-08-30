"""
FoodMate structured memory: user.json is the primary store, with user.md migration and Markdown export.
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

# Multi-user memory root: memory/users/{uid}/
USERS_DIR = MEMORY_DIR / "users"

# Serialize reads/writes per user so Judge and Agent tools do not write duplicate entries
_STORE_LOCKS: dict[str, threading.Lock] = {}
_STORE_LOCKS_GUARD = threading.Lock()


def _uid_lock(uid: str) -> threading.Lock:
    """
    Get the memory-store lock for a user.

    Args:
        uid (str): User ID

    Returns:
        threading.Lock: Mutex for this user
    """
    with _STORE_LOCKS_GUARD:
        lock = _STORE_LOCKS.get(uid)
        if lock is None:
            lock = threading.Lock()
            _STORE_LOCKS[uid] = lock
        return lock


# Profile Markdown header template (used for migration and export)
USER_MD_HEADER = """# User Food Profile

> Maintained by FoodMate — long-term health constraints, taste habits, household context, kitchen setup, and related cooking preferences.
"""

USER_TEMPLATE = USER_MD_HEADER + "\n".join(
    f"\n## {cat}\n\n(None yet)" for cat in MEMORY_CATEGORIES
)

# Regex to parse memory citations from assistant replies (matches [mem_xxxxxx])
MEMORY_REF_PATTERN = re.compile(r"\[(mem_[a-zA-Z0-9]+)\]")


def get_user_memory_dir(uid: str) -> Path:
    """
    Get the memory root directory for a uid.

    Args:
        uid (str): User ID

    Returns:
        Path: Absolute path of memory/users/{uid}
    """
    safe_uid = "".join(c for c in uid if c.isalnum())
    if not safe_uid:
        raise ValueError("Invalid uid")
    return USERS_DIR / safe_uid


def get_user_path(uid: str) -> Path:
    """
    Get the user.md path for a uid (compat / backup).

    Args:
        uid (str): User ID

    Returns:
        Path: user.md file path
    """
    return get_user_memory_dir(uid) / "user.md"


def get_user_json_path(uid: str) -> Path:
    """
    Get the user.json path for a uid (primary store).

    Args:
        uid (str): User ID

    Returns:
        Path: user.json file path
    """
    return get_user_memory_dir(uid) / "user.json"


def get_user_sessions_dir(uid: str) -> Path:
    """
    Get the web chat sessions directory for a uid.

    Args:
        uid (str): User ID

    Returns:
        Path: sessions directory path
    """
    return get_user_memory_dir(uid) / "sessions"


def _generate_entry_id() -> str:
    """
    Generate a short random memory entry ID.

    Returns:
        str: Format mem_xxxxxx
    """
    return f"mem_{secrets.token_hex(3)}"


def _truncate_quote(text: str, max_len: int = 200) -> str:
    """
    Truncate a user-quote excerpt so it does not grow too long.

    Args:
        text (str): Original text
        max_len (int): Max character count

    Returns:
        str: Truncated excerpt
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
    Build an updated entry from an existing one and append a revision record.

    Args:
        entry (MemoryEntry): Original entry
        content (str): New content
        category (str | None): New category; keep the original if None
        changed_at (float | None): Change time; defaults to now
        change_source (str | None): Source type of this change
        source_session_id (str | None): Session ID that triggered this change
        source_quote (str | None): User quote that triggered this change

    Returns:
        MemoryEntry: New entry with revisions; original entry if nothing changed
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
    Write source context onto a memory entry.

    Args:
        entry (MemoryEntry): Target entry
        source (MemorySourceContext | None): Source context
        on_update (bool): Whether this is an update (keep created_at and first source)

    Returns:
        MemoryEntry: Entry with source information
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
    Write one atomic fact into the store: merge with a near-duplicate, or add a new entry.

    Args:
        store (MemoryStore): Current memory store
        cat (str): Category
        content (str): Atomic fact text
        now (float): Write timestamp
        source (MemorySourceContext | None): Source context
        added_ids (list[str]): IDs added this call (appended in place)
        updated_ids (list[str]): IDs updated this call (appended in place)
        exclude_id (str | None): ID to skip when finding similar entries
            (avoids merging a different fact back into the original)
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
    Strip a leading [mem:xxx] marker from a list-item line if present.

    Args:
        line (str): Raw list-item text

    Returns:
        str: Content text only
    """
    return re.sub(r"^\[mem_[a-zA-Z0-9]+\]\s*", "", line.strip()).strip()


def _parse_user_md_to_entries(md_content: str) -> list[MemoryEntry]:
    """
    Parse user.md into a list of structured entries.

    Args:
        md_content (str): Full user.md text

    Returns:
        list[MemoryEntry]: Parsed memory entries
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
        # Try to keep an existing inline mem ID
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
    Render structured entries as user.md Markdown with IDs.

    Args:
        entries (list[MemoryEntry]): Memory entry list

    Returns:
        str: Full Markdown text
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

    Args:
        uid (str): User ID
        store (MemoryStore): Current store

    Returns:
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
    Read user.json from disk; if missing, try migrating from user.md.

    Args:
        uid (str): User ID

    Returns:
        MemoryStore: Memory store
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

    # Migrate: parse from user.md
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
    Write the memory store to user.json and sync a user.md backup.

    Args:
        uid (str): User ID
        store (MemoryStore): Memory store

    Returns:
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
    Ensure the user's memory directory and initial files exist.

    Args:
        uid (str): User ID

    Returns:
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
    Render given memory entries as Markdown suitable for injecting into the system prompt.

    Only categories that have entries are output, so unrecalled categories are not
    rendered as "(None yet)" which would be misleading.

    Args:
        entries (list[MemoryEntry]): Memory entry list (may be empty)

    Returns:
        str: Profile Markdown; empty string if there are no entries
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
    Load the user's long-term profile Markdown (with [mem:xxx] IDs) for the system prompt.

    Args:
        uid (str): User ID

    Returns:
        str: Profile Markdown text
    """
    store = _read_store(uid)
    return entries_to_context(store.entries)


def save_user(content: str, uid: str) -> None:
    """
    Overwrite memory from Markdown (parse into entries, store as user.json, keep existing sources).

    Similar same-category entries are merged first; on conflict, the newer updated_at wins.

    Args:
        content (str): Full user.md Markdown
        uid (str): User ID

    Returns:
        None
    """
    old_store = _read_store(uid)
    old_by_id = {e.id: e for e in old_store.entries}
    entries = _parse_user_md_to_entries(content)
    merged: list[MemoryEntry] = []
    for e in entries:
        old = old_by_id.get(e.id)
        if old:
            # Refresh updated_at when content changes so conflicts can prefer the newer one
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
    List all structured memory entries for a user.

    Splits old multi-fact entries such as "spicy; sour" into separate cards, and only
    merges true near-paraphrases of the same fact.

    Args:
        uid (str): User ID

    Returns:
        list[MemoryEntry]: Entry list
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
    Get a single memory entry by ID.

    Args:
        uid (str): User ID
        entry_id (str): Entry ID

    Returns:
        MemoryEntry | None: The entry if found, otherwise None
    """
    for entry in _read_store(uid).entries:
        if entry.id == entry_id:
            return entry
    return None


def get_entries_by_ids(uid: str, entry_ids: list[str]) -> list[MemoryEntry]:
    """
    Get memory entries by IDs in request order, skipping missing IDs.

    Args:
        uid (str): User ID
        entry_ids (list[str]): Entry ID list

    Returns:
        list[MemoryEntry]: Matched entries
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
    Add a memory entry; merge or overwrite on conflict if a similar same-category entry exists.

    Args:
        uid (str): User ID
        category (str): Category name
        content (str): Memory text
        source (MemorySourceContext | None): Source context

    Returns:
        MemoryEntry: Newly created or merged entry

    Raises:
        ValueError: Invalid category or empty content
    """
    category = normalize_category(category)
    if category not in MEMORY_CATEGORIES:
        raise ValueError(f"Invalid category: {category}")
    content = content.strip()
    if not content:
        raise ValueError("Content cannot be empty")

    # Use the shared operation path so similar-merge / conflict resolution is reused
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
    # Fallback: return the most related same-category entry
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
    Update a memory entry's content (and optionally category), recording the change source.

    Args:
        uid (str): User ID
        entry_id (str): Entry ID
        content (str): New content
        category (str | None): Optional new category; keep the original if None
        source (MemorySourceContext | None): Source of this change; None means manual edit

    Returns:
        MemoryEntry: Updated entry

    Raises:
        ValueError: Entry not found, empty content, or invalid category
    """
    content = content.strip()
    if not content:
        raise ValueError("Content cannot be empty")

    new_category: str | None = None
    if category is not None:
        new_category = normalize_category(category)
        if new_category not in MEMORY_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

    # No explicit source means a manual edit on the memory page
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
                # Reconcile after the change to drop near-duplicates it created
                reconciled, _ = reconcile_entries(store.entries)
                store.entries = reconciled
                _write_store(uid, store)
                for e in store.entries:
                    if e.id == entry_id:
                        return e
                # If merged into another entry, return the most similar result
                similar = find_similar_entry(
                    store.entries, updated.category, updated.content
                )
                return similar or updated
        raise ValueError(f"Entry not found: {entry_id}")


def delete_entry(uid: str, entry_id: str) -> bool:
    """
    Delete a memory entry.

    Args:
        uid (str): User ID
        entry_id (str): Entry ID

    Returns:
        bool: Whether the entry was deleted
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
    Apply a batch of memory operations (add / update / delete).

    On add, if a similar same-category entry exists: merge complementary content,
    or take the new content on conflict (update the existing entry).
    After all operations, run one more same-category reconcile.
    Writes for the same user are serialized so Judge and Agent tools do not
    write duplicate entries in parallel.

    Args:
        uid (str): User ID
        operations (list[MemoryOperation]): Operation list
        source (MemorySourceContext | None): Write source context

    Returns:
        ApplyResult: Apply result
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
    Apply memory operations while already holding the user lock.

    Args:
        uid (str): User ID
        operations (list[MemoryOperation]): Operation list
        source (MemorySourceContext | None): Write source context

    Returns:
        ApplyResult: Apply result
    """
    if not operations:
        store = _read_store(uid)
        return ApplyResult(changed=False, entries=list(store.entries))

    store = _read_store(uid)
    added_ids: list[str] = []
    updated_ids: list[str] = []
    deleted_ids: list[str] = []
    now = time.time()

    # Split multi-keyword content into multiple adds so each fact is one card
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
                # Judge often sends distinct same-category facts as update; they should be separate entries
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
    Backfill source info on entries that do not yet have source_session_id.

    Args:
        uid (str): User ID
        entry_ids (list[str]): Entry ID list
        source (MemorySourceContext): Source context

    Returns:
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
    Extract memory citation IDs from assistant reply text (deduped, order preserved).

    Args:
        text (str): Assistant reply body

    Returns:
        list[str]: mem ID list
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
    Normalize a relative path string from the frontend.

    Args:
        rel_path (str): Relative path

    Returns:
        str: POSIX-style path
    """
    return rel_path.replace("\\", "/").strip()


def _validate_memory_rel_path(rel_path: str, uid: str) -> Path:
    """
    Validate and resolve a memory relative path; only user.md is allowed.

    Args:
        rel_path (str): Frontend relative path
        uid (str): User ID

    Returns:
        Path: Absolute disk path

    Raises:
        ValueError: Invalid path
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
    List metadata for editable memory files.

    Args:
        uid (str): User ID

    Returns:
        list[dict]: File metadata list
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
    Safely read a text file under the memory directory (user.md export view).

    Args:
        rel_path (str): Relative path
        uid (str): User ID

    Returns:
        str: File content
    """
    _validate_memory_rel_path(rel_path, uid)
    return load_context(uid)


def save_memory_file(rel_path: str, content: str, uid: str) -> None:
    """
    Safely write the memory directory (parse Markdown into user.json).

    Args:
        rel_path (str): Relative path
        content (str): Markdown content
        uid (str): User ID

    Returns:
        None
    """
    _validate_memory_rel_path(rel_path, uid)
    save_user(content, uid)
