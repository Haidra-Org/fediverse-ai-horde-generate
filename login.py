import os
from dotenv import load_dotenv
from mastodon import Mastodon

load_dotenv()

mastodon = Mastodon(
    client_id = 'pytooter_clientcred.secret',
    api_base_url = f"https://{os.environ['MASTODON_INSTANCE']}"
)
mastodon.log_in(
    os.environ['EMAIL'],
    os.environ['PASSWORD'],
    to_file = 'pytooter_usercred.secret'
)
