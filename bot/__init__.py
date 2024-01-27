import os
import bot.env
from bot.argparser import args
from bot.logger import logger, set_logger_verbosity, quiesce_logger
from bot.redisctrl import get_bot_db, is_redis_up
from bot.lemmy_ctrl import lemmy
from mastodon import Mastodon

db_r = None

if args.type == "mastodon":
    logger.init("Database", status="Connecting")
    if is_redis_up():
        db_r = get_bot_db()
        logger.init_ok("Database", status="Connected")
    else:
        logger.init_err("Database", status="Failed")
        raise Exception("No redis DB found")