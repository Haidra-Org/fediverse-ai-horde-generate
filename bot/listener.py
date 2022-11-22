import requests, json, os, time, argparse, base64, random, re, pprint
import threading
from mastodon.Mastodon import MastodonNetworkError, MastodonNotFoundError, MastodonGatewayTimeoutError, MastodonBadGatewayError, MastodonAPIError
from mastodon import StreamListener
from bs4 import BeautifulSoup
from datetime import timedelta
from . import args, logger, db_r, HordeMultiGen


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
term_regex = re.compile(r'draw for me (.+)', re.IGNORECASE)
modifier_seek_regex = re.compile(r'style:', re.IGNORECASE)
prompt_only_regex = re.compile(r'draw for me (.+)style:', re.IGNORECASE)
style_regex = re.compile(r'style: ?(\w+)', re.IGNORECASE)


class StreamListener(StreamListener):
    

    def __init__(self,mastodon):
        super().__init__()
        self.mastodon = mastodon

    @logger.catch(reraise=True)
    def on_notification(self,notification):
        if notification["type"] == "mention":
            if notification["status"]["visibility"] == "direct":
                thread = threading.Thread(target=self.handle_dm, args=(notification,))
            else:
                thread = threading.Thread(target=self.handle_mention, args=(notification,))
            thread.daemon = True
            thread.start()
    
    def handle_mention(self, notification):
        # pp.pprint(notification)
        incoming_status = notification["status"]
        notification_id = notification["id"]
        request_id = incoming_status["id"]
        tags = [tag.name for tag in incoming_status["tags"]]
        reply_content = BeautifulSoup(incoming_status["content"],features="html.parser").get_text()
        # logger.debug([notification_id, last_parsed_notification, notification_id < last_parsed_notification])
        reg_res = term_regex.search(reply_content)
        # if notification_id <= last_parsed_notification:
        #     logger.debug(f"skipping {notification_id} < {last_parsed_notification}")
        #     continue
        if not reg_res:
            logger.info(f"{request_id} is not a generation request, skipping")
            # if notification_id > last_parsed_notification:
            #     db_r.set("last_parsed_id",notification_id)
            return
        styles_array = parse_style(reply_content)
        # For now we're only have the same styles on each element. Later we might be able to have multiple ones.
        unformated_prompt = reg_res.group(1)
        if modifier_seek_regex.search(unformated_prompt):
            por = prompt_only_regex.search(reply_content)
            unformated_prompt = por.group(1)
        submit_list = []
        for style in styles_array:
            prompt = style["prompt"].format(p=unformated_prompt)
            model = style["model"]
            submit_dict = generic_submit_dict.copy()
            submit_dict["prompt"] = prompt
            submit_dict["params"] = imgen_params
            submit_dict["models"] = [model]
            logger.debug(submit_dict)
            submit_list.append(submit_list)
        gen = HordeMultiGen(submit_list, notification_id)
        while not gen.all_gens_done():
            time.sleep(1)
        media_dicts = []
        for filename in gen.get_all_filenames():
            for iter in range(4):
                try:
                    media_dict = self.mastodon.media_post(
                        media_file=filename, 
                        description=f"Image with seed {seed} generated via Stable Diffusion through @stablehorde@sigmoid.social. Prompt: {unformated_prompt}"
                    )
                    break
                except (MastodonGatewayTimeoutError, MastodonNetworkError, MastodonBadGatewayError) as e:
                    if iter >= 3:
                        # Delete images on crash
                        for fn in gen.get_all_filenames():
                            os.remove(fn)
                        raise e
                    logger.warning(f"Network error when uploading files. Retry {iter+1}/3")
            media_dicts.append(media_dict)
            logger.debug(f"Uploaded {final_filename}")
        logger.info(f"replying to {request_id}: {reply_content}")
        tags_string = ''
        for t in tags:
            tags_string += f" #{t}"
        for iter in range(4):
            try:
                self.mastodon.status_reply(
                    to_status=incoming_status,
                    status=f"Here are some images matching your prompt\n\n#aiart #stablediffusion #stablehorde{tags_string}", 
                    media_ids=media_dicts,
                    spoiler_text="AI Generated Images",
                )
                break
            except (MastodonGatewayTimeoutError, MastodonNetworkError, MastodonBadGatewayError) as e:
                if iter >= 3:
                    raise e
                logger.warning(f"Network error when replying. Retry {iter+1}/3")
        for fn in gen.get_all_filenames():
            os.remove(fn)
        # mastodon.status_reply(to_status=incoming_status, status="Here is your generation", media_ids=media_dict)
        # if notification_id > last_parsed_notification:
        #     db_r.set("last_parsed_id",notification_id)

    def handle_dm(self, notification):
        pp.pprint(notification)

def get_styles():
    # styles = db_r.get("styles")
    # logger.info([styles, type(styles)])
    logger.debug("Downloading styles")
    for iter in range(5):
        try:
            r = requests.get("https://raw.githubusercontent.com/db0/Stable-Horde-Styles/main/styles.json")
            styles = r.json()
            # db_r.setex("styles", timedelta(minutes=30), styles)
            break
        except Exception as e:
            if iter >= 3: 
                styles = {"raw": "{p}"}
                break
            logger.warning(f"Error during style download. Retrying ({iter+1}/3)")
            time.sleep(1)
    return(styles)

def parse_style(reply_content):
    '''retrieves the styles requested and returns a list of unformated style prompts and the models to use'''
    global style_regex
    styles = get_styles()
    style_array = []
    default_style = {
            "prompt": "{p}",
            "model": "stable_diffusion"
        }
    for iter in range(4):
        style_array.append(default_style)
    sr = style_regex.search(reply_content)
    if sr:
        requested_style = sr.group(1)
        if requested_style == "raw":
            for iter in range(4):
                style_array = [styles[requested_style]]
        else:
            for category in styles:
                if requested_style == category:
                    # TODO: For now I do all of them in a random style. Later I will switch it to a random style per image
                    random_key = random.choice(list(styles[category].keys()))
                    for iter in range(4):
                        style_array = [styles[category][random_key]]
                        # style_array = [styles[category].pop(key)] # for the TODO
                if requested_style in styles[category]:
                    for iter in range(4):
                        style_array = [styles[category][requested_style]]
    logger.debug(style_array)
    return(style_array)