"""
基于 user_info.csv 的用户认证与会话标识解析。
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
    """CSV 中的用户记录。"""

    id: int
    uid: str
    pwd: str
    session: str
    nickname: str = ""
    # 是否展示调试/记忆相关 UI：1=展示，0=隐藏
    is_show: int = 1
    last_time: str = ""


# 新用户可用的英文昵称池
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
    将 CSV 中的 is_show 字段解析为 0 或 1。

    参数:
        raw (str | None): 原始字符串

    返回:
        int: 0 或 1，缺省为 1
    """
    value = (raw or "").strip()
    if value in ("0", "1"):
        return int(value)
    return 1


def _load_users() -> list[UserRecord]:
    """
    从 CSV 加载全部用户记录。

    返回:
        list[UserRecord]: 用户列表
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
    将用户记录写回 CSV。

    参数:
        users (list[UserRecord]): 用户列表

    返回:
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
    生成不与现有用户冲突的英文昵称。

    参数:
        existing (set[str] | None): 已占用的昵称集合，缺省时从 CSV 加载

    返回:
        str: 英文昵称
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
    生成不与现有用户冲突的 6 位数字 uid。

    返回:
        str: 6 位数字用户 ID
    """
    existing = {user.uid for user in _load_users()}
    for _ in range(1000):
        uid = f"{random.randint(100000, 999999)}"
        if uid not in existing:
            return uid
    raise RuntimeError("无法生成唯一 uid，请手动指定")


def generate_random_pwd() -> str:
    """
    生成 8 位数字与字母组合的密码。

    返回:
        str: 8 位随机密码
    """
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=8))


def compute_session(uid: str, pwd: str) -> str:
    """
    根据 uid 与 pwd 拼接后加密，生成 12 位 session 密钥。

    参数:
        uid (str): 用户 ID
        pwd (str): 密码

    返回:
        str: 12 位十六进制 session 标识
    """
    combined = f"{uid}{pwd}"
    return hashlib.md5(combined.encode("utf-8")).hexdigest()[:12]


def add_user(uid: str | None = None, pwd: str | None = None) -> UserRecord:
    """
    向 user_info.csv 添加用户；uid、pwd 未提供时随机生成。

    参数:
        uid (str | None): 用户 ID，可选
        pwd (str | None): 密码，可选

    返回:
        UserRecord: 新创建的用户记录

    异常:
        ValueError: uid 已存在
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
    校验 uid 与密码是否匹配。

    参数:
        uid (str): 用户 ID
        pwd (str): 密码

    返回:
        UserRecord | None: 匹配成功返回用户记录，否则 None
    """
    uid = uid.strip()
    pwd = pwd.strip()
    for user in _load_users():
        if user.uid == uid and user.pwd == pwd:
            return user
    return None


def get_user_by_session(user_session: str) -> UserRecord | None:
    """
    通过 URL session 标识查找用户。

    参数:
        user_session (str): CSV 中的 session 列

    返回:
        UserRecord | None: 找到则返回用户记录，否则 None
    """
    user_session = user_session.strip()
    for user in _load_users():
        if user.session == user_session:
            return user
    return None


def get_user_by_uid(uid: str) -> UserRecord | None:
    """
    通过用户 ID 查找用户。

    参数:
        uid (str): 用户 ID

    返回:
        UserRecord | None: 找到则返回用户记录，否则 None
    """
    uid = uid.strip()
    for user in _load_users():
        if user.uid == uid:
            return user
    return None


def touch_last_login(uid: str) -> None:
    """
    更新用户最近登录时间。

    参数:
        uid (str): 用户 ID

    返回:
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
    返回可安全暴露给前端的用户信息。

    参数:
        user (UserRecord): 用户记录

    返回:
        dict: 含 uid、session、nickname 与 is_show
    """
    return {
        "uid": user.uid,
        "session": user.session,
        "nickname": user.nickname or user.uid,
        "is_show": user.is_show,
    }
