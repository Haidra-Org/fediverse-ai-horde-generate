import threading
import time
from mastodon import StreamListener
from . import logger, MentionHandler, mastodon, JobStatus


class StreamListener(StreamListener):
    

    def __init__(self):
        super().__init__()
        self.queue = []
        self.processing_notifications = []
        self.concurrency = 4
        self.queue_thread = threading.Thread(target=self.process_queue, args=())
        self.queue_thread.daemon = True
        self.queue_thread.start()

    @logger.catch(reraise=True)
    def on_notification(self,notification):
        if notification["type"] == "mention":
            self.queue.append(MentionHandler(notification))
    
    @logger.catch(reraise=True)
    def process_queue(self):
        while True:
            processing_notifications = self.processing_notifications.copy()
            for pn in processing_notifications:
                if pn.is_finished():
                    self.processing_notifications.remove(pn)
            if len(self.processing_notifications) < self.concurrency:
                notification_handler = self.queue.pop(0)
                self.processing_notifications.append(notification_handler)
                thread = threading.Thread(target=notification_handler.handle_notification, args=())
                thread.daemon = True
                thread.start()
            time.sleep(1)
