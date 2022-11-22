import requests, json, os, time, argparse, base64, random, re, pprint
from mastodon import StreamListener
from . import args, logger, db_r


HORDE_URL = "https://stablehorde.net"
imgen_params = {
    "n": 4,
    "width": 512,
    "height":512,
    "steps": 35,
    "sampler_name": "k_euler_a",
    "cfg_scale": 7.5,
    "karras": True,
    "post_processing": ['GFPGAN'],
}
generic_submit_dict = {
    "prompt": "a horde of cute stable robots in a sprawling server room repairing a massive mainframe",
    "nsfw": False,
    "censor_nsfw": True,
    "trusted_workers": True,
    "models": ["stable_diffusion"]
}
pp = pprint.PrettyPrinter(depth=3)


# class StreamListener(StreamListener):
    
#     def on_notification(self,notification):
#         incoming_status = notification["status"]
#         notification_id = notification["id"]
#         request_id = incoming_status["id"]
#         tags = [tag.name for tag in incoming_status["tags"]]
#         pp.pprint(notification)
