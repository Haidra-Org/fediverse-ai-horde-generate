from .argparser import args
from .logger import logger, set_logger_verbosity, quiesce_logger
from .redisctrl import get_bot_db, is_redis_up
from .listener import StreamListener


db_r = None
logger.init("Database", status="Connecting")
if is_redis_up():
	db_r = get_bot_db()
	logger.init_ok("Database", status="Connected")
else:
	logger.init_err("Database", status="Failed")
    raise Exception("No redis DB found")