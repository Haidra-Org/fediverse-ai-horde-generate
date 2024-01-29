import  argparse

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('-v', '--verbosity', action='count', default=0, help="The default logging level is ERROR or higher. This value increases the amount of logging seen in your screen")
arg_parser.add_argument('-q', '--quiet', action='count', default=0, help="The default logging level is ERROR or higher. This value decreases the amount of logging seen in your screen")
arg_parser.add_argument('-n', '--number', action='store', default=4, help="Then amount of images to generate per request")
arg_parser.add_argument('type', action='store', help="The type of bot this will be (mastodon or lemmy)")
args = arg_parser.parse_args()
