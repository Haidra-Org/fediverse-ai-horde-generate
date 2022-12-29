from mastodon import Mastodon
load_dotenv()

Mastodon.create_app(
     'stablehorde_generator',
     api_base_url = os.environ['MASTODON_INSTANCE'],
     to_file = 'pytooter_clientcred.secret'
)