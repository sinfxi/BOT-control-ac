# BOT-control-ac — Cloudflare Bot API

نسخهٔ بازطراحی‌شدهٔ TG Manager برای اجرای بدون کامپیوتر روشن، روی Cloudflare Workers + D1.

> این شاخه از Telegram Bot API استفاده می‌کند؛ نسخهٔ اصلی Telethon در شاخهٔ `main` دست‌نخورده باقی مانده است.

## معماری

- Cloudflare Worker: دریافت Webhook و اجرای فرمان‌ها
- Cloudflare D1: ذخیرهٔ چت‌های شناخته‌شده، پیام‌های دریافتی، تنظیمات و زمان‌بندی
- Telegram Bot API: ارتباط با تلگرام
- Cron Trigger هر دقیقه: ارسال پیام‌های زمان‌بندی‌شده

## پیش‌نیازهای راه‌اندازی

1. در BotFather یک Bot بساز و توکن آن را دریافت کن.
2. Worker را در Cloudflare با نام `bot-control-ac` منتشر کن.
3. در بخش Worker > Settings > Variables and Secrets این Secretها را اضافه کن:
   - `BOT_TOKEN`: توکن BotFather
   - `TELEGRAM_WEBHOOK_SECRET`: یک رشتهٔ تصادفی امن، ۱ تا ۲۵۶ نویسه و فقط شامل حروف انگلیسی، عدد، `_` و `-`
4. متغیر متنی `OWNER_ID` را با شناسهٔ عددی مالک تنظیم کن.
5. دیتابیس D1 با نام `bot-control-ac-db` و binding با نام `DB` به Worker متصل است.
6. پس از Deploy، Webhook را ثبت کن:

```bash
curl -X POST "https://api.telegram.org/bot< BOT_TOKEN >/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://bot-control-ac.<YOUR_SUBDOMAIN>.workers.dev/telegram","secret_token":"<TELEGRAM_WEBHOOK_SECRET>","allowed_updates":["message","edited_message"]}'
```

توکن و secret را داخل GitHub، کد، Issue یا پیام عمومی قرار نده.

## فرمان‌های پیاده‌سازی‌شده

`/start`, `/help`, `/ping`, `/id`, `/me`, `/info`, `/stats`, `/admins`, `/invite`, `/title`, `/ban`, `/unban`, `/kick`, `/mute`, `/unmute`, `/promote`, `/demote`, `/pin`, `/unpin`, `/del`, `/schedule`, `/scheduled`, `/unschedule`, `/search`, `/export`, `/afk`, `/unafk`, `/send`.

برای فرمان‌های مدیریتی، ربات باید در گروه ادمین باشد و فقط مدیر گروه یا مالک ربات می‌تواند آن‌ها را اجرا کند.

## محدودیت‌های Bot API نسبت به Userbot

Bot API هویت یک ربات مستقل دارد و جای حساب شخصی را نمی‌گیرد. در نتیجه مدیریت نشست‌های اکانت، مخاطبین و حریم خصوصی حساب، تغییر پروفایل شخصی، خواندن تاریخچهٔ قدیمی، ساخت گروه/کانال از طرف حساب و مشاهدهٔ فهرست کامل اعضا در دسترس نیست. جست‌وجو و خروجی فقط روی پیام‌هایی کار می‌کند که بعد از اضافه‌شدن ربات به آن چت به Worker رسیده‌اند.

برای دریافت پیام‌های عادی گروه، Privacy Mode ربات باید از BotFather غیرفعال شود یا ربات دسترسی ادمین مناسب داشته باشد. بدون این تنظیم، تلگرام فقط بخشی از پیام‌های گروه را به ربات می‌فرستد.

## داده و نگهداری

پیام‌های متنی و کپشن‌های دریافت‌شده برای جست‌وجو و خروجی در D1 ذخیره می‌شوند و پاک‌سازی خودکار داده‌های پیام و شناسه‌های پردازش‌شده پس از ۳۰ روز اجرا می‌شود. پیش از استفاده در گروه‌های واقعی، اعضا را از این موضوع مطلع کن. برای داده‌های حساس از ربات استفاده نکن.

## فایل‌ها

- `worker.js`: منطق Webhook و فرمان‌ها
- `schema.sql`: ساختار D1
- `wrangler.toml`: تنظیمات Worker و اتصال D1
