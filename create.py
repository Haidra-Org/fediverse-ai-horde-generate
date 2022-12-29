from mastodon import Mastodon
load_dotenv()

Mastodon.create_app(
     'stablehorde_generator',
     api_base_url = os.environ['https://sigmoid.social'],
     to_file = 'pytooter_clientcred.secret'
)