import os
from dotenv import load_dotenv
from bot.argparser import args
from bot.logger import logger, set_logger_verbosity, quiesce_logger
from bot.redisctrl import get_bot_db, is_redis_up
from bot.lemmy_ctrl import lemmy
from mastodon import Mastodon


load_dotenv()

db_r = None
logger.init("Database", status="Connecting")
if is_redis_up():
    db_r = get_bot_db()
    logger.init_ok("Database", status="Connected")
else:
    logger.init_err("Database", status="Failed")
    raise Exception("No redis DB found")

if args.type == "mastodon":
    mastodon = Mastodon(
        access_token = 'pytooter_usercred.secret',
        api_base_url = f"https://{os.environ['MASTODON_INSTANCE']}"
    )

    from bot.mastodon_notifications import MentionHandler
    from bot.mastodon_listener import StreamListenerExtended
if args.type == "lemmy":
    from bot.lemmy_notifications import MentionHandler
    from bot.lemmy_listener import StreamListenerExtended
        