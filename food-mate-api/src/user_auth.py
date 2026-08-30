"""
User auth and session-id lookup based on user_info.csv.
"""

from __future__ import annotations

import csv
import hashlib
import random
import string
from dataclasses import dataclass
from datetime import datetime

from src.config import PROJECT_ROOT

USER_INFO_PATH = PROJECT_ROOT / "data" / "user_info.csv"


@dataclass(frozen=True)
class UserRecord:
    """User record from the CSV."""

    id: int
    uid: str
    pwd: str
    session: str
    nickname: str = ""
    # Whether to show debug/memory UI: 1 = show, 0 = hide
    is_show: int = 1
    last_time: str = ""


# English nickname pool for new users
_NICKNAME_POOL = [
    "Alex",
    "Blake",
    "Casey",
    "Dana",
    "Ellis",
    "Finn",
    "Gray",
    "Harper",
    "Indie",
    "Jordan",
    "Kai",
    "Logan",
    "Morgan",
    "Noah",
    "Olive",
    "Parker",
    "Quinn",
    "Riley",
    "Sage",
    "Taylor",
    "River",
    "Skyler",
    "Jamie",
    "Cameron",
    "Avery",
    "Reese",
    "Hayden",
    "Rowan",
]


def _parse_is_show(raw: str | None) -> int:
    """
    Parse the CSV is_show field as 0 or 1.

    Args:
        raw (str | None): Raw string

    Returns:
        int: 0 or 1; defaults to 1
    """
    value = (raw or "").strip()
    if value in ("0", "1"):
        return int(value)
    return 1


def _load_users() -> list[UserRecord]:
    """
    Load all user records from the CSV.

    Returns:
        list[UserRecord]: User list
    """
    if not USER_INFO_PATH.exists():
        return []

    users: list[UserRecord] = []
    with USER_INFO_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for index, row in enumerate(reader, start=1):
            uid = (row.get("uid") or "").strip()
            pwd = (row.get("pwd") or "").strip()
            session = (row.get("session") or "").strip()
            if not uid or not pwd or not session:
                continue
            raw_id = (row.get("id") or "").strip()
            user_id = int(raw_id) if raw_id.isdigit() else index
            users.append(
                UserRecord(
                    id=user_id,
                    uid=uid,
                    pwd=pwd,
                    session=session,
                    nickname=(row.get("nickname") or "").strip(),
                    is_show=_parse_is_show(row.get("is_show")),
                    last_time=(row.get("last_time") or "").strip(),
                )
            )
    return users


def _write_users(users: list[UserRecord]) -> None:
    """
    Write user records back to the CSV.

    Args:
        users (list[UserRecord]): User list

    Returns:
        None
    """
    USER_INFO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with USER_INFO_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["id", "uid", "pwd", "session", "nickname", "is_show", "last_time"]
        )
        for user in users:
            writer.writerow(
                [
                    user.id,
                    user.uid,
                    user.pwd,
                    user.session,
                    user.nickname,
                    user.is_show,
                    user.last_time,
                ]
            )


def generate_random_nickname(existing: set[str] | None = None) -> str:
    """
    Generate an English nickname that does not collide with existing users.

    Args:
        existing (set[str] | None): Taken nicknames; loaded from CSV if omitted

    Returns:
        str: English nickname
    """
    taken = existing if existing is not None else {u.nickname for u in _load_users()}
    available = [name for name in _NICKNAME_POOL if name not in taken]
    if available:
        return random.choice(available)
    for _ in range(1000):
        suffix = "".join(random.choices(string.ascii_lowercase, k=4))
        name = f"User{suffix}"
        if name not in taken:
            return name
    raise RuntimeError("无法生成唯一 nickname，请手动指定")


def generate_random_uid() -> str:
    """
    Generate a 6-digit uid that does not collide with existing users.

    Returns:
        str: 6-digit user ID
    """
    existing = {user.uid for user in _load_users()}
    for _ in range(1000):
        uid = f"{random.randint(100000, 999999)}"
        if uid not in existing:
            return uid
    raise RuntimeError("无法生成唯一 uid，请手动指定")


def generate_random_pwd() -> str:
    """
    Generate an 8-character alphanumeric password.

    Returns:
        str: 8-character random password
    """
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=8))


def compute_session(uid: str, pwd: str) -> str:
    """
    Hash uid concatenated with pwd into a 12-character session key.

    Args:
        uid (str): User ID
        pwd (str): Password

    Returns:
        str: 12-character hex session identifier
    """
    combined = f"{uid}{pwd}"
    return hashlib.md5(combined.encode("utf-8")).hexdigest()[:12]


def add_user(uid: str | None = None, pwd: str | None = None) -> UserRecord:
    """
    Add a user to user_info.csv; randomly generate uid/pwd if omitted.

    Args:
        uid (str | None): User ID, optional
        pwd (str | None): Password, optional

    Returns:
        UserRecord: Newly created user record

    Raises:
        ValueError: uid already exists
    """
    users = _load_users()
    existing_uids = {user.uid for user in users}

    final_uid = (uid or "").strip() or generate_random_uid()
    if final_uid in existing_uids:
        raise ValueError(f"uid 已存在: {final_uid}")

    final_pwd = (pwd or "").strip() or generate_random_pwd()
    session = compute_session(final_uid, final_pwd)
    nickname = generate_random_nickname({user.nickname for user in users})
    last_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    next_id = max((user.id for user in users), default=0) + 1

    record = UserRecord(
        id=next_id,
        uid=final_uid,
        pwd=final_pwd,
        session=session,
        nickname=nickname,
        is_show=1,
        last_time=last_time,
    )
    users.append(record)
    _write_users(users)
    return record


def authenticate(uid: str, pwd: str) -> UserRecord | None:
    """
    Check whether uid and password match.

    Args:
        uid (str): User ID
        pwd (str): Password

    Returns:
        UserRecord | None: Matching user record, or None
    """
    uid = uid.strip()
    pwd = pwd.strip()
    for user in _load_users():
        if user.uid == uid and user.pwd == pwd:
            return user
    return None


def get_user_by_session(user_session: str) -> UserRecord | None:
    """
    Look up a user by URL session identifier.

    Args:
        user_session (str): session column in the CSV

    Returns:
        UserRecord | None: User record if found, otherwise None
    """
    user_session = user_session.strip()
    for user in _load_users():
        if user.session == user_session:
            return user
    return None


def get_user_by_uid(uid: str) -> UserRecord | None:
    """
    Look up a user by user ID.

    Args:
        uid (str): User ID

    Returns:
        UserRecord | None: User record if found, otherwise None
    """
    uid = uid.strip()
    for user in _load_users():
        if user.uid == uid:
            return user
    return None


def touch_last_login(uid: str) -> None:
    """
    Update the user's last login time.

    Args:
        uid (str): User ID

    Returns:
        None
    """
    users = _load_users()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated: list[UserRecord] = []
    changed = False
    for user in users:
        if user.uid == uid:
            updated.append(
                UserRecord(
                    id=user.id,
                    uid=user.uid,
                    pwd=user.pwd,
                    session=user.session,
                    nickname=user.nickname,
                    is_show=user.is_show,
                    last_time=now,
                )
            )
            changed = True
        else:
            updated.append(user)
    if changed:
        _write_users(updated)


def public_user_info(user: UserRecord) -> dict[str, str | int]:
    """
    Return user info that is safe to expose to the frontend.

    Args:
        user (UserRecord): User record

    Returns:
        dict: uid, session, nickname, and is_show
    """
    return {
        "uid": user.uid,
        "session": user.session,
        "nickname": user.nickname or user.uid,
        "is_show": user.is_show,
    }
