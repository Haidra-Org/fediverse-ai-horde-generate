import os
import threading
from mastodon import Mastodon
from mastodon.Mastodon import MastodonNetworkError, MastodonNotFoundError, MastodonGatewayTimeoutError, MastodonBadGatewayError, MastodonAPIError
from bot import args, logger, db_r, set_logger_verbosity, quiesce_logger, handle_mention, handle_dm
from dotenv import load_dotenv


load_dotenv()
set_logger_verbosity(args.verbosity)
quiesce_logger(args.quiet)

mastodon = Mastodon(
    access_token = 'pytooter_usercred.secret',
    api_base_url = 'https://sigmoid.social'
)


@logger.catch(reraise=True)
def check_for_requests():
    notifications = mastodon.notifications(
        exclude_types=["follow", "favourite", "reblog", "poll", "follow_request"]
    )
    notifications.reverse()
    # pp.pprint(notifications[0])
    logger.info(f"Retrieved {len(notifications)} notifications.")
    waiting_threads = []
    for notification in notifications:
        if db_r.get(notification["id"]):
            continue
        if notification["status"]["visibility"] == "direct":
            thread = threading.Thread(target=handle_dm, args=(notification,))
        else:
            thread = threading.Thread(target=handle_mention, args=(notification,))
        thread.start()
        waiting_threads.append(thread)    

logger.init("Mastodon Stable Horde Bot", status="Starting")
try:
    check_for_requests()
    while True:
        try:
            listener = StreamListener(mastodon)
            mastodon.stream_user(listener=listener)
            time.sleep(1)
        except (MastodonGatewayTimeoutError, MastodonNetworkError, MastodonBadGatewayError, MastodonAPIError):
            logger.warning("MastodonNetworkError reopening connection")
except KeyboardInterrupt:
    logger.init_ok("Mastodon Stable Horde Bot", status="Exited")