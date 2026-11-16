# Telegram Account Manager (Telethon)

ابزار خط فرمان برای مدیریت **اکانت شخصی خودتان** از طریق MTProto (کتابخانه Telethon).
نیازمند Python 3.10 یا بالاتر.

## نصب

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # برای تست: pip install -r requirements-dev.txt
```

## پیکربندی

1. در https://my.telegram.org وارد شوید → «API development tools» → یک اپ بسازید و `api_id` و `api_hash` را بگیرید.
2. `cp .env.example .env` سپس مقادیر را پر کنید و `chmod 600 .env` بزنید.

## اولین ورود (فقط یک بار)

```bash
python -m tgmanager login
```

شماره تلفن (اگر در `.env` نیست)، کد تأیید و در صورت فعال بودن، رمز دو مرحله‌ای در ترمینال از شما پرسیده می‌شود
(ورودی کد و رمز نمایش داده نمی‌شود). بعد از آن نشست ذخیره می‌شود و دیگر نیازی به ورود مجدد نیست.

## نمونه دستورها

```bash
python -m tgmanager whoami
python -m tgmanager dialogs --unread
python -m tgmanager history @username --limit 20
python -m tgmanager send @username "سلام"
python -m tgmanager send me "یادداشت" --schedule 2026-12-01T09:00
python -m tgmanager send-file @username ./photo.jpg --caption "عکس"
python -m tgmanager download @channel 1234
python -m tgmanager watch                     # نمایش زندهٔ پیام‌های جدید
python -m tgmanager group-create "تیم من" --user @a --user @b
python -m tgmanager members @mygroup
python -m tgmanager -y delete @username 101 102
python -m tgmanager contacts
python -m tgmanager sessions                  # دستگاه‌های وارد شده به اکانت
python -m tgmanager --help                    # فهرست کامل دستورها
```

دستورهای مخرب (حذف، ترک گروه، اخراج، خروج از نشست …) قبل از اجرا تأیید می‌گیرند؛ با `-y` این تأیید رد می‌شود.

## امنیت

* `api_hash`، شماره تلفن و فایل نشست هیچ‌جا در کد نیستند؛ فقط از `.env` / متغیر محیطی خوانده می‌شوند.
* فایل نشست (`~/.tgmanager/account.session`) **معادل رمز اکانت شماست**. هرکس آن را داشته باشد بدون کد و رمز وارد اکانت می‌شود.
  * هرگز آن را commit، ایمیل یا در چت ارسال نکنید. پوشه ۰۷۰۰ و فایل ۰۶۰۰ ساخته می‌شود (در ویندوز دسترسی‌ها را دستی محدود کنید).
  * دیسک را رمزگذاری کنید (LUKS / FileVault / BitLocker) و از بکاپ‌های همگانی/ابری حذفش کنید.
  * اگر مشکوک شدید: `python -m tgmanager sessions` و `terminate-session`، یا از اپ رسمی تلگرام ← Settings ← Devices.
* در لاگ‌ها شماره تلفن و رشته‌های ۳۲ کاراکتری hex ماسک می‌شوند و **متن پیام‌ها هرگز لاگ نمی‌شود**.

## محدودیت‌ها و قوانین تلگرام

* اسپم، ارسال انبوه، اضافه‌کردن گروهی کاربران و جمع‌آوری اطلاعات دیگران باعث محدودیت یا بن شدن اکانت می‌شود.
  برای همین ارسال‌ها فاصلهٔ زمانی دارند (`TG_SEND_MIN_INTERVAL`) و افزودن عضو حداکثر ۲۰ نفر در هر بار است.
* چت‌های رمزنگاری‌شدهٔ Secret از طریق این API پشتیبانی نمی‌شوند.
* پایان دادن به نشست‌های دیگر فقط برای نشست‌های قدیمی‌تر از ۲۴ ساعت مجاز است.

## تست

```bash
pip install -r requirements-dev.txt
pytest
```
