#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TG Manager — مدیریت کامل اکانت تلگرام (Userbot روی Telethon / MTProto)

ورود: شماره تلفن + کد تأیید (+ رمز دو مرحله‌ای در صورت فعال بودن) داخل ترمینال.
کنترل: فقط پیام‌هایی که «خودِ اکانت» می‌فرستد و با پیشوند (پیش‌فرض ".") شروع می‌شوند.
        بهترین جا برای تایپ دستورها: Saved Messages. دستور `.help` را بزن.

امنیت:
  * هیچ دستور eval/shell وجود ندارد.
  * دستورهای حساس (نشست‌ها، حریم خصوصی، مخاطبین، بکاپ...) فقط در Saved Messages اجرا می‌شوند.
  * دستورهای مخرب نیاز به تأیید صریح (yes) دارند.
  * فایل data/account.session = کلید کامل اکانت. هرگز به اشتراک نگذار.
"""
from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from getpass import getpass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv اختیاری است
    pass

try:
    from telethon import TelegramClient, events, functions, types, utils
    from telethon.errors import (
        ApiIdInvalidError,
        ChatAdminRequiredError,
        FloodWaitError,
        MessageDeleteForbiddenError,
        MessageNotModifiedError,
        PasswordHashInvalidError,
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        PhoneNumberBannedError,
        PhoneNumberInvalidError,
        PhoneNumberUnoccupiedError,
        RPCError,
        SessionPasswordNeededError,
    )
except ImportError:
    sys.exit("Telethon نصب نیست. اجرا کن:  pip install -r requirements.txt")

VERSION = "1.0.0"
MAX_TEXT = 3900
log = logging.getLogger("tgmanager")

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_ERR_FA = {
    "ChatAdminRequiredError": "برای این کار باید ادمین باشی.",
    "ChatWriteForbiddenError": "اجازه‌ی ارسال پیام در این چت را نداری.",
    "UserNotParticipantError": "این کاربر عضو چت نیست.",
    "UserAdminInvalidError": "روی ادمین‌ها نمی‌شود این کار را کرد.",
    "UsernameOccupiedError": "این یوزرنیم گرفته شده است.",
    "UsernameInvalidError": "یوزرنیم نامعتبر است.",
    "UsernameNotOccupiedError": "چنین یوزرنیمی وجود ندارد.",
    "AboutTooLongError": "متن بیو بیش از حد طولانی است.",
    "PeerFloodError": "تلگرام موقتاً محدودیت اسپم اعمال کرده؛ کمی صبر کن.",
    "InviteHashExpiredError": "لینک دعوت منقضی شده است.",
    "InviteHashInvalidError": "لینک دعوت نامعتبر است.",
    "UserAlreadyParticipantError": "از قبل عضو هستی.",
    "ChannelsTooMuchError": "به سقف تعداد گروه/کانال رسیده‌ای.",
    "FreshResetAuthorisationForbiddenError": "نشست‌های جدید (کمتر از ۲۴ ساعت) قابل حذف نیستند.",
    "MessageIdInvalidError": "شناسه‌ی پیام نامعتبر است.",
    "MessageDeleteForbiddenError": "اجازه‌ی حذف این پیام‌ها را نداری.",
    "ScheduleTooMuchError": "تعداد پیام‌های زمان‌بندی‌شده به سقف رسیده است.",
    "ScheduleDateTooLateError": "زمان‌بندی بیش از حد دور است.",
}


# ───────────────────────────── تنظیمات ─────────────────────────────
@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    prefix: str
    data_dir: Path

    @property
    def session_path(self) -> Path:
        return self.data_dir / "account"

    @property
    def downloads(self) -> Path:
        return self.data_dir / "downloads"

    @property
    def exports(self) -> Path:
        return self.data_dir / "exports"

    @classmethod
    def load(cls) -> "Config":
        raw_id = os.getenv("TG_API_ID", "").strip()
        api_hash = os.getenv("TG_API_HASH", "").strip()
        if not raw_id.isdigit() or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
            sys.exit(
                "TG_API_ID / TG_API_HASH تنظیم نشده یا نامعتبر است.\n"
                "از https://my.telegram.org  ←  API development tools بگیر و در فایل .env بگذار."
            )
        prefix = os.getenv("TG_PREFIX", ".") or "."
        data_dir = Path(os.getenv("TG_DATA_DIR", "data")).expanduser().resolve()
        for d in (data_dir, data_dir / "downloads", data_dir / "exports"):
            d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(data_dir, 0o700)
        except OSError:
            pass
        return cls(int(raw_id), api_hash, prefix, data_dir)


class State:
    """وضعیت کوچک و پایدار (مثلاً حالت AFK) در یک فایل JSON با نوشتن اتمیک."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {"afk": None}
        try:
            if path.exists():
                self.data.update(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError):
            log.warning("state file unreadable; starting fresh")

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, self.path)


@dataclass
class App:
    client: TelegramClient
    cfg: Config
    state: State
    me: types.User
    stop_event: asyncio.Event
    tasks: set = field(default_factory=set)
    afk_seen: dict = field(default_factory=dict)

    def spawn(self, coro: Awaitable) -> None:
        t = asyncio.ensure_future(coro)
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)


# ───────────────────────────── ابزارک‌ها ─────────────────────────────
class CommandError(Exception):
    """خطای قابل‌نمایش به کاربر."""


def esc(v: Any) -> str:
    return html.escape(str(v), quote=False)


def strip_html(t: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", t))


def split_first(s: str) -> tuple[str, str]:
    parts = s.strip().split(None, 1)
    if not parts:
        return "", ""
    return parts[0], (parts[1] if len(parts) > 1 else "")


def strip_confirm(args: str) -> tuple[str, bool]:
    toks = args.split()
    if toks and toks[-1].lower() in ("yes", "y"):
        return " ".join(toks[:-1]), True
    return args.strip(), False


_DUR_RE = re.compile(r"(\d+)([smhdw])")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> Optional[timedelta]:
    text = text.strip().lower()
    if not re.fullmatch(r"(?:\d+[smhdw])+", text):
        return None
    secs = sum(int(n) * _UNITS[u] for n, u in _DUR_RE.findall(text))
    return timedelta(seconds=secs) if secs > 0 else None


def fmt_secs(secs: float) -> str:
    secs = int(secs)
    d, r = divmod(secs, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = [f"{v}{u}" for v, u in ((d, "d"), (h, "h"), (m, "m")) if v]
    return " ".join(parts) or f"{s}s"


def kind_of(e: Any) -> str:
    if isinstance(e, types.User):
        return "bot" if e.bot else "user"
    if isinstance(e, types.Channel):
        return "supergroup" if e.megagroup else "channel"
    if isinstance(e, types.Chat):
        return "group"
    return type(e).__name__


def display_name(e: Any) -> str:
    if isinstance(e, types.User):
        name = " ".join(p for p in (e.first_name, e.last_name) if p)
        return name or e.username or str(e.id)
    return getattr(e, "title", None) or str(getattr(e, "id", "?"))


def msg_to_dict(m: types.Message) -> dict:
    return {
        "id": m.id,
        "date": m.date.isoformat() if m.date else None,
        "edit_date": m.edit_date.isoformat() if m.edit_date else None,
        "sender_id": m.sender_id,
        "out": bool(m.out),
        "text": m.raw_text or "",
        "reply_to": m.reply_to_msg_id,
        "media": type(m.media).__name__ if m.media else None,
        "views": m.views,
        "forwards": m.forwards,
    }


async def _delete_later(msg: types.Message, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:  # noqa: BLE001 — حذف بهینه‌کار است
        pass


# ───────────────────────────── ثبت دستورها ─────────────────────────────
@dataclass
class Command:
    name: str
    func: Callable[["Ctx"], Awaitable[None]]
    usage: str
    desc: str
    category: str
    private_only: bool = False


COMMANDS: dict[str, Command] = {}


def command(name: str, usage: str, desc: str, category: str,
            aliases: tuple[str, ...] = (), private_only: bool = False):
    def deco(fn):
        cmd = Command(name, fn, usage, desc, category, private_only)
        COMMANDS[name] = cmd
        for a in aliases:
            COMMANDS[a] = cmd
        return fn

    return deco


class Ctx:
    def __init__(self, app: App, event: events.NewMessage.Event, args: str):
        self.app = app
        self.event = event
        self.args = args.strip()

    @property
    def client(self) -> TelegramClient:
        return self.app.client

    @property
    def cfg(self) -> Config:
        return self.app.cfg

    @property
    def in_saved(self) -> bool:
        return self.event.chat_id == self.app.me.id

    # ── خروجی ──
    async def say(self, text: str) -> None:
        if len(text) > MAX_TEXT:
            buf = io.BytesIO(strip_html(text).encode("utf-8"))
            buf.name = "output.txt"
            await self.client.send_file(self.event.chat_id, buf, caption="📄 خروجی طولانی")
            text = "📄 خروجی طولانی بود؛ به صورت فایل ارسال شد."
        try:
            await self.event.edit(text, parse_mode="html", link_preview=False)
        except MessageNotModifiedError:
            pass
        except RPCError:
            await self.client.send_message(
                self.event.chat_id, text, parse_mode="html", link_preview=False
            )

    async def flash(self, text: str, delay: float = 4.0) -> None:
        """نمایش کوتاه نتیجه و حذف خودکار خودِ پیام دستور."""
        await self.say(text)
        self.app.spawn(_delete_later(self.event.message, delay))

    async def notice(self, text: str, delay: float = 3.0) -> None:
        """پیام جدید و موقت (وقتی پیام دستور حذف شده است)."""
        m = await self.client.send_message(self.event.chat_id, text, parse_mode="html")
        self.app.spawn(_delete_later(m, delay))

    # ── مقصدها ──
    async def entity(self, arg: str):
        arg = arg.strip()
        if arg.lower() in ("me", "self", "saved"):
            return await self.client.get_me()
        key: Any = int(arg) if re.fullmatch(r"-?\d+", arg) else arg
        try:
            return await self.client.get_entity(key)
        except (ValueError, TypeError) as e:
            raise CommandError(f"مقصد «{arg}» پیدا نشد.") from e

    async def chat(self, arg: str = ""):
        return await self.entity(arg) if arg else await self.event.get_chat()

    async def need_reply(self) -> types.Message:
        rm = await self.event.get_reply_message()
        if not rm:
            raise CommandError("روی یک پیام ریپلای کن.")
        return rm

    async def user_and_rest(self) -> tuple[Any, str]:
        """کاربر هدف از ریپلای (و بقیه‌ی آرگومان) یا از اولین آرگومان."""
        rm = await self.event.get_reply_message()
        if rm:
            sender = await rm.get_sender()
            if sender is None:
                raise CommandError("فرستنده‌ی پیام مشخص نیست.")
            return sender, self.args
        tok, rest = split_first(self.args)
        if not tok:
            raise CommandError("کاربر را با ریپلای یا @username/ID مشخص کن.")
        return await self.entity(tok), rest

    async def group_chat(self):
        chat = await self.event.get_chat()
        if kind_of(chat) not in ("group", "supergroup", "channel"):
            raise CommandError("این دستور فقط در گروه/کانال کار می‌کند.")
        return chat


# ───────────────────────────── دستورهای عمومی ─────────────────────────────
@command("help", "help [دستور]", "راهنما", "عمومی", aliases=("h", "start"))
async def cmd_help(c: Ctx):
    p = c.cfg.prefix
    name = c.args.lower().removeprefix(p)
    if name:
        cmd = COMMANDS.get(name)
        if not cmd:
            raise CommandError("چنین دستوری نیست.")
        lock = "\n🔒 فقط در Saved Messages" if cmd.private_only else ""
        return await c.say(f"<code>{esc(p + cmd.usage)}</code>\n{esc(cmd.desc)}{lock}")
    cats: dict[str, list[Command]] = {}
    seen: set[str] = set()
    for cmd in COMMANDS.values():
        if cmd.name not in seen:
            seen.add(cmd.name)
            cats.setdefault(cmd.category, []).append(cmd)
    out = [f"<b>TG Manager v{VERSION}</b> — <code>{esc(p)}help &lt;دستور&gt;</code> برای جزئیات"]
    for cat, cmds in cats.items():
        out.append(f"\n<b>{esc(cat)}</b>")
        for cmd in sorted(cmds, key=lambda x: x.name):
            lock = " 🔒" if cmd.private_only else ""
            out.append(f"<code>{esc(p + cmd.name)}</code>{lock} — {esc(cmd.desc)}")
    await c.say("\n".join(out))


@command("ping", "ping", "تست تأخیر اتصال", "عمومی")
async def cmd_ping(c: Ctx):
    t0 = time.perf_counter()
    await c.client(functions.PingRequest(ping_id=int(t0 * 1000) % (2**31)))
    ms = (time.perf_counter() - t0) * 1000
    await c.say(f"🏓 Pong — <b>{ms:.0f} ms</b>")


@command("id", "id", "شناسه‌ی چت/پیام/فرستنده (با ریپلای)", "عمومی")
async def cmd_id(c: Ctx):
    lines = [f"💬 Chat: <code>{c.event.chat_id}</code>", f"✉️ Message: <code>{c.event.id}</code>"]
    rm = await c.event.get_reply_message()
    if rm:
        lines.append(f"↩️ Reply: <code>{rm.id}</code>")
        lines.append(f"👤 Sender: <code>{rm.sender_id}</code>")
    await c.say("\n".join(lines))


@command("stop", "stop", "توقف امن ربات", "عمومی")
async def cmd_stop(c: Ctx):
    await c.say("⏹ متوقف شد.")
    c.app.stop_event.set()


# ───────────────────────────── اکانت و پروفایل ─────────────────────────────
@command("me", "me", "اطلاعات اکانت من", "اکانت")
async def cmd_me(c: Ctx):
    me = await c.client.get_me()
    phone = me.phone or ""
    if phone and not c.in_saved:
        phone = phone[:3] + "•••" + phone[-2:]
    lines = [
        f"👤 <b>{esc(display_name(me))}</b>",
        f"🆔 <code>{me.id}</code>",
        f"🔗 @{esc(me.username)}" if me.username else "🔗 —",
        f"📱 <code>{esc(phone or '—')}</code>",
        f"⭐ Premium: {'بله' if getattr(me, 'premium', False) else 'خیر'}",
    ]
    await c.say("\n".join(lines))


@command("stats", "stats", "آمار گفتگوها (پی‌وی/گروه/کانال/نخوانده)", "اکانت", private_only=True)
async def cmd_stats(c: Ctx):
    users = bots = groups = channels = unread = 0
    async for d in c.client.iter_dialogs():
        unread += d.unread_count
        if d.is_user:
            if getattr(d.entity, "bot", False):
                bots += 1
            else:
                users += 1
        elif d.is_group:
            groups += 1
        elif d.is_channel:
            channels += 1
    await c.say(
        f"📊 کاربران: <b>{users}</b> | ربات‌ها: <b>{bots}</b>\n"
        f"👥 گروه‌ها: <b>{groups}</b> | 📢 کانال‌ها: <b>{channels}</b>\n"
        f"🔔 پیام نخوانده: <b>{unread}</b>"
    )


@command("setname", "setname نام | نام‌خانوادگی", "تغییر نام نمایشی", "اکانت")
async def cmd_setname(c: Ctx):
    first, _, last = c.args.partition("|")
    first, last = first.strip(), last.strip()
    if not first:
        raise CommandError("نام را وارد کن: setname نام | نام‌خانوادگی")
    await c.client(functions.account.UpdateProfileRequest(first_name=first, last_name=last))
    await c.flash("✅ نام تغییر کرد.")


@command("setbio", "setbio متن", "تغییر بیو (خالی = حذف)", "اکانت")
async def cmd_setbio(c: Ctx):
    await c.client(functions.account.UpdateProfileRequest(about=c.args))
    await c.flash("✅ بیو تغییر کرد.")


@command("setusername", "setusername نام", "تغییر یوزرنیم (خالی = حذف)", "اکانت")
async def cmd_setusername(c: Ctx):
    await c.client(functions.account.UpdateUsernameRequest(username=c.args.lstrip("@")))
    await c.flash("✅ یوزرنیم به‌روزرسانی شد.")


@command("setphoto", "setphoto (ریپلای روی عکس)", "تنظیم عکس پروفایل", "اکانت")
async def cmd_setphoto(c: Ctx):
    rm = await c.need_reply()
    if not rm.photo:
        raise CommandError("پیام ریپلای‌شده عکس ندارد.")
    path = await rm.download_media(file=str(c.cfg.downloads) + os.sep)
    try:
        uploaded = await c.client.upload_file(path)
        await c.client(functions.photos.UploadProfilePhotoRequest(file=uploaded))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    await c.flash("✅ عکس پروفایل تنظیم شد.")


@command("delphotos", "delphotos yes", "حذف همه‌ی عکس‌های پروفایل", "اکانت")
async def cmd_delphotos(c: Ctx):
    _, ok = strip_confirm(c.args)
    if not ok:
        raise CommandError("برای تأیید بنویس: delphotos yes")
    photos = await c.client.get_profile_photos("me")
    if not photos:
        raise CommandError("عکسی وجود ندارد.")
    await c.client(functions.photos.DeletePhotosRequest(id=[utils.get_input_photo(p) for p in photos]))
    await c.flash(f"✅ {len(photos)} عکس حذف شد.")


@command("status", "status online|offline", "تنظیم وضعیت آنلاین/آفلاین", "اکانت")
async def cmd_status(c: Ctx):
    v = c.args.lower()
    if v not in ("online", "offline"):
        raise CommandError("status online  یا  status offline")
    await c.client(functions.account.UpdateStatusRequest(offline=(v == "offline")))
    await c.flash(f"✅ وضعیت: {v}")


# ───────────────────────────── امنیت و حریم خصوصی ─────────────────────────────
@command("sessions", "sessions", "فهرست نشست‌های فعال", "امنیت", private_only=True)
async def cmd_sessions(c: Ctx):
    res = await c.client(functions.account.GetAuthorizationsRequest())
    lines = ["<b>نشست‌های فعال</b>"]
    for a in res.authorizations:
        cur = " ✅ (این نشست)" if a.current else ""
        lines.append(
            f"\n<code>{a.hash}</code>{cur}\n"
            f"{esc(a.app_name)} {esc(a.app_version)} — {esc(a.device_model)} / {esc(a.platform)}\n"
            f"🌍 {esc(a.country)} · {esc(a.ip)} · {a.date_active:%Y-%m-%d %H:%M} UTC"
        )
    await c.say("\n".join(lines))


@command("kill", "kill <hash>", "بستن یک نشست مشخص", "امنیت", private_only=True)
async def cmd_kill(c: Ctx):
    if not re.fullmatch(r"-?\d+", c.args):
        raise CommandError("hash عددی نشست را بده (از sessions).")
    await c.client(functions.account.ResetAuthorizationRequest(hash=int(c.args)))
    await c.flash("✅ نشست بسته شد.")


@command("killothers", "killothers yes", "بستن همه‌ی نشست‌ها به جز نشست فعلی", "امنیت", private_only=True)
async def cmd_killothers(c: Ctx):
    _, ok = strip_confirm(c.args)
    if not ok:
        raise CommandError("برای تأیید بنویس: killothers yes")
    await c.client(functions.auth.ResetAuthorizationsRequest())
    await c.flash("✅ سایر نشست‌ها بسته شدند.")


@command("privacy", "privacy <کلید> <everyone|contacts|nobody>",
         "حریم خصوصی؛ کلیدها: lastseen phone photo calls forwards invite bio", "امنیت", private_only=True)
async def cmd_privacy(c: Ctx):
    keys = {
        "lastseen": types.InputPrivacyKeyStatusTimestamp,
        "phone": types.InputPrivacyKeyPhoneNumber,
        "photo": types.InputPrivacyKeyProfilePhoto,
        "calls": types.InputPrivacyKeyPhoneCall,
        "forwards": types.InputPrivacyKeyForwards,
        "invite": types.InputPrivacyKeyChatInvite,
        "bio": types.InputPrivacyKeyAbout,
    }
    rules = {
        "everyone": types.InputPrivacyValueAllowAll,
        "contacts": types.InputPrivacyValueAllowContacts,
        "nobody": types.InputPrivacyValueDisallowAll,
    }
    k_raw, v_raw = split_first(c.args)
    k, v = k_raw.lower(), v_raw.strip().lower()
    if k not in keys or v not in rules:
        raise CommandError("مثال: privacy lastseen nobody\nکلیدها: " + " ".join(keys))
    await c.client(functions.account.SetPrivacyRequest(key=keys[k](), rules=[rules[v]()]))
    await c.flash(f"✅ {k} → {v}")


@command("logout", "logout yes", "خروج از اکانت و حذف نشست این ربات", "امنیت", private_only=True)
async def cmd_logout(c: Ctx):
    _, ok = strip_confirm(c.args)
    if not ok:
        raise CommandError("برای تأیید بنویس: logout yes")
    await c.say("👋 خارج شدم.")
    await c.client.log_out()
    c.app.stop_event.set()


# ───────────────────────────── مخاطبین ─────────────────────────────
@command("contacts", "contacts [تعداد]", "فهرست مخاطبین", "مخاطبین", private_only=True)
async def cmd_contacts(c: Ctx):
    limit = int(c.args) if c.args.isdigit() else 50
    res = await c.client(functions.contacts.GetContactsRequest(hash=0))
    users = list(getattr(res, "users", []))
    lines = [f"<b>مخاطبین ({len(users)})</b>"]
    for u in users[:limit]:
        un = f" @{esc(u.username)}" if u.username else ""
        lines.append(f"• {esc(display_name(u))}{un} — <code>{u.id}</code>")
    await c.say("\n".join(lines))


@command("addcontact", "addcontact +98... نام | نام‌خانوادگی", "افزودن مخاطب با شماره", "مخاطبین", private_only=True)
async def cmd_addcontact(c: Ctx):
    phone, rest = split_first(c.args)
    first, _, last = rest.partition("|")
    if not re.fullmatch(r"\+?\d{7,15}", phone) or not first.strip():
        raise CommandError("مثال: addcontact +989121234567 علی | رضایی")
    res = await c.client(functions.contacts.ImportContactsRequest(
        contacts=[types.InputPhoneContact(client_id=0, phone=phone,
                                          first_name=first.strip(), last_name=last.strip())]
    ))
    if not res.users:
        raise CommandError("این شماره در تلگرام ثبت‌نام نکرده است.")
    await c.flash("✅ مخاطب اضافه شد.")


@command("delcontact", "delcontact <کاربر>", "حذف مخاطب", "مخاطبین", private_only=True)
async def cmd_delcontact(c: Ctx):
    user = await c.entity(c.args) if c.args else None
    if user is None:
        raise CommandError("کاربر را مشخص کن.")
    await c.client(functions.contacts.DeleteContactsRequest(id=[user]))
    await c.flash("✅ مخاطب حذف شد.")


@command("block", "block [کاربر]", "بلاک کاربر (ریپلای/آرگومان)", "مخاطبین")
async def cmd_block(c: Ctx):
    user, _ = await c.user_and_rest()
    await c.client(functions.contacts.BlockRequest(id=user))
    await c.flash("🚫 بلاک شد.")


@command("unblock", "unblock [کاربر]", "رفع بلاک", "مخاطبین")
async def cmd_unblock(c: Ctx):
    user, _ = await c.user_and_rest()
    await c.client(functions.contacts.UnblockRequest(id=user))
    await c.flash("✅ بلاک برداشته شد.")


# ───────────────────────────── پیام‌ها ─────────────────────────────
@command("send", "send <مقصد> <متن>", "ارسال پیام به مقصد (me = Saved Messages)", "پیام‌ها")
async def cmd_send(c: Ctx):
    dest, text = split_first(c.args)
    if not dest or not text:
        raise CommandError("send <مقصد> <متن>")
    ent = await c.entity(dest)
    await c.client.send_message(ent, text, parse_mode=None)
    await c.flash("✅ ارسال شد.")


@command("fwd", "fwd <مقصد> (ریپلای)", "فوروارد پیام", "پیام‌ها")
async def cmd_fwd(c: Ctx):
    rm = await c.need_reply()
    ent = await c.entity(c.args)
    await c.client.forward_messages(ent, rm)
    await c.flash("✅ فوروارد شد.")


@command("copy", "copy <مقصد> (ریپلای)", "ارسال کپی پیام بدون برچسب فوروارد", "پیام‌ها")
async def cmd_copy(c: Ctx):
    rm = await c.need_reply()
    ent = await c.entity(c.args)
    await c.client.send_message(ent, rm)
    await c.flash("✅ کپی ارسال شد.")


@command("save", "save (ریپلای)", "ذخیره‌ی پیام در Saved Messages", "پیام‌ها")
async def cmd_save(c: Ctx):
    rm = await c.need_reply()
    await c.client.forward_messages("me", rm)
    await c.flash("💾 ذخیره شد.")


@command("del", "del [تعداد]", "حذف N پیام آخرِ خودت در این چت", "پیام‌ها")
async def cmd_del(c: Ctx):
    n = int(c.args) if c.args.isdigit() else 1
    if not 1 <= n <= 1000:
        raise CommandError("تعداد باید بین ۱ تا ۱۰۰۰ باشد.")
    chat = await c.event.get_input_chat()
    ids = {c.event.id}
    async for m in c.client.iter_messages(chat, limit=n + 1, from_user="me"):
        ids.add(m.id)
        if len(ids) >= n + 1:
            break
    await c.client.delete_messages(chat, list(ids), revoke=True)
    await c.notice(f"🗑 {len(ids) - 1} پیام حذف شد.")


@command("purge", "purge yes (ریپلای روی پیام شروع)", "حذف همه‌ی پیام‌ها از پیام ریپلای‌شده تا آخر (در گروه: نیاز به دسترسی)", "پیام‌ها")
async def cmd_purge(c: Ctx):
    rm = await c.need_reply()
    _, ok = strip_confirm(c.args)
    if not ok:
        raise CommandError("برای تأیید بنویس: purge yes (با ریپلای روی پیام شروع)")
    chat = await c.event.get_input_chat()
    ids = [m.id async for m in c.client.iter_messages(chat, min_id=rm.id - 1, limit=5000)]
    try:
        await c.client.delete_messages(chat, ids, revoke=True)
    except (MessageDeleteForbiddenError, ChatAdminRequiredError):
        ids = [m.id async for m in c.client.iter_messages(
            chat, min_id=rm.id - 1, limit=5000, from_user="me")]
        if c.event.id not in ids:
            ids.append(c.event.id)
        await c.client.delete_messages(chat, ids, revoke=True)
    await c.notice(f"🧹 {len(ids)} پیام حذف شد.")


@command("schedule", "schedule <مدت> <متن>", "زمان‌بندی پیام؛ مدت: 30s 10m 2h 1d 1h30m", "پیام‌ها")
async def cmd_schedule(c: Ctx):
    dur_s, text = split_first(c.args)
    dur = parse_duration(dur_s)
    if dur is None or not text:
        raise CommandError("مثال: schedule 2h یادآوری جلسه")
    if not timedelta(seconds=30) <= dur <= timedelta(days=365):
        raise CommandError("مدت باید بین ۳۰ ثانیه و ۳۶۵ روز باشد.")
    await c.client.send_message(c.event.chat_id, text, schedule=dur, parse_mode=None)
    await c.flash(f"⏰ ارسال شد برای {fmt_secs(dur.total_seconds())} دیگر.")


@command("scheduled", "scheduled", "فهرست پیام‌های زمان‌بندی‌شده‌ی این چت", "پیام‌ها")
async def cmd_scheduled(c: Ctx):
    peer = await c.event.get_input_chat()
    res = await c.client(functions.messages.GetScheduledHistoryRequest(peer=peer, hash=0))
    msgs = list(getattr(res, "messages", []))
    if not msgs:
        return await c.flash("هیچ پیام زمان‌بندی‌شده‌ای نیست.")
    lines = ["<b>زمان‌بندی‌شده‌ها</b>"]
    for m in msgs:
        snippet = (m.message or "[media]")[:60].replace("\n", " ")
        lines.append(f"• <code>{m.id}</code> {m.date.astimezone():%Y-%m-%d %H:%M} — {esc(snippet)}")
    await c.say("\n".join(lines))


@command("unschedule", "unschedule <id|all>", "حذف پیام زمان‌بندی‌شده", "پیام‌ها")
async def cmd_unschedule(c: Ctx):
    peer = await c.event.get_input_chat()
    if c.args.lower() == "all":
        res = await c.client(functions.messages.GetScheduledHistoryRequest(peer=peer, hash=0))
        ids = [m.id for m in getattr(res, "messages", [])]
    elif c.args.isdigit():
        ids = [int(c.args)]
    else:
        raise CommandError("unschedule <id>  یا  unschedule all")
    if ids:
        await c.client(functions.messages.DeleteScheduledMessagesRequest(peer=peer, id=ids))
    await c.flash(f"✅ {len(ids)} مورد حذف شد.")


@command("pin", "pin (ریپلای)", "پین کردن پیام (بدون اعلان)", "پیام‌ها")
async def cmd_pin(c: Ctx):
    rm = await c.need_reply()
    await c.client.pin_message(c.event.chat_id, rm, notify=False)
    await c.flash("📌 پین شد.")


@command("unpin", "unpin [all] (ریپلای)", "برداشتن پین", "پیام‌ها")
async def cmd_unpin(c: Ctx):
    if c.args.lower() == "all":
        await c.client.unpin_message(c.event.chat_id)
    else:
        rm = await c.need_reply()
        await c.client.unpin_message(c.event.chat_id, rm)
    await c.flash("✅ پین برداشته شد.")


@command("read", "read", "علامت‌گذاری چت به‌عنوان خوانده‌شده", "پیام‌ها")
async def cmd_read(c: Ctx):
    await c.client.send_read_acknowledge(c.event.chat_id, clear_mentions=True)
    await c.flash("✅ خوانده شد.")


@command("search", "search <متن>", "جست‌وجو در پیام‌های این چت (۱۰ نتیجه)", "پیام‌ها")
async def cmd_search(c: Ctx):
    if not c.args:
        raise CommandError("search <متن>")
    lines = [f"🔎 <b>{esc(c.args)}</b>"]
    count = 0
    async for m in c.client.iter_messages(c.event.chat_id, search=c.args, limit=10):
        snippet = (m.raw_text or f"[{type(m.media).__name__}]")[:80].replace("\n", " ")
        lines.append(f"• <code>{m.id}</code> {m.date.astimezone():%Y-%m-%d %H:%M} — {esc(snippet)}")
        count += 1
    await c.say("\n".join(lines) if count else "چیزی پیدا نشد.")


@command("dl", "dl (ریپلای)", "دانلود مدیای پیام در پوشه‌ی downloads", "پیام‌ها")
async def cmd_dl(c: Ctx):
    rm = await c.need_reply()
    if not rm.media:
        raise CommandError("این پیام مدیا ندارد.")
    await c.say("⬇️ در حال دانلود…")
    path = await rm.download_media(file=str(c.cfg.downloads) + os.sep)
    await c.say(f"✅ ذخیره شد: <code>{esc(Path(path).name)}</code>")


@command("export", "export [تعداد|all]", "خروجی JSON از تاریخچه‌ی چت → Saved Messages", "پیام‌ها")
async def cmd_export(c: Ctx):
    limit: Optional[int] = None if c.args.lower() == "all" else (int(c.args) if c.args.isdigit() else 1000)
    chat = await c.event.get_chat()
    rows: list[dict] = []
    async for m in c.client.iter_messages(chat, limit=limit):
        rows.append(msg_to_dict(m))
        if len(rows) % 2000 == 0:
            await c.say(f"⏳ {len(rows)} پیام…")
    rows.reverse()
    path = c.cfg.exports / f"chat_{c.event.chat_id}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps({"chat": display_name(chat), "id": c.event.chat_id, "messages": rows},
                               ensure_ascii=False, indent=1), "utf-8")
    await c.client.send_file("me", str(path), caption=f"📦 {esc(display_name(chat))} — {len(rows)} پیام")
    await c.flash(f"✅ {len(rows)} پیام به Saved Messages ارسال شد.")


# ───────────────────────────── چت‌ها ─────────────────────────────
@command("dialogs", "dialogs [تعداد]", "فهرست آخرین چت‌ها", "چت‌ها", private_only=True)
async def cmd_dialogs(c: Ctx):
    n = int(c.args) if c.args.isdigit() else 20
    lines = ["<b>چت‌ها</b>"]
    async for d in c.client.iter_dialogs(limit=min(n, 100)):
        unread = f" 🔔{d.unread_count}" if d.unread_count else ""
        lines.append(f"• {esc(d.name)} [{kind_of(d.entity)}] <code>{d.id}</code>{unread}")
    await c.say("\n".join(lines))


@command("info", "info [مقصد]", "اطلاعات کاربر/گروه/کانال (ریپلای، آرگومان یا چت فعلی)", "چت‌ها")
async def cmd_info(c: Ctx):
    if c.args:
        ent = await c.entity(c.args)
    else:
        rm = await c.event.get_reply_message()
        ent = (await rm.get_sender()) if rm else await c.event.get_chat()
    lines = [f"<b>{esc(display_name(ent))}</b> ({kind_of(ent)})", f"🆔 <code>{ent.id}</code>"]
    if getattr(ent, "username", None):
        lines.append(f"🔗 @{esc(ent.username)}")
    about: Optional[str] = None
    try:
        if isinstance(ent, types.User):
            full = await c.client(functions.users.GetFullUserRequest(ent))
            fu = getattr(full, "full_user", full)
            about = getattr(fu, "about", None)
            lines.append(f"⭐ Premium: {'بله' if getattr(ent, 'premium', False) else 'خیر'}"
                         f" · ✔️ Verified: {'بله' if getattr(ent, 'verified', False) else 'خیر'}")
            common = getattr(fu, "common_chats_count", None)
            if common is not None:
                lines.append(f"👥 گروه مشترک: {common}")
        elif isinstance(ent, types.Channel):
            full = await c.client(functions.channels.GetFullChannelRequest(ent))
            about = full.full_chat.about
            lines.append(f"👥 اعضا: {getattr(full.full_chat, 'participants_count', '—')}")
        elif isinstance(ent, types.Chat):
            full = await c.client(functions.messages.GetFullChatRequest(ent.id))
            about = full.full_chat.about
            lines.append(f"👥 اعضا: {ent.participants_count}")
    except RPCError as e:
        log.info("full info unavailable: %s", type(e).__name__)
    if about:
        lines.append(f"\n{esc(about)}")
    await c.say("\n".join(lines))


@command("join", "join <لینک|@username>", "عضویت در گروه/کانال", "چت‌ها")
async def cmd_join(c: Ctx):
    if not c.args:
        raise CommandError("join <لینک یا @username>")
    m = re.search(r"(?:t\.me/\+|t\.me/joinchat/|tg://join\?invite=|^\+)([\w-]+)", c.args.strip())
    if m:
        await c.client(functions.messages.ImportChatInviteRequest(m.group(1)))
    else:
        ent = await c.entity(c.args)
        await c.client(functions.channels.JoinChannelRequest(ent))
    await c.flash("✅ عضو شدی.")


@command("leave", "leave [مقصد] yes", "ترک گروه/کانال", "چت‌ها")
async def cmd_leave(c: Ctx):
    arg, ok = strip_confirm(c.args)
    ent = await c.chat(arg)
    if not isinstance(ent, (types.Chat, types.Channel)):
        raise CommandError("فقط گروه/کانال قابل ترک است.")
    if not ok:
        raise CommandError("برای تأیید بنویس: leave yes  (یا leave <مقصد> yes)")
    await c.client.delete_dialog(ent)
    # بعد از ترک، ویرایش پیام دستور ممکن نیست؛ نتیجه را در Saved Messages اعلام می‌کنیم
    await c.client.send_message("me", f"✅ ترک شد: <b>{esc(display_name(ent))}</b>", parse_mode="html")


@command("mkgroup", "mkgroup عنوان", "ساخت سوپرگروه + لینک دعوت", "چت‌ها")
async def cmd_mkgroup(c: Ctx):
    await _create_channel(c, megagroup=True)


@command("mkchannel", "mkchannel عنوان", "ساخت کانال + لینک دعوت", "چت‌ها")
async def cmd_mkchannel(c: Ctx):
    await _create_channel(c, megagroup=False)


async def _create_channel(c: Ctx, megagroup: bool) -> None:
    if not c.args:
        raise CommandError("عنوان را وارد کن.")
    res = await c.client(functions.channels.CreateChannelRequest(
        title=c.args[:128], about="", megagroup=megagroup, broadcast=not megagroup))
    chat = res.chats[0]
    inv = await c.client(functions.messages.ExportChatInviteRequest(peer=chat))
    await c.say(f"✅ ساخته شد: <b>{esc(chat.title)}</b>\n🔗 {esc(inv.link)}")


@command("title", "title عنوان", "تغییر عنوان گروه/کانال", "چت‌ها")
async def cmd_title(c: Ctx):
    chat = await c.group_chat()
    if not c.args:
        raise CommandError("عنوان جدید را بنویس.")
    if isinstance(chat, types.Channel):
        await c.client(functions.channels.EditTitleRequest(channel=chat, title=c.args[:128]))
    else:
        await c.client(functions.messages.EditChatTitleRequest(chat_id=chat.id, title=c.args[:128]))
    await c.flash("✅ عنوان تغییر کرد.")


@command("archive", "archive", "آرشیو این چت", "چت‌ها")
async def cmd_archive(c: Ctx):
    await c.client.edit_folder(c.event.chat_id, 1)
    await c.flash("🗂 آرشیو شد.")


@command("unarchive", "unarchive", "خارج کردن چت از آرشیو", "چت‌ها")
async def cmd_unarchive(c: Ctx):
    await c.client.edit_folder(c.event.chat_id, 0)
    await c.flash("✅ از آرشیو خارج شد.")


async def _set_mute(c: Ctx, until: int) -> None:
    peer = await c.event.get_input_chat()
    await c.client(functions.account.UpdateNotifySettingsRequest(
        peer=types.InputNotifyPeer(peer=peer),
        settings=types.InputPeerNotifySettings(mute_until=until)))


@command("mute", "mute [مدت]", "بی‌صدا کردن اعلان این چت (بدون مدت = همیشه)", "چت‌ها")
async def cmd_mute(c: Ctx):
    dur = parse_duration(c.args) if c.args else None
    if c.args and dur is None:
        raise CommandError("مدت نامعتبر؛ مثال: 8h یا 1d")
    until = int(time.time() + dur.total_seconds()) if dur else 2**31 - 1
    await _set_mute(c, until)
    await c.flash("🔕 بی‌صدا شد.")


@command("unmute", "unmute", "فعال کردن اعلان این چت", "چت‌ها")
async def cmd_unmute(c: Ctx):
    await _set_mute(c, 0)
    await c.flash("🔔 اعلان فعال شد.")


# ───────────────────────────── مدیریت گروه (نیازمند دسترسی ادمین) ─────────────────────────────
@command("members", "members [تعداد]", "فهرست اعضا", "گروه", private_only=True)
async def cmd_members(c: Ctx):
    chat = await c.group_chat()
    n = int(c.args) if c.args.isdigit() else 50
    lines = [f"<b>{esc(display_name(chat))}</b>"]
    async for u in c.client.iter_participants(chat, limit=min(n, 500)):
        un = f" @{esc(u.username)}" if u.username else ""
        lines.append(f"• {esc(display_name(u))}{un} — <code>{u.id}</code>")
    await c.say("\n".join(lines))


@command("admins", "admins", "فهرست ادمین‌ها", "گروه")
async def cmd_admins(c: Ctx):
    chat = await c.group_chat()
    lines = ["<b>ادمین‌ها</b>"]
    async for u in c.client.iter_participants(chat, filter=types.ChannelParticipantsAdmins):
        un = f" @{esc(u.username)}" if u.username else ""
        lines.append(f"• {esc(display_name(u))}{un}")
    await c.say("\n".join(lines))


@command("invite", "invite", "ساخت لینک دعوت", "گروه")
async def cmd_invite(c: Ctx):
    chat = await c.group_chat()
    inv = await c.client(functions.messages.ExportChatInviteRequest(peer=chat))
    await c.say(f"🔗 {esc(inv.link)}")


@command("kick", "kick [کاربر]", "اخراج (می‌تواند دوباره بپیوندد)", "گروه")
async def cmd_kick(c: Ctx):
    chat = await c.group_chat()
    user, _ = await c.user_and_rest()
    await c.client.kick_participant(chat, user)
    await c.flash("👢 اخراج شد.")


@command("ban", "ban [کاربر]", "بن دائمی", "گروه")
async def cmd_ban(c: Ctx):
    chat = await c.group_chat()
    user, _ = await c.user_and_rest()
    await c.client.edit_permissions(chat, user, view_messages=False)
    await c.flash("⛔ بن شد.")


@command("unban", "unban [کاربر]", "رفع بن", "گروه")
async def cmd_unban(c: Ctx):
    chat = await c.group_chat()
    user, _ = await c.user_and_rest()
    await c.client.edit_permissions(chat, user, view_messages=True)
    await c.flash("✅ بن برداشته شد.")


@command("silence", "silence [کاربر] [مدت]", "ممنوعیت ارسال پیام (بدون مدت = دائمی)", "گروه")
async def cmd_silence(c: Ctx):
    chat = await c.group_chat()
    user, rest = await c.user_and_rest()
    dur = parse_duration(rest) if rest else None
    if rest and dur is None:
        raise CommandError("مدت نامعتبر؛ مثال: 1h")
    await c.client.edit_permissions(chat, user, until_date=dur, send_messages=False)
    await c.flash("🤐 ساکت شد.")