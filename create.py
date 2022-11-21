from mastodon import Mastodon

Mastodon.create_app(
     'stablehorde_generator',
     api_base_url = 'https://sigmoid.social',
     to_file = 'pytooter_clientcred.secret'
)