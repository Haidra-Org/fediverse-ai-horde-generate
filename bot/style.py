import requests,time,random, re
from bot.logger import logger
from bot.horde import HordeMultiGen
from bot.argparser import args
from bot.exceptions import *

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
term_regex = re.compile(r'draw (for )?(?:me|us) (.+)', re.IGNORECASE)
modifier_seek_regex = re.compile(r'style:', re.IGNORECASE)
prompt_only_regex = re.compile(r'draw (for )?(?:me|us) (.+)style:', re.IGNORECASE)
style_regex = re.compile(r'style: *([\w+*._ -]+)', re.IGNORECASE)

class Styling:
    
    notification_text: str
    prompt: str
    negprompt: str = ''
    style: str
    style_array: list[str] = None
    gen: HordeMultiGen
    submit_list: list[dict] = []

    def __init__(self, notification_text):
        self.notification_text = notification_text
        reg_res = term_regex.search(notification_text)
        if not reg_res:
            raise HordeBotException
        unformated_prompt = reg_res.group(2)
        if modifier_seek_regex.search(unformated_prompt):
            por = prompt_only_regex.search(notification_text)
            unformated_prompt = por.group(2)
        self.prompt = unformated_prompt
        if "###" in unformated_prompt:
            self.prompt, self.negprompt = unformated_prompt.split("###", 1)
        self.parse_style()
        self.prepare_payload()

    def prepare_payload(self):
        if self.style_array is None:
            raise UnknownStyle
        if len(self.style_array) == 0:
            raise ModelNotServed
        self.submit_list = []
        n_per = args.number
        if len(self.style_array) == int(args.number / 2) and len(self.style_array) > 1:
            n_per = int(args.number / 2)
        if len(self.style_array) > int(args.number / 2):
            n_per = 1
        for style in self.style_array:
            logger.debug(style)
            negprompt = self.negprompt
            if "###" not in style["prompt"] and negprompt != '' and "###" not in negprompt:
                negprompt = '###' + negprompt
            submit_dict = generic_submit_dict.copy()
            submit_dict["prompt"] = style["prompt"].format(p=self.prompt, np=negprompt)
            submit_dict["params"] = imgen_params.copy()
            submit_dict["models"] = [style["model"]]
            submit_dict["params"]["width"] = style.get("width", 512)
            submit_dict["params"]["height"] = style.get("height", 512)
            submit_dict["params"]["sampler_name"] = style.get("sampler_name", "k_euler_a")
            submit_dict["params"]["steps"] = style.get("steps", 45)
            submit_dict["params"]["cfg_scale"] = style.get("cfg_scale", 7.5)
            submit_dict["params"]["hires_fix"] = style.get("hires_fix", False)
            submit_dict["params"]["n"] = n_per
            if "loras" in style:
                submit_dict["params"]["loras"] = style["loras"]
            if "tis" in style:
                submit_dict["params"]["tis"] = style["tis"]
            self.submit_list.append(submit_dict)
    
    def request_images(self, unique_id) -> HordeMultiGen:
        logger.info(f"Starting generation from ID '{unique_id}'. Prompt: {self.prompt}. Style: {self.style}")
        self.gen = HordeMultiGen(self.submit_list, unique_id)
        while not self.gen.all_gens_done():
            if self.gen.is_faulted():
                if not self.gen.is_possible():
                    raise CurrentlyImpossible
                else:
                    raise UnknownError
            if self.gen.is_censored():
                raise AllCensored
            time.sleep(1)
        return self.gen


    def get_styles(self):
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
                except Exception as err:
                    if iter >= 3:
                        jsons.append(download["default"])
                        break
                    logger.warning(f"Error during file download ({err}). Retrying ({iter+1}/3)")
                    time.sleep(1)
        return jsons

    def parse_style(self):
        '''retrieves the styles requested and returns a list of unformated style prompts and the models to use'''
        global style_regex
        jsons = self.get_styles()
        styles = jsons[0]
        categories = jsons[1]
        horde_models = jsons[2]
        requested_style = "featured"
        sr = style_regex.search(self.notification_text)
        if sr:
            requested_style = sr.group(1).lower()  
        if requested_style == "featured":
            requested_style = self.get_featured_style(categories)
        if requested_style in styles:
            self.style_array = []
            if not self.get_model_worker_count(styles[requested_style]["model"], horde_models):
                logger.error(f"Style '{requested_style}' appear to have no workers. Aborting.")
                return None, None
            self.style_array.append(styles[requested_style])
        elif requested_style in categories:
            self.style_array = []
            category_styles = self.expand_category(categories,requested_style)
            category_styles_running = category_styles.copy()
            n = 4
            uses_sdxl_beta = None
            for iter in range(n):
                if len(category_styles_running) == 0:
                    # category_styles_running = category_styles.copy()
                    break # We instead use n > 1 now to be more efficient
                random_style = category_styles_running.pop(random.randrange(len(category_styles_running)))
                if random_style not in styles:
                    logger.error(f"Category has style {random_style} which cannot be found in styles json. Skipping.")
                    continue
                if not self.get_model_worker_count(styles[random_style]["model"], horde_models):
                    logger.warning(f"Category style {random_style} has no workers available. Skipping.")
                    if not len(category_styles_running) and not len(self.style_array):
                        logger.error(f"All styles in category {requested_style} appear to have no workers. Aborting.")
                        return None, None
                    continue
                is_sdxl_beta = styles[random_style]["model"] == "SDXL_beta::stability.ai#6901"
                # We don't want to mix SD1.5/SD2 with SDXL_beta
                if uses_sdxl_beta is False and is_sdxl_beta:
                    continue
                self.style_array.append(styles[random_style])
                # When the category has an sdxl_beta style, we use only 1 of them as it gets 2 images from that one
                if is_sdxl_beta is True:
                    break
                if uses_sdxl_beta is None:
                    uses_sdxl_beta = is_sdxl_beta
        self.style = requested_style

    def expand_category(self,categories, category_name):
        styles = []
        for item in categories[category_name]:
            if item in categories:
                styles += self.expand_category(categories,item)
            else:
                styles.append(item)
        return styles


    def get_featured_style(self,categories):
        return categories['featured'][0]


    def get_model_worker_count(self,model_name, models_json):
        for model_details in models_json:
            if model_name == model_details["name"]:
                return model_details["count"]
        return 0

    @staticmethod
    def is_generation_request(text):
        return term_regex.search(text)