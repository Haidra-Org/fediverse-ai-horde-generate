import requests, json, os, time, argparse, base64, random, re, pprint
import threading
from mastodon.Mastodon import MastodonNetworkError, MastodonNotFoundError, MastodonGatewayTimeoutError, MastodonBadGatewayError, MastodonAPIError
from bs4 import BeautifulSoup
from datetime import timedelta
from . import args, logger, db_r, HordeMultiGen, mastodon, JobStatus
from requests.structures import CaseInsensitiveDict


imgen_params = {
    "n": 1,
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
style_regex = re.compile(r'style: ?([\w ]+)', re.IGNORECASE)

class MentionHandler:

    def __init__(self, notification):
        self.status = JobStatus.INIT
        self.notification = notification

    def is_finished(self):
        return self.status in [JobStatus.DONE, JobStatus.FAULTED]
        
    @logger.catch(reraise=True)
    def handle_notification(self):
        if self.notification["status"]["visibility"] == "direct":
            self.handle_dm()
        else:
            self.handle_mention()
        
    def handle_mention(self):
        # pp.pprint(notification)
        self.status = JobStatus.WORKING
        incoming_status = self.notification["status"]
        notification_id = self.notification["id"]
        request_id = incoming_status["id"]
        tags = [tag.name for tag in incoming_status["tags"]]
        reply_content = BeautifulSoup(incoming_status["content"],features="html.parser").get_text()
        # logger.debug([notification_id, last_parsed_notification, notification_id < last_parsed_notification])
        reg_res = term_regex.search(reply_content)
        if not reg_res:
            logger.info(f"{request_id} is not a generation request, skipping")
            db_r.setex(str(notification_id), timedelta(days=30), 1)
            return
        styles_array, requested_style = parse_style(reply_content)
        # For now we're only have the same styles on each element. Later we might be able to have multiple ones.
        unformated_prompt = reg_res.group(1)
        if modifier_seek_regex.search(unformated_prompt):
            por = prompt_only_regex.search(reply_content)
            unformated_prompt = por.group(1)
        logger.info(f"Starting generation from ID '{notification_id}'. Prompt: {unformated_prompt}. Style: {requested_style}")
        submit_list = []
        for style in styles_array:
            prompt = style["prompt"].format(p=unformated_prompt)
            model = style["model"]
            submit_dict = generic_submit_dict.copy()
            submit_dict["prompt"] = prompt
            submit_dict["params"] = imgen_params
            submit_dict["models"] = [model]
            submit_list.append(submit_dict)
        gen = HordeMultiGen(submit_list, notification_id)
        while not gen.all_gens_done():
            time.sleep(1)
        media_dicts = []
        for job in gen.get_all_done_jobs():
            for iter in range(4):
                try:
                    media_dict = mastodon.media_post(
                        media_file=job.filename, 
                        description=f"Image with seed {job.seed} generated via Stable Diffusion through @stablehorde@sigmoid.social. Prompt: {job.prompt}"
                    )
                    break
                except (MastodonGatewayTimeoutError, MastodonNetworkError, MastodonBadGatewayError) as e:
                    if iter >= 3:
                        # Delete images on crash
                        for fn in gen.get_all_filenames():
                            os.remove(fn)
                        self.status = JobStatus.FAULTED
                        raise e
                    logger.warning(f"Network error when uploading files. Retry {iter+1}/3")
            media_dicts.append(media_dict)
            logger.debug(f"Uploaded {job.filename}")
        logger.info(f"replying to {request_id}: {reply_content}")
        tags_string = ''
        for t in tags:
            tags_string += f" #{t}"
        for iter in range(4):
            try:
                mastodon.status_reply(
                    to_status=incoming_status,
                    status=f"Here are some images matching your request\nPrompt: {unformated_prompt}\nStyle: {requested_style}\n\n#aiart #stablediffusion #stablehorde{tags_string}", 
                    media_ids=media_dicts,
                    spoiler_text="AI Generated Images",
                )
                break
            except (MastodonGatewayTimeoutError, MastodonNetworkError, MastodonBadGatewayError) as e:
                if iter >= 3:
                    self.status = JobStatus.FAULTED
                    raise e
                logger.warning(f"Network error when replying. Retry {iter+1}/3")
        for fn in gen.get_all_filenames():
            os.remove(fn)
        # mastodon.status_reply(to_status=incoming_status, status="Here is your generation", media_ids=media_dict)
        db_r.setex(str(notification_id), timedelta(days=30), 1)
        self.status = JobStatus.DONE

    def handle_dm(self):
        # pp.pprint(notification)
        db_r.setex(str(self.notification['id']), timedelta(days=30), 1)


def get_styles():
    # styles = db_r.get("styles")
    # logger.info([styles, type(styles)])
    downloads = [
        # Styles
        {
            "url": "https://raw.githubusercontent.com/db0/Stable-Horde-Styles/main/styles.json",
            "default": {"raw": "{p}"}
        },
        # Categories
        {
            "url": "https://raw.githubusercontent.com/db0/Stable-Horde-Styles/main/categories.json",
            "default": {}
        },
    ]
    logger.debug("Downloading styles")
    jsons = []
    for download in downloads:
        for iter in range(5):
            try:
                r = requests.get(download["url"])
                jsons.append(r.json())
                break
            except Exception as e:
                if iter >= 3: 
                    jsons.append(download["default"])
                    break
                logger.warning(f"Error during file download. Retrying ({iter+1}/3)")
                time.sleep(1)
    return(jsons)

def parse_style(reply_content):
    '''retrieves the styles requested and returns a list of unformated style prompts and the models to use'''
    global style_regex
    jsons = get_styles()
    styles = jsons[0]
    categories = jsons[1]
    style_array = []
    requested_style = 'raw'
    default_style = {
            "prompt": "{p}",
            "model": "stable_diffusion"
        }
    for iter in range(4):
        style_array.append(default_style)
    sr = style_regex.search(reply_content)
    if sr:
        requested_style = sr.group(1).lower()
        if requested_style in styles:
            style_array = []
            for iter in range(4):
                style_array.append(styles[requested_style])
        elif requested_style in categories:
            categories_copy = {}
            style_array = []
            for iter in range(4):
                if len(categories_copy) == 0:
                    categories_copy = categories.copy()            
                random_key = random.choice(list(categories_copy.keys()))
                style_array.append(categories_copy.pop(random_key))
    logger.debug(style_array)
    return(style_array, requested_style)