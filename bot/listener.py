import threading
from mastodon import StreamListener
from . import logger, handle_mention, handle_dm, mastodon


class StreamListener(StreamListener):

    @logger.catch(reraise=True)
    def on_notification(self,notification):
        if notification["type"] == "mention":
            if notification["status"]["visibility"] == "direct":
                thread = threading.Thread(target=handle_dm, args=(notification,))
            else:
                thread = threading.Thread(target=handle_mention, args=(notification,))
            thread.daemon = True
            thread.start()
    
