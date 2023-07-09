import threading
import copy
import requests
import time
from loguru import logger
from datetime import datetime
from . import  mastodon

class PolledRatings:

    known_polls = []
    headers = {
        "Client-Agent": "db0_mastodon_bot:1.0.0:(discord)db0#1625"
    }

    def __init__(self):
        self.thread = threading.Thread(target=self.check_poll_thread, args=())
        self.thread.daemon = True
        self.thread.start()

    def check_poll_thread(self):
        while True:
            self.check_polls()
            time.sleep(5)

    def check_polls(self):
        for poll in copy.deepcopy(self.known_polls):
            logger.debug(f"checking {poll}")
            if poll["expiry"].timestamp() > datetime.now().timestamp():
                continue
            poll_info = mastodon.poll(poll["id"])
            if poll_info["expired"] is False:
                continue
            max_title = max(poll_info["options"], key=lambda x: x['votes_count'])['title']
            max_votes = max(poll_info["options"], key=lambda x: x['votes_count'])['votes_count']
            tied = any(v['votes_count'] == max_votes for v in poll_info["options"])
            if tied:
                logger.info(f"WP {poll['wp_id']} is tied at {max_votes}. Ignoring")
                self.known_polls.remove(poll)
                continue
            _, winning_gen = max_title.split(' ', 1)
            # To make it match the list index
            winning_gen -= 1
            submit_dict = {"best": poll["image_ids"][winning_gen]}
            try:
                submit_req = requests.post(
                    f"https://aihorde.net/api/v2/generate/rate/{poll['wp_id']}", 
                    json = submit_dict, 
                    headers = self.headers, 
                    timeout = 3
                )
            except Exception as err:
                logger.error(f"Exception when submitting ratings: {err}")
                self.known_polls.remove(poll)
                continue
            if not submit_req.ok:
                logger.error(f"Error when submitting ratings: {submit_req.text}")
                self.known_polls.remove(poll)
                continue
            logger.info(f"Succesfully submitted rating for WP {poll['wp_id']}")

    def queue_poll(self, poll_dict, horde_job):
        poll_entry = {
            "id": poll_dict["id"],
            "expiry": poll_dict["expires_at"],
            "wp_id": horde_job.req_id,
            "image_ids": horde_job.img_ids,
        }
        self.known_polls.append(poll_entry)
        logger.debug(f"Queued poll {poll_dict['id']} for wp {horde_job.req_id}")


polled_ratings = PolledRatings()