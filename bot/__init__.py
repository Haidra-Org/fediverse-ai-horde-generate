import os
from dotenv import load_dotenv
from .argparser import args
from .logger import logger, set_logger_verbosity, quiesce_logger
from .redisctrl import get_bot_db, is_redis_up
from .enums import JobStatus
from .horde import HordeGenerate, HordeMultiGen
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


mastodon = Mastodon(
    access_token = 'pytooter_usercred.secret',
    api_base_url = f"https://{os.environ['MASTODON_INSTANCE']}"
)

from .notifications import MentionHandler
from .listener import StreamListenerExtended
    