import os
from pythorhead import Lemmy

lemmy = None
if os.environ['LEMMY_INSTANCE']:
    lemmy = Lemmy(f"https://{os.environ['LEMMY_INSTANCE']}", request_timeout=30)
    lemmy.log_in(os.environ['LEMMY_USERNAME'], os.environ['LEMMY_PASSWORD'])

lemmy_image_community_id = lemmy.discover_community("botart")
