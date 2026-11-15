const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };
const html = (value = "") => String(value).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const asText = value => String(value ?? "").trim();

async function telegram(env, method, payload = {}) {
  const response = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.description || `Telegram API error: ${method}`);
  }
  return data.result;
}

async function reply(env, chatId, text, extra = {}) {
  return telegram(env, "sendMessage", {
    chat_id: chatId, text, parse_mode: "HTML", disable_web_page_preview: true, ...extra
  });
}

async function rememberUpdate(update, env) {
  const seen = await env.DB.prepare(
    "INSERT OR IGNORE INTO processed_updates(update_id) VALUES (?)"
  ).bind(update.update_id).run();
  if (!seen.meta?.changes) return false;

  const msg = update.message || update.edited_message || update.channel_post || update.edited_channel_post;
  if (!msg?.chat) return true;

  const chat = msg.chat;
  await env.DB.prepare(`
    INSERT INTO chats(chat_id,type,title,username,last_seen)
    VALUES(?,?,?,?,CURRENT_TIMESTAMP)
    ON CONFLICT(chat_id) DO UPDATE SET
      type=excluded.type,title=excluded.title,username=excluded.username,last_seen=CURRENT_TIMESTAMP
  `).bind(String(chat.id), chat.type || "", chat.title || chat.first_name || "", chat.username || "").run();

  const text = msg.text || msg.caption || "";
  if (text) {
    await env.DB.prepare(`
      INSERT OR IGNORE INTO messages(chat_id,message_id,user_id,username,text)
      VALUES(?,?,?,?,?)
    `).bind(String(chat.id), msg.message_id, String(msg.from?.id || ""), msg.from?.username || "", text.slice(0, 3500)).run();
  }
  return true;
}

function parseCommand(text, botUsername = "") {
  const match = asText(text).match(/^\/([a-z0-9_]+)(?:@([a-z0-9_]+))?(?:\s+([\s\S]*))?$/i);
  if (!match) return null;
  if (match[2] && botUsername && match[2].toLowerCase() !== botUsername.toLowerCase()) return null;
  return { name: match[1].toLowerCase(), args: (match[3] || "").trim() };
}

function targetUser(message, args) {
  if (message.reply_to_message?.from?.id) return message.reply_to_message.from.id;
  const first = args.split(/\s+/, 1)[0];
  if (/^\d+$/.test(first)) return Number(first);
  return null;
}

function durationSeconds(value) {
  const m = /^([1-9]\d*)(s|m|h|d)$/.exec(value || "");
  if (!m) return null;
  return Number(m[1]) * ({ s: 1, m: 60, h: 3600, d: 86400 }[m[2]]);
}

async function isChatAdmin(env, chatId, userId) {
  const member = await telegram(env, "getChatMember", { chat_id: chatId, user_id: userId });
  return ["creator", "administrator"].includes(member.status);
}

async function requireModerator(message, env) {
  if (!message.from) throw new Error("فرستندهٔ پیام مشخص نیست.");
  const isOwner = env.OWNER_ID && String(message.from.id) === String(env.OWNER_ID);
  if (message.chat.type === "private") {
    if (!isOwner) throw new Error("این دستور فقط برای مالک ربات فعال است.");
    return;
  }
  if (!isOwner && !(await isChatAdmin(env, message.chat.id, message.from.id))) {
    throw new Error("برای اجرای این دستور باید مدیر گروه باشی.");
  }
}

async function runCommand(message, command, env, botUsername) {
  const chatId = message.chat.id;
  const args = command.args;
  const words = args.split(/\s+/).filter(Boolean);
  const name = command.name;
  const say = (text, extra = {}) => reply(env, chatId, text, extra);

  if (name === "start" || name === "help") {
    return say(
      "<b>TG Manager — نسخهٔ Cloudflare</b>\n" +
      "/ping — تست اتصال\n/id — شناسهٔ چت و کاربر\n/me — اطلاعات ربات\n/info — اطلاعات چت\n" +
      "/admins — فهرست مدیران\n/invite — لینک دعوت\n/title متن — تغییر عنوان\n" +
      "/ban و /unban — بن و رفع بن (با ریپلای یا شناسه)\n/kick — اخراج عضو\n" +
      "/mute 10m و /unmute — محدودیت ارسال\n/promote و /demote — مدیریت مدیران\n" +
      "/pin و /unpin — سنجاق پیام (با ریپلای)\n/del — حذف پیام ریپلای‌شده\n" +
      "/schedule 10m متن — زمان‌بندی\n/scheduled و /unschedule شناسه\n" +
      "/search عبارت — جست‌وجو در پیام‌های ذخیره‌شده\n/export — خروجی پیام‌های دریافت‌شده\n/stats — آمار\n\n" +
      "برای مدیریت گروه، ربات را ادمین کن و دسترسی‌های لازم را بده."
    );
  }
  if (name === "ping") return say("🏓 Pong — ربات روی Cloudflare فعال است.");
  if (name === "id") {
    return say(`💬 Chat ID: <code>${chatId}</code>\n👤 User ID: <code>${message.from?.id || "—"}</code>`);
  }
  if (name === "me") {
    const me = await telegram(env, "getMe");
    return say(`🤖 <b>${html(me.first_name)}</b>\n🆔 <code>${me.id}</code>\n🔗 ${me.username ? "@" + html(me.username) : "—"}`);
  }
  if (name === "info") {
    const info = await telegram(env, "getChat", { chat_id: chatId });
    let count = "—";
    try { count = await telegram(env, "getChatMemberCount", { chat_id: chatId }); } catch {}
    return say(`<b>${html(info.title || info.first_name || "گفتگو")}</b>\nنوع: ${html(info.type)}\nشناسه: <code>${info.id}</code>\nاعضا: ${count}`);
  }
  if (name === "stats") {
    const [chats, messages, scheduled] = await Promise.all([
      env.DB.prepare("SELECT COUNT(*) n FROM chats").first(),
      env.DB.prepare("SELECT COUNT(*) n FROM messages").first(),
      env.DB.prepare("SELECT COUNT(*) n FROM scheduled_messages WHERE sent_at IS NULL").first()
    ]);
    return say(`📊 چت‌های شناخته‌شده: ${chats.n}\nپیام‌های ذخیره‌شده: ${messages.n}\nپیام‌های زمان‌بندی‌شده: ${scheduled.n}`);
  }
  if (name === "admins") {
    const admins = await telegram(env, "getChatAdministrators", { chat_id: chatId });
    return say("<b>مدیران گروه</b>\n" + admins.map(a => "• " + html([a.user.first_name, a.user.last_name].filter(Boolean).join(" ")) + (a.user.username ? " @" + html(a.user.username) : "")).join("\n"));
  }
  if (name === "invite") {
    await requireModerator(message, env);
    const link = await telegram(env, "exportChatInviteLink", { chat_id: chatId });
    return say("🔗 " + html(link));
  }
  if (name === "title") {
    await requireModerator(message, env);
    if (!args) throw new Error("عنوان جدید را وارد کن.");
    await telegram(env, "setChatTitle", { chat_id: chatId, title: args.slice(0, 128) });
    return say("✅ عنوان گروه تغییر کرد.");
  }
  if (["ban", "unban", "kick", "mute", "unmute", "promote", "demote"].includes(name)) {
    await requireModerator(message, env);
    const userId = targetUser(message, args);
    if (!userId) throw new Error("روی پیام کاربر ریپلای کن یا شناسهٔ عددی او را بنویس.");
    if (name === "ban") {
      await telegram(env, "banChatMember", { chat_id: chatId, user_id: userId });
      return say("⛔ کاربر مسدود شد.");
    }
    if (name === "unban") {
      await telegram(env, "unbanChatMember", { chat_id: chatId, user_id: userId, only_if_banned: true });
      return say("✅ مسدودیت برداشته شد.");
    }
    if (name === "kick") {
      await telegram(env, "banChatMember", { chat_id: chatId, user_id: userId });
      await telegram(env, "unbanChatMember", { chat_id: chatId, user_id: userId, only_if_banned: true });
      return say("👢 کاربر از گروه اخراج شد.");
    }
    if (name === "mute") {
      const durationToken = message.reply_to_message ? words[0] : words[1];
      const duration = durationSeconds(durationToken) || 3600;
      const until_date = Math.floor(Date.now() / 1000) + duration;
      await telegram(env, "restrictChatMember", {
        chat_id: chatId, user_id: userId, until_date,
        permissions: { can_send_messages: false, can_send_audios: false, can_send_documents: false, can_send_photos: false, can_send_videos: false, can_send_video_notes: false, can_send_voice_notes: false, can_send_polls: false, can_send_other_messages: false, can_add_web_page_previews: false }
      });
      return say("🤐 دسترسی ارسال پیام محدود شد.");
    }
    if (name === "unmute") {
      await telegram(env, "restrictChatMember", {
        chat_id: chatId, user_id: userId,
        permissions: { can_send_messages: true, can_send_audios: true, can_send_documents: true, can_send_photos: true, can_send_videos: true, can_send_video_notes: true, can_send_voice_notes: true, can_send_polls: true, can_send_other_messages: true, can_add_web_page_previews: true }
      });
      return say("✅ محدودیت ارسال برداشته شد.");
    }
    if (name === "promote") {
      await telegram(env, "promoteChatMember", { chat_id: chatId, user_id: userId, can_delete_messages: true, can_restrict_members: true, can_invite_users: true, can_pin_messages: true, can_manage_chat: true });
      return say("⬆️ کاربر ارتقا یافت. سطح دسترسی را از تنظیمات گروه بررسی کن.");
    }
    await telegram(env, "promoteChatMember", { chat_id: chatId, user_id: userId, can_change_info: false, can_post_messages: false, can_edit_messages: false, can_delete_messages: false, can_invite_users: false, can_restrict_members: false, can_pin_messages: false, can_promote_members: false, can_manage_chat: false });
    return say("⬇️ دسترسی‌های مدیریتی برداشته شد.");
  }
  if (name === "pin" || name === "unpin") {
    await requireModerator(message, env);
    const target = message.reply_to_message?.message_id;
    if (name === "pin") {
      if (!target) throw new Error("برای پین کردن روی پیام موردنظر ریپلای کن.");
      await telegram(env, "pinChatMessage", { chat_id: chatId, message_id: target, disable_notification: true });
      return say("📌 پیام سنجاق شد.");
    }
    if (target) await telegram(env, "unpinChatMessage", { chat_id: chatId, message_id: target });
    else await telegram(env, "unpinAllChatMessages", { chat_id: chatId });
    return say("✅ پین برداشته شد.");
  }
  if (name === "del") {
    await requireModerator(message, env);
    const target = message.reply_to_message?.message_id;
    if (!target) throw new Error("برای حذف، روی پیام موردنظر ریپلای کن.");
    await telegram(env, "deleteMessage", { chat_id: chatId, message_id: target });
    return say("🗑 پیام حذف شد.");
  }
  if (name === "schedule") {
    const match = /^(\d+[smhd])\s+([\s\S]+)$/.exec(args);
    if (!match) throw new Error("نمونه: /schedule 30m متن پیام");
    const seconds = durationSeconds(match[1]);
    if (!seconds || seconds < 30 || seconds > 31536000) throw new Error("مدت باید بین ۳۰ ثانیه تا یک سال باشد.");
    const due = Math.floor(Date.now() / 1000) + seconds;
    const result = await env.DB.prepare("INSERT INTO scheduled_messages(chat_id,text,due_at,created_by) VALUES(?,?,?,?)")
      .bind(String(chatId), match[2].slice(0, 3500), due, String(message.from?.id || "")).run();
    return say(`⏰ پیام با شناسهٔ ${result.meta.last_row_id} زمان‌بندی شد.`);
  }
  if (name === "scheduled") {
    const rows = await env.DB.prepare("SELECT id,text,due_at FROM scheduled_messages WHERE chat_id=? AND sent_at IS NULL ORDER BY due_at LIMIT 10").bind(String(chatId)).all();
    if (!rows.results.length) return say("پیام زمان‌بندی‌شده‌ای وجود ندارد.");
    return say("<b>پیام‌های زمان‌بندی‌شده</b>\n" + rows.results.map(x => `#${x.id} — ${new Date(x.due_at * 1000).toLocaleString("fa-IR")} — ${html(x.text.slice(0, 80))}`).join("\n"));
  }
  if (name === "unschedule") {
    if (!/^\d+$/.test(args)) throw new Error("شناسهٔ پیام زمان‌بندی‌شده را وارد کن.");
    const result = await env.DB.prepare("DELETE FROM scheduled_messages WHERE id=? AND chat_id=? AND sent_at IS NULL").bind(Number(args), String(chatId)).run();
    return say(result.meta.changes ? "✅ زمان‌بندی حذف شد." : "این شناسه پیدا نشد.");
  }
  if (name === "search") {
    if (!args) throw new Error("عبارت جست‌وجو را بنویس.");
    const rows = await env.DB.prepare("SELECT message_id,user_id,username,text,created_at FROM messages WHERE chat_id=? AND text LIKE ? ORDER BY id DESC LIMIT 8")
      .bind(String(chatId), "%" + args.slice(0, 80) + "%").all();
    if (!rows.results.length) return say("نتیجه‌ای در پیام‌های ذخیره‌شده پیدا نشد.");
    return say("<b>نتایج جست‌وجو</b>\n" + rows.results.map(x => `#${x.message_id} — ${html(x.username || x.user_id)}\n${html(x.text.slice(0, 220))}`).join("\n\n"));
  }
  if (name === "export") {
    const rows = await env.DB.prepare("SELECT message_id,user_id,username,text,created_at FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 40").bind(String(chatId)).all();
    if (!rows.results.length) return say("هنوز پیامی برای خروجی ذخیره نشده است.");
    const body = rows.results.reverse().map(x => `[${x.created_at}] ${x.username || x.user_id}: ${x.text}`).join("\n");
    return say("<pre>" + html(body.slice(0, 3800)) + "</pre>");
  }
  if (name === "afk") {
    const value = JSON.stringify({ enabled: true, reason: args.slice(0, 300) });
    await env.DB.prepare("INSERT INTO settings(key,value) VALUES('afk',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(value).run();
    return say("🌙 پاسخ خودکار ربات در گفت‌وگوهای خصوصی فعال شد.");
  }
  if (name === "unafk") {
    await env.DB.prepare("DELETE FROM settings WHERE key='afk'").run();
    return say("☀️ پاسخ خودکار غیرفعال شد.");
  }
  if (name === "send") {
    await requireModerator(message, env);
    const m = /^(\-?\d+|@[a-zA-Z0-9_]+)\s+([\s\S]+)$/.exec(args);
    if (!m) throw new Error("نمونه: /send chat_id متن پیام");
    await reply(env, m[1], m[2]);
    return say("✅ پیام ارسال شد.");
  }
  throw new Error("این دستور در نسخهٔ Bot API پشتیبانی نمی‌شود. /help را ببین.");
}

async function processUpdate(update, env) {
  try {
    if (!(await rememberUpdate(update, env))) return;
    const message = update.message || update.edited_message;
    if (!message?.chat) return;
    const text = message.text || "";
    const afk = await env.DB.prepare("SELECT value FROM settings WHERE key='afk'").first();
    const command = parseCommand(text, env.BOT_USERNAME || "");
    if (!command && message.chat.type === "private" && message.from && afk) {
      const state = JSON.parse(afk.value);
      const key = "afk_seen_" + message.from.id;
      const previous = await env.DB.prepare("SELECT value FROM settings WHERE key=?").bind(key).first();
      const now = Math.floor(Date.now() / 1000);
      if (!previous || now - Number(previous.value) > 600) {
        await env.DB.prepare("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(key, String(now)).run();
        await reply(env, message.chat.id, "🌙 فعلاً در دسترس نیستم." + (state.reason ? "\nدلیل: " + html(state.reason) : ""));
      }
    }
    if (!command) return;
    try {
      await runCommand(message, command, env);
    } catch (error) {
      console.error("command failed", command.name, error?.message || error);
      await reply(env, message.chat.id, "⚠️ " + html(error?.message || "خطای نامشخص"));
    }
  } catch (error) {
    await env.DB.prepare("DELETE FROM processed_updates WHERE update_id=?").bind(update.update_id).run();
    throw error;
  }
}

async function deliverScheduled(env) {
  await env.DB.prepare("DELETE FROM processed_updates WHERE processed_at < datetime('now', '-30 days')").run();
  await env.DB.prepare("DELETE FROM messages WHERE created_at < datetime('now', '-30 days')").run();
  await env.DB.prepare("DELETE FROM scheduled_messages WHERE sent_at IS NOT NULL AND sent_at != 'FAILED' AND sent_at < datetime('now', '-30 days')").run();
  const now = Math.floor(Date.now() / 1000);
  const due = await env.DB.prepare("SELECT id,chat_id,text FROM scheduled_messages WHERE sent_at IS NULL AND due_at<=? ORDER BY due_at LIMIT 25").bind(now).all();
  for (const item of due.results) {
    try {
      await reply(env, item.chat_id, html(item.text));
      await env.DB.prepare("UPDATE scheduled_messages SET sent_at=CURRENT_TIMESTAMP WHERE id=?").bind(item.id).run();
    } catch (error) {
      console.error("scheduled message failed", item.id, error?.message || error);
      await env.DB.prepare("UPDATE scheduled_messages SET sent_at='FAILED' WHERE id=?").bind(item.id).run();
    }
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") {
      return new Response("BOT-control-ac Worker is running.", { status: 200 });
    }
    if (request.method !== "POST" || url.pathname !== "/telegram") {
      return new Response("Not Found", { status: 404 });
    }
    if (!env.BOT_TOKEN || !env.TELEGRAM_WEBHOOK_SECRET || !env.DB) {
      return new Response("Worker configuration incomplete.", { status: 503 });
    }
    const supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
    if (supplied !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }
    let update;
    try { update = await request.json(); }
    catch { return new Response("Bad Request", { status: 400 }); }
    try {
      await processUpdate(update, env);
      return new Response("OK", { status: 200 });
    } catch (error) {
      console.error("update failed", error?.message || error);
      return new Response("Temporary processing failure", { status: 500 });
    }
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(deliverScheduled(env));
  }
};
