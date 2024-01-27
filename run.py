import os, time
import threading
from mastodon.Mastodon import MastodonNetworkError, MastodonGatewayTimeoutError, MastodonBadGatewayError, MastodonAPIError
from bot.argparser import args
from bot.logger import logger, set_logger_verbosity, quiesce_logger
from bot.redisctrl import db_r

set_logger_verbosity(args.verbosity)
quiesce_logger(args.quiet)


@logger.catch(reraise=True)
def check_for_requests():
    notifications = mastodon.notifications(
        exclude_types=["follow", "favourite", "reblog", "poll", "follow_request"]
    )
    notifications.reverse()
    logger.info(f"Retrieved {len(notifications)} notifications.")
    waiting_threads = []
    for notification in notifications:
        if db_r.get(str(notification["id"])):
            continue
        notification_handler = MentionHandler(notification)
        thread = threading.Thread(target=notification_handler.handle_notification, args=())
        thread.start()
        waiting_threads.append(thread)    

logger.init("Mastodon Stable Horde Bot", status="Starting")
try:
    from bot.mastodon_notifications import db_r, MentionHandler
    from bot.mastodon_listener import StreamListenerExtended
    from bot.mastodon_ctrl import mastodon
    check_for_requests()
    while True:
        try:
            logger.debug(f"Starting Listener")
            listener = StreamListenerExtended()
            logger.debug(f"Streaming User")
            mastodon.stream_user(listener=listener)
            time.sleep(1)
        except (MastodonGatewayTimeoutError, MastodonNetworkError, MastodonBadGatewayError, MastodonAPIError) as e:
            logger.warning(f"{e} reopening connection")
            listener.shutdown()
            time.sleep(10)
except KeyboardInterrupt:
    logger.init_ok("Mastodon Stable Horde Bot", status="Exited")