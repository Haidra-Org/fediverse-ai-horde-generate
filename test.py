import time
import os
from pythorhead import Lemmy
from dotenv import load_dotenv
import json
load_dotenv()

lemmy = None
if os.environ['LEMMY_INSTANCE']:
    lemmy = Lemmy(f"https://{os.environ['LEMMY_INSTANCE']}", request_timeout=5)
    lemmy.log_in(os.environ['LEMMY_USERNAME'], os.environ['LEMMY_PASSWORD'])

def start_loop():
    while True:
        time.sleep(1)
        mentions = lemmy.mention.list(
            unread_only=True,
            limit=10
        )
        for mention in mentions['mentions']:
            lemmy.comment.create(
                post_id = mention['comment']['post_id'], 
                content = "Cheers", 
                parent_id = mention['person_mention']['comment_id'], 
                )
        break
start_loop()
            
# d = lemmy.image.upload('/home/db0/Pictures/SD_INPUTS/logo.png')
# print(json.dumps(d, indent=4))