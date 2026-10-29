# X → Telegram Bot

Tumhare X account ke **following feed** ke saare naye tweets Telegram pe bhejta hai (~20 sec me), plus `/add` se extra accounts.

## Setup (VPS)
```bash
git clone <your-repo> /opt/x-telegram-bot && cd /opt/x-telegram-bot
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env
./venv/bin/python bot.py        # pehle ek baar chala ke dekho
```
Background me chalane ke liye:
```bash
cp xbot.service /etc/systemd/system/ && systemctl daemon-reload
systemctl enable --now xbot && journalctl -u xbot -f
```

## Cookies kaise nikale
x.com login → F12 → Application → Cookies → `https://x.com` → `auth_token` aur `ct0` copy karke `.env` me daalo.

## Commands
/add user, /remove user, /list, /pause, /resume, /status

## Notes
- Pehli baar purane tweets nahi bhejta (sirf naye).
- Spam se bachne ke liye replies default OFF (`SEND_REPLIES=1` se ON).
- Faster chahiye to `POLL_SECONDS=10` (min 10); isse kam karoge to rate limit/ban risk.
- Better hai extra/secondary X account ke cookies use karo (unofficial method hai).
- Cookies expire hon to bot Telegram pe warning dega; nayi cookies daal ke restart karo.
