import os
from pythorhead import Lemmy

lemmy = None
if os.environ['LEMMY_INSTANCE']:
    lemmy = Lemmy(f"https://{os.environ['LEMMY_INSTANCE']}", request_timeout=5)
    lemmy.log_in(os.environ['LEMMY_USERNAME'], os.environ['LEMMY_PASSWORD'])
