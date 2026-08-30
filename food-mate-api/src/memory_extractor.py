"""
Memory extractor — merge session log preferences into long-term user.md profile.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.llm_client import LLMClient
from src.config import DEFAULT_MODEL
from src.memory_schema import MEMORY_CATEGORIES, categories_prompt_block


EXPECTED_USER_HEADINGS = [f"## {cat}" for cat in MEMORY_CATEGORIES]


@dataclass(frozen=True)
class ExtractResult:
    """
    Memory extraction result.

    Attributes:
        updated_user_markdown (str): Updated full user.md content
        changed (bool): Whether content changed (string comparison)
    """

    updated_user_markdown: str
    changed: bool


def _strip_code_fences(text: str) -> str:
    """
    Remove code fence wrappers from model output (e.g. ```markdown ... ```).

    Args:
        text (str): Raw output

    Returns:
        str: Clean Markdown
    """
    cleaned = text.strip()
    if cleaned.startswith("```markdown"):
        cleaned = cleaned[len("```markdown") :].lstrip("\n")
    elif cleaned.startswith("```md"):
        cleaned = cleaned[len("```md") :].lstrip("\n")
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```") :].lstrip("\n")

    if cleaned.endswith("```"):
        cleaned = cleaned[: -len("```")].rstrip()
    return cleaned.strip()


def _has_expected_headings(user_markdown: str) -> bool:
    """
    Check whether user.md contains all expected section headings.

    Args:
        user_markdown (str): user.md content

    Returns:
        bool: Whether headings are present
    """
    return all(h in user_markdown for h in EXPECTED_USER_HEADINGS)


def extract_and_merge_user_from_session(
    session_content: str,
    current_user_markdown: str,
    *,
    model: str = DEFAULT_MODEL,
    max_session_chars: int = 12000,
) -> ExtractResult:
    """
    Extract preference updates from session log and merge into long-term user.md.

    Args:
        session_content (str): Formatted recent web chat session text
        current_user_markdown (str): Current user.md content
        model (str): Model for extraction
        max_session_chars (int): Max session chars sent to LLM (tail kept)

    Returns:
        ExtractResult: Updated user.md and changed flag
    """
    session_excerpt = (session_content or "").strip()
    if len(session_excerpt) > max_session_chars:
        session_excerpt = session_excerpt[-max_session_chars:]

    llm = LLMClient(default_model=model)
    category_guide = categories_prompt_block()
    system_prompt = (
        "You are the FoodMate memory extractor for a home cooking assistant. "
        "Update the long-term user.md cooking profile from recent session logs. "
        "Keep exactly five fixed English section headings and output the complete user.md ready to save. "
        "Place each bullet under the correct category; prefer the first four categories over Other. "
        "ONE keyword fact = ONE bullet. Never join different facts with '; ' on the same line "
        "(e.g. write two bullets '- lactose intolerant' and '- peanut allergy', not one combined line). "
        "No full sentences or parenthetical explanations. "
        "Merge only near-duplicate bullets about the SAME fact "
        "(e.g. 'likes spicy' and 'prefers spicy food'); "
        "keep distinct facts as separate bullets "
        "(e.g. 'likes spicy' and 'likes sour' must be two bullets). "
        "On conflicting facts about the same topic, keep the newer session info. "
        "Keep entry wording in the same language as the evidence from the session when possible."
    )

    user_prompt = f"""
Update the user food profile below from the latest session log.

Requirements (all must be met):
1. Structure: include exactly these section headings (do not remove or rename):
{chr(10).join(EXPECTED_USER_HEADINGS)}
2. Category meanings:
{category_guide}
3. Do not drop valid existing information; you may condense, reorder, or add.
4. ONE fact = ONE bullet. Distinct facts stay as separate bullets (do not join with '; ').
   Only merge bullets that are near-duplicates of the SAME fact
   (e.g. 'likes spicy' and 'prefers spicy food'). Keep the existing [mem_xxx] id of the older entry when merging.
   'likes spicy' and 'likes sour' (喜欢吃辣 vs 喜欢吃酸的) MUST remain two bullets.
5. On conflict (contradictory facts about the same topic, e.g. "likes spicy" vs "avoids spicy"),
   keep only the newer information from the session log and drop/overwrite the outdated one.
   Prefer session evidence over older profile bullets when they disagree.
6. If a section is unknown, keep "(None yet)".
7. Output only the complete updated user.md Markdown:
   - No explanation
   - No code fences
   - Must start with `# User Food Profile` if the current profile uses that title
   - Preserve existing [mem_xxx] ids for unchanged or updated bullets; only omit ids for brand-new bullets

Current user.md:
```md
{current_user_markdown.strip()}
```

Latest session log:
```md
{session_excerpt}
```
""".strip()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    response = llm.chat(messages=messages)
    updated = _strip_code_fences(response.content or "")

    if not _has_expected_headings(updated):
        return ExtractResult(updated_user_markdown=current_user_markdown, changed=False)

    changed = updated.strip() != (current_user_markdown or "").strip()
    return ExtractResult(updated_user_markdown=updated, changed=changed)
