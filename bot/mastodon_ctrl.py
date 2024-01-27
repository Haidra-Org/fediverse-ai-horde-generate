import os
from mastodon import Mastodon

mastodon = Mastodon(
    access_token = 'pytooter_usercred.secret',
    api_base_url = f"https://{os.environ['MASTODON_INSTANCE']}"
)