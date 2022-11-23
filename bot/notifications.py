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
    "steps": 45,
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
        logger.debug(f"Handling notification {notification_id} as a mention")
        tags = [tag.name for tag in incoming_status["tags"]]
        reply_content = BeautifulSoup(incoming_status["content"],features="html.parser").get_text()
        # logger.debug([notification_id, last_parsed_notification, notification_id < last_parsed_notification])
        reg_res = term_regex.search(reply_content)
        if not reg_res:
            logger.info(f"{request_id} is not a generation request, skipping")
            db_r.setex(str(notification_id), timedelta(days=30), 1)
            self.status = JobStatus.DONE
            return
        styles_array, requested_style = parse_style(reply_content)
        if len(styles_array) == 0:
            self.reply_faulted("We could not discover this style in our database. Please pick one from style (https://github.com/db0/Stable-Horde-Styles/blob/main/styles.json) or categories (https://github.com/db0/Stable-Horde-Styles/blob/main/categories.json) ")
            return
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
            if gen.is_faulted():
                if not gen.is_possible():
                    self.reply_faulted("It is not possible to fulfil this request using this style at the moment. Please select a different style and try again.")
                else:
                    self.reply_faulted("Something went wrong when trying to fulfil your request. Please try again later")
                return
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
                        self.reply_faulted("Something went wrong when trying to fulfil your request. Please try again later")
                        return
                    logger.warning(f"Network error when uploading files. Retry {iter+1}/3")
            media_dicts.append(media_dict)
            logger.debug(f"Uploaded {job.filename}")
        logger.info(f"replying to {request_id}: {reply_content}")
        tags_string = ''
        for t in tags:
            tags_string += f" #{t}"
        for iter in range(4):
            try:
                visibility = incoming_status['visibility']
                if visibility == 'public':
                    if db_r.get("unlisted_post"):
                        visibility = 'unlisted'
                    else:
                        visibility = 'public'
                        db_r.setex("unlisted_post", timedelta(minutes=30), 1)
                mastodon.status_reply(
                    to_status=incoming_status,
                    status=f"Here are some images matching your request\nPrompt: {unformated_prompt}\nStyle: {requested_style}\n\n#aiart #stablediffusion #stablehorde{tags_string}", 
                    media_ids=media_dicts,
                    spoiler_text="AI Generated Images",
                    visibility=visibility,
                )
                break
            except (MastodonGatewayTimeoutError, MastodonNetworkError, MastodonBadGatewayError) as e:
                if iter >= 3:
                    self.reply_faulted("Something went wrong when trying to fulfil your request. Please try again later")
                    return
                logger.warning(f"Network error when replying. Retry {iter+1}/3")
        for fn in gen.get_all_filenames():
            os.remove(fn)
        # mastodon.status_reply(to_status=incoming_status, status="Here is your generation", media_ids=media_dict)
        db_r.setex(str(notification_id), timedelta(days=30), 1)
        self.status = JobStatus.DONE

    def handle_dm(self):
        # pp.pprint(notification)
        logger.debug(f"Handling notification {self.notification['id']} as a DM")
        db_r.setex(str(self.notification['id']), timedelta(days=30), 1)
        self.status = JobStatus.DONE

    def reply_faulted(self,message):
        self.status = JobStatus.FAULTED
        incoming_status = self.notification["status"]
        notification_id = self.notification["id"]
        mastodon.status_reply(
            to_status=incoming_status,
            status=message, 
        )
        db_r.setex(str(notification_id), timedelta(days=30), 1)


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
                r = requests.get(download["url"],timeout=5)
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
    requested_style = "raw"
    sr = style_regex.search(reply_content)
    if sr:
        requested_style = sr.group(1).lower()
    if requested_style in styles:
        for iter in range(4):
            style_array.append(styles[requested_style])
    elif requested_style in categories:
        category_copy = []
        for iter in range(4):
            if len(category_copy) == 0:
                category_copy = categories[requested_style].copy()
            random_style = category_copy.pop(random.randrange(len(category_copy)))    
            if random_style not in styles:
                logger.error(f"Category has style {random_style} which cannot be found in styles json:")
                continue
            style_array.append(styles[random_style])
    logger.debug(style_array)
    return(style_array, requested_style)