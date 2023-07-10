import requests, json, os, time, argparse, base64, random, re, pprint
import threading
from mastodon.Mastodon import MastodonNetworkError, MastodonNotFoundError, MastodonGatewayTimeoutError, MastodonBadGatewayError, MastodonAPIError
from bs4 import BeautifulSoup
from datetime import timedelta
from . import args, logger, db_r, HordeMultiGen, mastodon, JobStatus
from requests.structures import CaseInsensitiveDict
from bot.lemmy import lemmy
from bot.ratings import polled_ratings

imgen_params = {
    "n": 1,
    "karras": True,
    # "post_processing": ['GFPGAN'],
}
generic_submit_dict = {
    "prompt": "a horde of cute stable robots in a sprawling server room repairing a massive mainframe",
    "nsfw": False,
    "censor_nsfw": True,
    "r2": True,
    "shared": True,
    "trusted_workers": True,
    "models": ["stable_diffusion"]
}
pp = pprint.PrettyPrinter(depth=3)
term_regex = re.compile(r'draw for (?:me|us) (.+)', re.IGNORECASE)
modifier_seek_regex = re.compile(r'style:', re.IGNORECASE)
prompt_only_regex = re.compile(r'draw for (?:me|us) (.+)style:', re.IGNORECASE)
style_regex = re.compile(r'style: *([\w+*._ -]+)', re.IGNORECASE)

class MentionHandler:

    def __init__(self, notification):
        self.status = JobStatus.INIT
        self.notification = notification
        self.incoming_status = self.notification["status"]
        self.notification_id = self.notification["id"]
        self.request_id = self.incoming_status["id"]
        self.tags = [tag.name for tag in self.incoming_status["tags"]]

        self.mention_content = BeautifulSoup(self.incoming_status["content"],features="html.parser").get_text()

    def is_finished(self):
        return self.status in [JobStatus.DONE, JobStatus.FAULTED]
        
    @logger.catch(reraise=True)
    def handle_notification(self):
        if self.notification["status"]["visibility"] == "direct" and not term_regex.search(self.mention_content):
            self.handle_dm()
        else:
            self.handle_mention()
        
    def handle_mention(self):
        # pp.pprint(notification)
        self.status = JobStatus.WORKING
        logger.debug(f"Handling notification {self.notification_id} as a mention")
        # logger.debug([self.notification_id, last_parsed_notification, self.notification_id < last_parsed_notification])
        reg_res = term_regex.search(self.mention_content)
        if not reg_res:
            logger.info(f"{self.request_id} is not a generation request, skipping")
            db_r.setex(str(self.notification_id), timedelta(days=30), 1)
            self.status = JobStatus.DONE
            return
        styles_array, requested_style = parse_style(self.mention_content)
        if styles_array is None:
            self.reply_faulted("Unfortunately it appears all models in this category are currently not being served. Please select another cateogory")
            return
        if len(styles_array) == 0:
            self.reply_faulted("We could not discover this style in our database. Please pick one from style (https://github.com/db0/Stable-Horde-Styles/blob/main/styles.json) or categories (https://github.com/db0/Stable-Horde-Styles/blob/main/categories.json) ")
            return
        # For now we're only have the same styles on each element. Later we might be able to have multiple ones.
        unformated_prompt = reg_res.group(1)
        negprompt = ''
        if modifier_seek_regex.search(unformated_prompt):
            por = prompt_only_regex.search(self.mention_content)
            unformated_prompt = por.group(1)
        if "###" in unformated_prompt:
            unformated_prompt, negprompt = unformated_prompt.split("###", 1)
        logger.info(f"Starting generation from ID '{self.notification_id}'. Prompt: {unformated_prompt}. Style: {requested_style}")
        submit_list = []
        submit_ratings = False
        for style in styles_array:
            logger.debug(style)
            if "###" not in style["prompt"] and negprompt != '' and "###" not in negprompt:
                negprompt = '###' + negprompt
            submit_dict = generic_submit_dict.copy()
            submit_dict["prompt"] = style["prompt"].format(p=unformated_prompt, np=negprompt)
            submit_dict["params"] = imgen_params.copy()
            if style["model"] == "SDXL_beta::stability.ai#6901":
                submit_dict["params"]["n"] = 2
                submit_ratings = True
            submit_dict["models"] = [style["model"]]
            submit_dict["params"]["width"] = style.get("width", 512)
            submit_dict["params"]["height"] = style.get("height", 512)
            submit_dict["params"]["sampler_name"] = style.get("sampler", "k_euler_a")
            submit_dict["params"]["steps"] = style.get("steps", 45)
            submit_dict["params"]["cfg_scale"] = style.get("cfg_scale", 7.5)
            if "loras" in style:
                submit_dict["params"]["loras"] = style["loras"]
            submit_list.append(submit_dict)
        gen = HordeMultiGen(submit_list, self.notification_id)
        while not gen.all_gens_done():
            if gen.is_faulted():
                if not gen.is_possible():
                    self.reply_faulted("It is not possible to fulfil this request using this style at the moment. Please select a different style and try again.")
                else:
                    self.reply_faulted("Something went wrong when trying to fulfil your request. Please try again later")
                return
            if gen.is_censored():
                self.reply_faulted("Unfortunately all images from this request were censored by the automatic safety filer. Please tweak your prompt to avoid nsfw terms and try again.")
                return
            time.sleep(1)
        media_dicts = []
        done_jobs = gen.get_all_done_jobs()
        for job in done_jobs:
            for iter_fn in range(len(job.filenames)):
                for iter in range(4):
                    try:
                        media_dict = mastodon.media_post(
                            media_file=job.filenames[iter_fn], 
                            description=f"Image with seed {job.seeds[iter_fn]} generated via Stable Diffusion through @stablehorde@sigmoid.social. Prompt: {job.prompt}"
                        )
                        break
                    except (MastodonGatewayTimeoutError, MastodonNetworkError, MastodonBadGatewayError, MastodonAPIError) as e:
                        # If a file fails, we skip it
                        if iter >= 3:
                            continue
                        logger.warning(f"Error '{e}' when uploading files. Retry {iter+1}/3")
                media_dicts.append(media_dict)
                logger.debug(f"Uploaded {job.filenames[iter_fn]}")
        if len(media_dicts) == 0:
            self.reply_faulted("Something went wrong when trying to fulfil your request. Please try again later")
            return
        logger.info(f"replying to {self.request_id}: {self.mention_content}")
        tags_string = ''
        for t in self.tags:
            tags_string += f" #{t}"
        for iter in range(4):
            try:
                visibility = self.incoming_status['visibility']
                # if visibility != 'direct' and os.environ['MASTODON_INSTANCE'] == "hachyderm.io":
                #     public_spot_found = False
                #     for iter in range(5):
                #         daily_post = db_r.get(f"hachyderm_daily_post_{iter}")
                #         if not daily_post:
                #             visibility = 'public'
                #             public_spot_found = True
                #             db_r.setex(f"hachyderm_daily_post_{iter}", timedelta(hours=24), 1)
                #             break
                #     if not public_spot_found:
                #         visibility = 'direct'
                public_minutes = 10
                if os.environ['MASTODON_INSTANCE'] == "hachyderm.io":
                    public_minutes = 120
                if visibility == 'public':
                    if db_r.get(f"{os.environ['MASTODON_INSTANCE']}_unlisted_post"):
                        visibility = 'unlisted'
                    else:
                        visibility = 'public'
                        db_r.setex(f"{os.environ['MASTODON_INSTANCE']}_unlisted_post", timedelta(minutes=public_minutes), 1)
                extra_tags = ''
                if os.environ['MASTODON_INSTANCE'] == "hachyderm.io":
                    extra_tags = " #hachybots"
                reply_text = f"Here are some images matching your request\nPrompt: {unformated_prompt}\nStyle: {requested_style}\n\n#aiart #stablediffusion #aihorde{extra_tags}{tags_string}"
                if len(reply_text) > 500:
                    reply_text = f"Here are some images matching your request\nPrompt: {unformated_prompt[0:300]}...\nStyle: {requested_style}\n\n#aiart #stablediffusion #aihorde{tags_string}"
                media_status_dict = mastodon.status_reply(
                    to_status=self.incoming_status,
                    status=reply_text, 
                    media_ids=media_dicts,
                    spoiler_text="AI Generated Images",
                    visibility=visibility,
                )
                if len(media_dicts) > 1:
                    # Allow the other post to appear
                    time.sleep(5)
                    poll_options = []
                    for iter in range(len(media_dicts)):
                        poll_options.append(f"Generation {iter+1}")
                    poll = mastodon.make_poll(
                        options=poll_options,
                        expires_in=900,
                        # expires_in=300, # Testing
                    )
                    poll_status_dict = mastodon.status_reply(
                        to_status=media_status_dict,
                        status="Please let us know which of the generated images is the best", 
                        visibility=visibility,
                        poll=poll,
                    )
                    ret_poll = poll_status_dict['poll']
                    logger.debug(ret_poll)
                    if submit_ratings:
                        polled_ratings.queue_poll(
                            poll_dict = ret_poll,
                            horde_job = done_jobs[0],
                        )
                if visibility in ["public", "unlisted"]:
                    logger.info("Initiating crosspost to Bot Art")
                    community_id = lemmy.discover_community("botart")
                    image_body = ''
                    for media_dict in media_dicts:
                        image_body += f"![{media_dict['description']}]({media_dict['url']})"
                    if len(media_dicts) > 1:
                        image_body += f"\n\n You can vote for the best image here: {poll_status_dict['url']}"
                    post_result = lemmy.post(
                        community_id=community_id,
                        post_name=f"{requested_style}: {unformated_prompt}"[0:298],
                        post_url=media_dicts[0]["url"],
                        post_body=f"Prompt: {unformated_prompt}\n\nStyle: {requested_style}\n\n{image_body}"
                    )
                    if not post_result:
                        logger.warning("Failed to crosspost to Bot Art")
                break
            except (MastodonGatewayTimeoutError, MastodonNetworkError, MastodonBadGatewayError) as e:
                if iter >= 3:
                    self.reply_faulted("Something went wrong when trying to fulfil your request. Please try again later")
                    return
                logger.warning(f"Network error when replying. Retry {iter+1}/3")
            except (MastodonNotFoundError) as e:
                self.set_faulted()
                logger.error(f"Missing reply. Aborting!")
                return
        for fn in gen.get_all_filenames():
            os.remove(fn)
        # mastodon.status_reply(to_status=self.incoming_status, status="Here is your generation", media_ids=media_dict)
        db_r.setex(str(self.notification_id), timedelta(days=30), 1)
        self.status = JobStatus.DONE

    def handle_dm(self):
        # pp.pprint(notification)
        logger.debug(f"Handling notification {self.notification_id} as a DM")
        db_r.setex(str(self.notification_id), timedelta(days=30), 1)
        self.status = JobStatus.DONE

    def set_faulted(self):
        self.status = JobStatus.FAULTED
        db_r.setex(str(self.notification_id), timedelta(days=30), 1)

    def reply_faulted(self,message):
        self.set_faulted()
        visibility = "unlisted"
        if os.environ['MASTODON_INSTANCE'] == "hachyderm.io":
            visibility = "direct"
        mastodon.status_reply(
            to_status=self.incoming_status,
            status=message,
            visibility=visibility, 
        )

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
        # Horde models
        {
            "url": "https://aihorde.net/api/v2/status/models",
            "default": []
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
    return jsons

def parse_style(mention_content):
    '''retrieves the styles requested and returns a list of unformated style prompts and the models to use'''
    global style_regex
    jsons = get_styles()
    styles = jsons[0]
    categories = jsons[1]
    horde_models = jsons[2]
    style_array = []
    requested_style = "featured"
    sr = style_regex.search(mention_content)
    if sr:
        requested_style = sr.group(1).lower()
    if requested_style in styles:
        if not get_model_worker_count(styles[requested_style]["model"], horde_models):
            logger.error(f"Style '{requested_style}' appear to have no workers. Aborting.")
            return None, None
        n = 4
        if requested_style == "sdxl":
            n = 1
        for iter in range(n):
            style_array.append(styles[requested_style])
    elif requested_style in categories:
        category_styles = expand_category(categories,requested_style)
        category_styles_running = category_styles.copy()
        n = 4
        if "sdxl" in category_styles:
            n = 1
        for iter in range(n):
            if len(category_styles_running) == 0:
                category_styles_running = category_styles.copy()
            random_style = category_styles_running.pop(random.randrange(len(category_styles_running)))    
            if random_style not in styles:
                logger.error(f"Category has style {random_style} which cannot be found in styles json. Skipping.")
                continue
            if not get_model_worker_count(styles[random_style]["model"], horde_models):
                logger.warning(f"Category style {random_style} has no workers available. Skipping.")
                if not len(category_styles_running) and not len(style_array):
                    logger.error(f"All styles in category {requested_style} appear to have no workers. Aborting.")
                    return None, None
                continue
            style_array.append(styles[random_style])
    return style_array, requested_style

def expand_category(categories, category_name):
    styles = []
    for item in categories[category_name]:
        if item in categories:
            styles += expand_category(categories,item)
        else:
            styles.append(item)
    return styles


def get_model_worker_count(model_name, models_json):
    for model_details in models_json:
        if model_name == model_details["name"]:
            return model_details["count"]
    return 0
