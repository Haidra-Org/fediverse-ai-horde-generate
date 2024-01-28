import threading
import time
from bot.lemmy_ctrl import lemmy
from bot.logger import logger
from bot.lemmy_notifications import LemmyMentionHandler


class StreamListenerExtended():
    stop_thread = False
    session_seen_notifications =set()

    def __init__(self):
        super().__init__()
        self.queue = []
        self.processing_notifications = []
        self.concurrency = 4
        self.queue_thread = threading.Thread(target=self.process_queue, args=())
        self.queue_thread.daemon = True
        self.queue_thread.start()
        self.start_loop()

    @logger.catch(reraise=True)
    def start_loop(self):
        while not self.stop_thread:
            mentions = lemmy.mention.list(
                unread_only=True,
                limit=10
            )
            if mentions is None:
                time.sleep(1)
                continue
            for mention in mentions['mentions']:
                mention_id = mention['person_mention']['id']
                if mention_id not in self.session_seen_notifications:
                    self.queue.append(LemmyMentionHandler(mention))
                    self.session_seen_notifications.add(mention_id)
            time.sleep(1)
            
   
    def shutdown(self):
        self.stop_thread = True

    @logger.catch(reraise=True)
    def process_queue(self):
        logger.init("Queue processing thread", status="Starting")
        while True:
            if self.stop_thread:
                logger.init_ok("Queue processing thread", status="Stopped")
                return
            processing_notifications = self.processing_notifications.copy()
            for pn in processing_notifications:
                if pn.is_finished():
                    self.processing_notifications.remove(pn)
                    logger.debug(f"removing {pn}")
            if len(self.queue) and len(self.processing_notifications) < self.concurrency:
                notification_handler = self.queue.pop(0)
                self.processing_notifications.append(notification_handler)
                logger.debug(f"starting {notification_handler}")
                thread = threading.Thread(target=notification_handler.handle_notification, args=())
                thread.daemon = True
                thread.start()
            time.sleep(1)
