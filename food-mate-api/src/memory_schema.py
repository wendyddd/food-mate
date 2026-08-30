"""
Structured memory data models and constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Stable category ids (match user.md ## headings; storage and API use these English names)
MEMORY_CATEGORIES: list[str] = [
    "Health & Dietary Restrictions",
    "Taste & Habits",
    "Household & Context",
    "Kitchen & Budget",
    "Other",
]

# Category meanings (used by Judge / Extractor / tool descriptions)
CATEGORY_GUIDANCE: dict[str, str] = {
    "Health & Dietary Restrictions": (
        "Allergies, religious diets, absolute avoidances, and health-related goals "
        "(e.g. less oil, low-carb, high-protein). Hard constraints and dietary goals."
    ),
    "Taste & Habits": (
        "Flavor likes/dislikes, preferred cuisines, disliked ingredients, cooking skill, "
        "and habitual cooking style. Soft preferences about taste and how the user cooks."
    ),
    "Household & Context": (
        "Household size, family members' constraints, portions, time budget "
        "(e.g. weekdays under 25 minutes), and meal scenarios."
    ),
    "Kitchen & Budget": (
        "Kitchen equipment/appliances, pantry staples, and budget/cost sensitivity."
    ),
    "Other": (
        "Stable, cooking-relevant facts that do not fit the four categories above. "
        "Prefer the other categories when possible; never store one-off requests."
    ),
}

# Display labels (i18n; storage still uses MEMORY_CATEGORIES English names)
CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "Health & Dietary Restrictions": {
        "en": "Health & Dietary Restrictions",
        "zh": "健康与饮食限制",
    },
    "Taste & Habits": {
        "en": "Taste & Habits",
        "zh": "口味与习惯",
    },
    "Household & Context": {
        "en": "Household & Context",
        "zh": "家人与场景",
    },
    "Kitchen & Budget": {
        "en": "Kitchen & Budget",
        "zh": "厨房设备与预算",
    },
    "Other": {
        "en": "Other",
        "zh": "其他",
    },
}

# Legacy category names (Chinese/English) → current English categories
LEGACY_CATEGORY_MAP: dict[str, str] = {
    # Previous English five-category set
    "Taste Preferences": "Taste & Habits",
    "Dietary Restrictions & Allergies": "Health & Dietary Restrictions",
    "Cooking Skill & Kitchen": "Kitchen & Budget",
    "Favorite Cuisines": "Taste & Habits",
    "Dietary Goals": "Health & Dietary Restrictions",
    # Earlier Chinese five-category set
    "口味偏好": "Taste & Habits",
    "忌口与过敏": "Health & Dietary Restrictions",
    "烹饪水平与厨房条件": "Kitchen & Budget",
    "喜欢的菜系": "Taste & Habits",
    "饮食目标": "Health & Dietary Restrictions",
    # New five-category Chinese display names → English storage names
    "健康与饮食限制": "Health & Dietary Restrictions",
    "口味与习惯": "Taste & Habits",
    "家人与场景": "Household & Context",
    "厨房设备与预算": "Kitchen & Budget",
    "其他": "Other",
}

# Empty-section placeholders (current and legacy)
EMPTY_PLACEHOLDERS: tuple[str, ...] = (
    "(None yet)",
    "(No entries yet)",
    "（暂无）",
    "（暂无记录）",
)

# Category title → Markdown ## line mapping
CATEGORY_TO_HEADING: dict[str, str] = {c: f"## {c}" for c in MEMORY_CATEGORIES}

MemoryAction = Literal["add", "update", "delete"]

# Memory source types
MemorySourceType = Literal["judge", "manual", "extract", "tool", "migrate"]


def normalize_category(category: str) -> str:
    """
    Normalize a category name to the current English set, including legacy names.

    Args:
        category (str): Raw category string

    Returns:
        str: Normalized category name
    """
    if category in MEMORY_CATEGORIES:
        return category
    return LEGACY_CATEGORY_MAP.get(category, category)


def category_label(category: str, locale: str = "en") -> str:
    """
    Return the category display label for a locale.

    Args:
        category (str): Category id (English storage name)
        locale (str): Language code, e.g. en / zh / zh-CN

    Returns:
        str: Display label
    """
    lang = "zh" if locale.lower().startswith("zh") else "en"
    labels = CATEGORY_LABELS.get(normalize_category(category), {})
    return labels.get(lang) or labels.get("en") or category


def categories_prompt_block() -> str:
    """
    Build a category list with meanings for Judge / Extractor prompts.

    Returns:
        str: Multi-line category guidance text
    """
    lines = []
    for cat in MEMORY_CATEGORIES:
        lines.append(f"- {cat}: {CATEGORY_GUIDANCE[cat]}")
    return "\n".join(lines)


@dataclass
class MemoryRevision:
    """
    One memory revision (snapshot before the change and when it happened).

    Attributes:
        content (str): Content before the change
        category (str): Category before the change
        changed_at (float): Timestamp of this change
        new_content (str): Content after the change
        new_category (str): Category after the change
        source_type (str | None): Source that triggered this change (manual/judge/…)
        source_session_id (str | None): Session ID that triggered this change
        source_quote (str | None): User quote excerpt that triggered this change
    """

    content: str
    category: str
    changed_at: float
    new_content: str
    new_category: str
    source_type: str | None = None
    source_session_id: str | None = None
    source_quote: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to a JSON-storable dict.

        Returns:
            dict: Revision dict
        """
        data: dict[str, Any] = {
            "content": self.content,
            "category": self.category,
            "changed_at": self.changed_at,
            "new_content": self.new_content,
            "new_category": self.new_category,
        }
        if self.source_type:
            data["source_type"] = self.source_type
        if self.source_session_id:
            data["source_session_id"] = self.source_session_id
        if self.source_quote:
            data["source_quote"] = self.source_quote
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRevision:
        """
        Deserialize a revision from a dict.

        Args:
            data (dict): Stored dict

        Returns:
            MemoryRevision: Revision instance
        """
        return cls(
            content=str(data.get("content", "")),
            category=normalize_category(str(data.get("category", "Other"))),
            changed_at=float(data.get("changed_at", 0)),
            new_content=str(data.get("new_content", data.get("content", ""))),
            new_category=normalize_category(
                str(data.get("new_category", data.get("category", "Other")))
            ),
            source_type=data.get("source_type") or None,
            source_session_id=data.get("source_session_id") or None,
            source_quote=data.get("source_quote") or None,
        )


@dataclass
class MemoryEntry:
    """
    Single structured memory entry.

    Attributes:
        id (str): Stable entry ID, format mem_xxxxxx
        category (str): Category name
        content (str): Memory text
        created_at (float): Created timestamp
        updated_at (float): Last updated timestamp
        source_type (str | None): Source type (judge/manual/extract/tool/migrate)
        source_session_id (str | None): Source session ID
        source_quote (str | None): User quote excerpt
        revisions (list[MemoryRevision]): History of revisions (old → new)
    """

    id: str
    category: str
    content: str
    created_at: float
    updated_at: float
    source_type: str | None = None
    source_session_id: str | None = None
    source_quote: str | None = None
    revisions: list[MemoryRevision] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to a JSON-storable dict.

        Returns:
            dict: Entry dict
        """
        data: dict[str, Any] = {
            "id": self.id,
            "category": self.category,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.source_type:
            data["source_type"] = self.source_type
        if self.source_session_id:
            data["source_session_id"] = self.source_session_id
        if self.source_quote:
            data["source_quote"] = self.source_quote
        if self.revisions:
            data["revisions"] = [r.to_dict() for r in self.revisions]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """
        Deserialize from dict.

        Args:
            data (dict): Stored dict

        Returns:
            MemoryEntry: Memory entry instance
        """
        revisions_raw = data.get("revisions") or []
        revisions = [
            MemoryRevision.from_dict(r)
            for r in revisions_raw
            if isinstance(r, dict)
        ]
        return cls(
            id=str(data["id"]),
            category=normalize_category(str(data["category"])),
            content=str(data["content"]),
            created_at=float(data.get("created_at", 0)),
            updated_at=float(data.get("updated_at", 0)),
            source_type=data.get("source_type") or None,
            source_session_id=data.get("source_session_id") or None,
            source_quote=data.get("source_quote") or None,
            revisions=revisions,
        )


@dataclass
class MemoryStore:
    """
    User memory store root structure (maps to user.json).

    Attributes:
        version (int): Schema version
        entries (list[MemoryEntry]): All memory entries
    """

    version: int = 1
    entries: list[MemoryEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to a JSON-storable dict.

        Returns:
            dict: Store structure
        """
        return {
            "version": self.version,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryStore:
        """
        Deserialize store from dict.

        Args:
            data (dict): JSON data

        Returns:
            MemoryStore: Store instance
        """
        entries = [MemoryEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(version=int(data.get("version", 1)), entries=entries)


@dataclass
class MemorySourceContext:
    """
    Source context when writing memory.

    Attributes:
        source_type (str): Source type
        source_session_id (str | None): Source session ID
        source_quote (str | None): User quote excerpt
    """

    source_type: str
    source_session_id: str | None = None
    source_quote: str | None = None


@dataclass
class MemoryOperation:
    """
    Memory change operation (for judge / extract).

    Attributes:
        action (str): add / update / delete
        category (str | None): Category for add
        content (str | None): Content for add/update
        entry_id (str | None): Entry ID for update/delete
    """

    action: MemoryAction
    category: str | None = None
    content: str | None = None
    entry_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryOperation:
        """
        Parse operation from LLM JSON output.

        Args:
            data (dict): Operation dict

        Returns:
            MemoryOperation: Operation instance
        """
        return cls(
            action=data["action"],
            category=data.get("category"),
            content=data.get("content"),
            entry_id=data.get("entry_id"),
        )


@dataclass
class ApplyResult:
    """
    Result of applying a batch of memory operations.

    Attributes:
        changed (bool): Whether anything changed
        entries (list[MemoryEntry]): All entries after change
        added_ids (list[str]): Added entry IDs
        updated_ids (list[str]): Updated entry IDs
        deleted_ids (list[str]): Deleted entry IDs
    """

    changed: bool
    entries: list[MemoryEntry]
    added_ids: list[str] = field(default_factory=list)
    updated_ids: list[str] = field(default_factory=list)
    deleted_ids: list[str] = field(default_factory=list)
