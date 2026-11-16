# TG Manager — Telegram Account Manager

ابزار مدیریت اکانت شخصی تلگرام با Python و Telethon (MTProto). اجرای اصلی از فایل `tg_manager.py` انجام می‌شود؛ این مخزن یک پکیج CLI به نام `tgmanager` نیست.

## نیازمندی‌ها

- Python 3.10+
- API ID و API Hash اختصاصی از [my.telegram.org](https://my.telegram.org)
- برای اتصال اختیاری به Cloudflare: اینترنت خروجی HTTPS

## نصب و اجرا

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

مقادیر `TG_API_ID` و `TG_API_HASH` را در فایل محلی `.env` قرار بده و سپس اجرا کن:

```powershell
py tg_manager.py
```

در اولین اجرا شماره، کد ورود و در صورت فعال بودن رمز دومرحله‌ای در ترمینال درخواست می‌شود. کد ورود و رمز را فقط در ترمینال محلی وارد کن؛ آن‌ها را برای هیچ‌کس ارسال نکن.

بعد از ورود، دستورهای مدیریتی با پیشوند پیش‌فرض `.` از Saved Messages قابل اجرا هستند؛ برای فهرست دستورها `.help` را بفرست.

## اتصال اختیاری به Cloudflare

Worker پروژه:
`https://telegram-account.99lq9ohj-kfshcd.workers.dev`

- `GET /health`: سلامت Worker و D1 و وضعیت آخرین heartbeat عامل پایتون
- `GET /v1`: معرفی مسیرهای API
- ارتباط Python با Worker با کلید مستقل `AGENT_API_KEY` احراز هویت می‌شود.
- کلید مدیریت API با نام `ADMIN_API_KEY` جداست و نباید روی سیستم اجرای Telethon قرار بگیرد.

برای فعال‌سازی:

1. در Cloudflare Dashboard → Workers & Pages → `telegram-account` → Settings → Variables and Secrets، دو Secret با نام‌های `AGENT_API_KEY` و `ADMIN_API_KEY` بساز.
2. یک مقدار تصادفی قوی برای هرکدام بساز. مقدار `AGENT_API_KEY` را فقط در Secret کلودفلر و متغیر محلی `FXI_AGENT_API_KEY` قرار بده. مقدار `ADMIN_API_KEY` فقط در Cloudflare بماند.
3. در فایل محلی `.env` این تنظیمات را اضافه کن:

```dotenv
FXI_API_URL=https://telegram-account.99lq9ohj-kfshcd.workers.dev
FXI_AGENT_API_KEY=مقدار-Secret-عامل
# اختیاری؛ در صورت حذف، شناسه از شناسه اکانت تلگرام ساخته می‌شود
# FXI_AGENT_ID=tg-شناسه-تلگرام
```

4. برنامه را دوباره اجرا کن. عامل Python ثبت می‌شود و هر ۳۰ ثانیه heartbeat می‌فرستد.

در این نسخه، صف فقط دو کار تشخیصی محدود را قبول می‌کند: `agent.ping` و `agent.status`. اجرای فرمان‌های تغییردهنده اکانت از راه API عمداً فعال نیست؛ قبل از افزودن آن‌ها باید مجوزها، تأیید عملیات حساس و ثبت رویدادها تکمیل شوند.

## امنیت نشست

- فایل `data/account.session` کلید کامل ورود به اکانت است. آن را در GitHub، چت، Cloudflare یا سرویس‌های اشتراک فایل قرار نده.
- فایل `.env` و کلیدهای API را commit نکن؛ فقط `.env.example` بدون مقدار واقعی در مخزن می‌ماند.
- نشست Telethon روی همان سیستم Python نگهداری می‌شود؛ D1 فقط وضعیت عامل، صف کارها و رویدادهای ممیزی را ذخیره می‌کند.
- از ارسال انبوه، اسپم و عملیات خلاف قوانین تلگرام خودداری کن.
