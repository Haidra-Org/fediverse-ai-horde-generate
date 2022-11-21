import requests, json, os, time, argparse, base64
from mastodon import Mastodon
from mastodon.Mastodon import MastodonNetworkError
from bot import args, logger, get_bot_db, is_redis_up, set_logger_verbosity, quiesce_logger
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageFont, ImageDraw, ImageFilter, ImageOps
from io import BytesIO

load_dotenv()
set_logger_verbosity(args.verbosity)
quiesce_logger(args.quiet)
import pprint, re

db_r = None
logger.init("Database", status="Connecting")
if is_redis_up():
	db_r = get_bot_db()
	logger.init_ok("Database", status="Connected")
else:
	logger.init_err("Database", status="Failed")

pp = pprint.PrettyPrinter(depth=3)
term_regex = re.compile(r'draw for me (.*)', re.IGNORECASE)

mastodon = Mastodon(
    access_token = 'pytooter_usercred.secret',
    api_base_url = 'https://sigmoid.social'
)

HORDE_URL = "https://stablehorde.net"
imgen_params = {
    "n": 1,
    "width": 512,
    "height":512,
    "steps": 30,
    "sampler_name": "k_euler_a",
    "cfg_scale": 7.5,
    "post_processing": ['GFPGAN'],
}
generic_submit_dict = {
    "prompt": "a horde of cute stable robots in a sprawling server room repairing a massive mainframe",
    "nsfw": False,
    "censor_nsfw": True,
    "trusted_workers": True,
    "models": ["stable_diffusion"]
}

@logger.catch(reraise=True)
def check_for_requests():
    last_parsed_notification = db_r.get("last_parsed_id")
    if last_parsed_notification != None:
        # last_parsed_notification = {"id": int(last_parsed_notification)}
        last_parsed_notification = int(last_parsed_notification)
    logger.debug(f"Last notification ID: {last_parsed_notification}")
    notifications = mastodon.notifications(
        # min_id=last_parsed_notification,  # doesn't work atm https://github.com/halcy/Mastodon.py/issues/270
        exclude_types=["follow", "favourite", "reblog", "poll", "follow_request"]
    )
    notifications.reverse()
    # pp.pprint(notifications)
    logger.info(f"Retrieved {len(notifications)} notifications.")
    for notification in notifications:
        incoming_status = notification["status"]
        request_id = incoming_status["id"]
        tags = [tag.name for tag in incoming_status["tags"]]
        reply_content = BeautifulSoup(incoming_status["content"],features="html.parser").get_text()
        # logger.debug([request_id, last_parsed_notification, request_id < last_parsed_notification])
        reg_res = term_regex.search(reply_content)
        if request_id <= last_parsed_notification:
            logger.debug(f"skipping {request_id} < {last_parsed_notification}")
            continue
        if not reg_res:
            logger.info(f"{request_id} is not a generation request, skipping")
            if request_id > last_parsed_notification:
                db_r.set("last_parsed_id",request_id)
            continue
        headers = {"apikey": os.environ['HORDE_API']}
        submit_dict = generic_submit_dict.copy()
        submit_dict["prompt"] = reg_res.group(1)
        submit_dict["params"] = imgen_params
        logger.debug(f"Submitting: {submit_dict}")
        submit_req = requests.post(f'{HORDE_URL}/api/v2/generate/async', json = submit_dict, headers = headers)
        if submit_req.ok:
            submit_results = submit_req.json()
            logger.debug(submit_results)
            req_id = submit_results['id']
            is_done = False
            while not is_done:
                chk_req = requests.get(f'{HORDE_URL}/api/v2/generate/check/{req_id}')
                if not chk_req.ok:
                    logger.error(chk_req.text)
                    return
                chk_results = chk_req.json()
                logger.info(chk_results)
                is_done = chk_results['done']
                time.sleep(0.8)
            retrieve_req = requests.get(f'{HORDE_URL}/api/v2/generate/status/{req_id}')
            if not retrieve_req.ok:
                logger.error(retrieve_req.text)
                return
            results_json = retrieve_req.json()
            # logger.debug(results_json)
            if results_json['faulted']:
                final_submit_dict = request_data.get_submit_dict()
                if "source_image" in final_submit_dict:
                    final_submit_dict["source_image"] = f"img2img request with size: {len(final_submit_dict['source_image'])}"
                logger.error(f"Something went wrong when generating the request. Please contact the horde administrator with your request details: {final_submit_dict}")
                return
            results = results_json['generations']
            seed = None
            for iter in range(len(results)):
                seed = results[iter]["seed"]
                b64img = results[iter]["img"]
                base64_bytes = b64img.encode('utf-8')
                img_bytes = base64.b64decode(base64_bytes)
                img = Image.open(BytesIO(img_bytes))
                final_filename = "horde_generation.jpg"
                img.save(final_filename)
                logger.info(f"Saved {final_filename}")
        else:
            logger.error(submit_req.text)
        logger.info(f"replying to {request_id}: {reply_content} - {tags}")
        media_dict = mastodon.media_post(media_file="horde_generation.jpg", description="Image request generated via Stable Diffusion through @stablehorde@sigmoid.social")
        tags_string = ''
        for t in tags:
            tags_string += f" #{t}"
        mastodon.status_reply(to_status=incoming_status, status=f"Here is an image matching your prompt with seed {seed}\n\n#aiart #stablediffusion #stablehorde{tags_string}", media_ids=media_dict)
        # mastodon.status_reply(to_status=incoming_status, status="Here is your generation", media_ids=media_dict)
        if request_id > last_parsed_notification:
            db_r.set("last_parsed_id",request_id)



logger.init("Mastodon Stable Horde Bot", status="Starting")
try:
    while True:
        try:
            check_for_requests()
            time.sleep(5)
        except MastodonNetworkError:
            logger.warning("MastodonNetworkError skipping iteration")
except KeyboardInterrupt:
    logger.init_ok("Mastodon Stable Horde Bot", status="Exited")