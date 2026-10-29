import asyncio, html, json, logging, os, time
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import RetryAfter
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from twikit import Client
from twikit.errors import TooManyRequests

load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
AUTH_TOKEN = os.environ["X_AUTH_TOKEN"]
CT0 = os.environ["X_CT0"]
POLL = max(10, int(os.getenv("POLL_SECONDS", "20")))
FOLLOWING_FEED = os.getenv("FOLLOWING_FEED", "1") == "1"
SEND_REPLIES = os.getenv("SEND_REPLIES", "0") == "1"
SEND_RETWEETS = os.getenv("SEND_RETWEETS", "1") == "1"
DATA = Path(os.getenv("DATA_FILE", "data.json"))

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger("xbot")


class State:
    def __init__(self):
        self.users, self.seen, self.seeded, self.paused = [], {}, [], False
        if DATA.exists():
            d = json.loads(DATA.read_text())
            self.users = d.get("users", [])
            self.seen = {i: 1 for i in d.get("seen", [])}
            self.seeded = d.get("seeded", [])
            self.paused = d.get("paused", False)

    def save(self):
        while len(self.seen) > 5000:
            self.seen.pop(next(iter(self.seen)))
        DATA.write_text(json.dumps({"users": self.users, "seen": list(self.seen),
                                    "seeded": self.seeded, "paused": self.paused}))


state = State()
last_err = {"t": 0}


async def tg_send(bot, tweet):
    src = getattr(tweet, "retweeted_tweet", None)
    base = src or tweet
    u = base.user
    text = html.escape((getattr(base, "full_text", None) or base.text or "").strip())
    url = f"https://x.com/{u.screen_name}/status/{base.id}"
    head = f"🐦 <b>{html.escape(u.name)}</b> (@{u.screen_name})"
    if src:
        head = f"🔁 @{tweet.user.screen_name} retweeted\n" + head
    elif getattr(tweet, "in_reply_to", None):
        head = "↩️ Reply\n" + head
    media = getattr(base, "media", None) or []
    photos = [m for m in media if getattr(m, "type", "") == "photo"]
    vids = [m for m in media if getattr(m, "type", "") in ("video", "animated_gif")]
    tail = ("\n🎥 video" if vids else "") + f'\n\n<a href="{url}">Open on X</a>'
    for attempt in range(3):
        try:
            if photos and getattr(photos[0], "media_url", None):
                cap = f"{head}\n\n{text[:850]}{tail}"
                try:
                    await bot.send_photo(OWNER_ID, photos[0].media_url, caption=cap, parse_mode=ParseMode.HTML)
                    return
                except RetryAfter:
                    raise
                except Exception as e:
                    log.warning("photo failed, text fallback: %s", e)
            await bot.send_message(OWNER_ID, f"{head}\n\n{text[:3800]}{tail}", parse_mode=ParseMode.HTML,
                                   link_preview_options=LinkPreviewOptions(is_disabled=True))
            return
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)


async def process(bot, tweets, key):
    first = key not in state.seeded
    new = sorted([t for t in tweets if t.id not in state.seen], key=lambda t: int(t.id))
    for t in new:
        state.seen[t.id] = 1
        if first:
            continue
        if not SEND_REPLIES and getattr(t, "in_reply_to", None):
            continue
        if not SEND_RETWEETS and getattr(t, "retweeted_tweet", None):
            continue
        try:
            await tg_send(bot, t)
        except Exception as e:
            log.error("send failed: %s", e)
    if first:
        state.seeded.append(key)
    state.save()


async def warn(bot, msg):
    if time.time() - last_err["t"] > 600:
        last_err["t"] = time.time()
        try:
            await bot.send_message(OWNER_ID, msg)
        except Exception:
            pass


async def poller(app):
    bot = app.bot
    client = Client("en-US")
    client.set_cookies({"auth_token": AUTH_TOKEN, "ct0": CT0})
    ids = {}
    while True:
        if not state.paused:
            try:
                if FOLLOWING_FEED:
                    await process(bot, await client.get_latest_timeline(count=40), "following")
                for name in list(state.users):
                    try:
                        if name not in ids:
                            ids[name] = (await client.get_user_by_screen_name(name)).id
                        tw = await client.get_user_tweets(ids[name], "Tweets", count=15)
                        await process(bot, tw, f"u:{name}")
                    except TooManyRequests:
                        raise
                    except Exception as e:
                        log.error("user %s: %s", name, e)
                        await warn(bot, f"⚠️ @{name} fetch error: {str(e)[:200]}")
                    await asyncio.sleep(1.5)
            except TooManyRequests as e:
                reset = getattr(e, "rate_limit_reset", None)
                wait = 120
                if isinstance(reset, (int, float)):
                    wait = min(900, max(30, reset - time.time()))
                log.warning("rate limited, sleeping %ss", wait)
                await asyncio.sleep(wait)
            except Exception as e:
                log.error("poll error: %s", e)
                await warn(bot, f"⚠️ Poll error (cookies expire to nahi hui?): {str(e)[:250]}")
                await asyncio.sleep(30)
        await asyncio.sleep(POLL)


async def post_init(app):
    app.bot_data["task"] = asyncio.create_task(poller(app))
    await app.bot.send_message(OWNER_ID, "✅ Bot start. /help dekho.")


async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        "/add username – account track karo\n/remove username\n/list\n/pause\n/resume\n/status\n\n"
        f"Following feed: {'ON' if FOLLOWING_FEED else 'OFF'} (X pe jo follow hai sab auto aayega)")


async def add(u, c):
    if not c.args:
        return await u.message.reply_text("Use: /add elonmusk")
    n = c.args[0].lstrip("@").lower()
    if n not in state.users:
        state.users.append(n)
        state.save()
    await u.message.reply_text(f"✅ Added @{n}")


async def remove(u, c):
    if not c.args:
        return await u.message.reply_text("Use: /remove elonmusk")
    n = c.args[0].lstrip("@").lower()
    if n in state.users:
        state.users.remove(n)
        state.save()
    await u.message.reply_text(f"🗑 Removed @{n}")


async def lst(u, c):
    await u.message.reply_text("\n".join(f"@{x}" for x in state.users) or "Koi manual account nahi.")


async def pause(u, c):
    state.paused = True; state.save()
    await u.message.reply_text("⏸ Paused")


async def resume(u, c):
    state.paused = False; state.save()
    await u.message.reply_text("▶️ Resumed")


async def status(u, c):
    await u.message.reply_text(f"Paused: {state.paused}\nPoll: {POLL}s\nFollowing feed: {FOLLOWING_FEED}\n"
                               f"Manual users: {len(state.users)}\nReplies: {SEND_REPLIES} | RTs: {SEND_RETWEETS}")


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    f = filters.User(OWNER_ID)
    for name, fn in [("start", start), ("help", start), ("add", add), ("remove", remove),
                     ("list", lst), ("pause", pause), ("resume", resume), ("status", status)]:
        app.add_handler(CommandHandler(name, fn, filters=f))
    app.run_polling()


if __name__ == "__main__":
    main()
