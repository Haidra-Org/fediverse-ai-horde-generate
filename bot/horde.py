
import requests, json, os, time, base64
import threading
from requests.exceptions import MissingSchema
from bot.logger import logger
from bot.enums import JobStatus
from PIL import Image, ImageFont, ImageDraw, ImageFilter, ImageOps
from io import BytesIO

HORDE_URL = "https://aihorde.net"

class HordeMultiGen:
    def __init__(self, submit_dicts, unique_id):
        self.submit_dicts = submit_dicts
        self.unique_id = unique_id
        self.status = JobStatus.INIT
        self.jobs = []
        iter = 0
        logger.debug(submit_dicts)
        for submit_dict in self.submit_dicts:
            job_unique_id = str(iter) + '_' + str(self.unique_id)
            self.jobs.append(HordeGenerate(submit_dict, job_unique_id, True))
            iter += 1
            time.sleep(0.75)
        
    def all_gens_done(self):
        return len(self.get_all_ongoing_jobs()) == 0
    
    def get_all_done_jobs(self):
        jobs = []
        for job in self.jobs:
            if job.status != JobStatus.DONE:
                continue
            jobs.append(job)
        return(jobs)

    def is_faulted(self):
        faulted = 0
        for job in self.jobs:
            if job.status == JobStatus.FAULTED:
                faulted += 1
        return len(self.jobs) == faulted

    def is_censored(self):
        censored = 0
        for job in self.jobs:
            if job.status == JobStatus.CENSORED:
                censored += 1
        return len(self.jobs) == censored

    def is_possible(self):
        count = 0
        for job in self.jobs:
            if not job.is_possible:
                count += 1
        return len(self.jobs) != count

    def get_all_ongoing_jobs(self):
        jobs = []
        for job in self.jobs:
            if job.status in [JobStatus.FAULTED, JobStatus.DONE, JobStatus.CENSORED]:
                continue
            jobs.append(job)
        return(jobs)

    def get_all_filenames(self):
        filenames = []
        for job in self.get_all_done_jobs():
            filenames += job.filenames
        return(filenames)

    def get_all_seeds(self):
        seeds = []
        for job in self.get_all_done_jobs():
            seeds += job.seeds
        return(seeds)

    def get_all_images(self):
        imgs = []
        for job in self.get_all_done_jobs():
            imgs += job.imgs
        return(imgs)


class HordeGenerate:

    def __init__(self, submit_dict, unique_id, asynchronous=False):
        self.submit_dict = submit_dict
        self.prompt = submit_dict["prompt"]
        self.unique_id = unique_id
        self.status = JobStatus.INIT
        self.headers = {
            "apikey": os.environ['HORDE_API'],
            "Client-Agent": "db0_fediverse_bot:2.0.0:(discord)db0#1625"
        }
        self.filenames = []
        self.seeds = []
        self.imgs = []
        self.img_ids = []
        self.thread = None
        self.is_possible = True
        self.req_id = None
        if asynchronous:
            self.thread = threading.Thread(target=self.generate_image, args=())
            self.thread.daemon = True
            self.thread.start()
        else:
            self.generate_image()
            

    def generate_image(self):
        logger.debug(f"Submitting: {self.submit_dict}")
        self.status = JobStatus.WORKING
        for attempt in range(5):
            try:
                submit_req = requests.post(f'{HORDE_URL}/api/v2/generate/async', json = self.submit_dict, headers = self.headers)
            except Exception as err:
                logger.warning(f"Exception on submit: {err}")
                self.status = JobStatus.FAULTED
                return
            if not submit_req.ok:
                try:
                    submit_results = submit_req.json()
                except:
                    logger.warning(f"Unexpected error code on submit: {submit_req.status_code}: {submit_req.text}")
                    self.status = JobStatus.FAULTED
                    return
                if "message" in submit_results and submit_results["message"] == "2 per 1 second":
                    logger.debug(f"Hit 2 per 1s rate limit. Try {attempt+1}/5")
                    time.sleep(1)
                    continue
                logger.warning(f"Unexpected error code on submit: {submit_req.status_code}: {submit_req.text}")
                self.status = JobStatus.FAULTED
                return
            break
        submit_results = submit_req.json()
        # logger.debug(submit_results)
        self.req_id = submit_results['id']
        is_done = False
        retry = 0
        while not is_done:
            retry += 1
            try:
                chk_req = requests.get(f'{HORDE_URL}/api/v2/generate/check/{self.req_id}')
            except Exception:
                self.status = JobStatus.FAULTED
                return
            if not chk_req.ok:
                logger.error(chk_req.text)
                self.status = JobStatus.FAULTED
                return
            if retry >= 300: 
                logger.error("Image failed to return in a reasonable amount of time. Aborting")
                self.status = JobStatus.FAULTED
                self.is_possible = False
                return
            chk_results = chk_req.json()
            logger.debug([self.unique_id, self.submit_dict.get("models"), chk_results])
            is_done = chk_results['done']
            is_faulted = chk_results['faulted']
            self.is_possible = chk_results['is_possible']
            if is_faulted or not self.is_possible:
                self.status = JobStatus.FAULTED
                return
            time.sleep(0.8)
        try:
            retrieve_req = requests.get(f'{HORDE_URL}/api/v2/generate/status/{self.req_id}')
        except Exception:
            self.status = JobStatus.FAULTED
            return
        if not retrieve_req.ok:
            logger.error(retrieve_req.text)
            self.status = JobStatus.FAULTED
            return
        results_json = retrieve_req.json()
        # logger.debug(results_json)
        if results_json['faulted']:
            logger.error(f"Something went wrong when generating the request")
            self.status = JobStatus.FAULTED
            return
        results = results_json['generations']
        censored_count = 0
        faulted_count = 0
        for iter in range(len(results)):
            if results[iter]["censored"]:
                logger.info("Image received censored")
                censored_count += 1
                if censored_count + faulted_count == len(results):
                    self.status = JobStatus.CENSORED
                    return
                continue
            try:
                img_bytes = requests.get(results[iter]["img"]).content
            except MissingSchema as e:
                b64img = results[iter]["img"]
                base64_bytes = b64img.encode('utf-8')
                img_bytes = base64.b64decode(base64_bytes)
            try:
                img = Image.open(BytesIO(img_bytes))
                self.imgs.append(img)
                self.img_ids.append(results[iter]["id"])
            except Exception:
                logger.error("Error reading image data")
                faulted_count += 1
                if faulted_count + censored_count == len(results):
                    self.status = JobStatus.FAULTED
                    return
                continue
            filename = f"{self.unique_id}_{iter}_horde_generation.jpg"
            self.filenames.append(filename)
            self.seeds.append(results[iter]["seed"])
            img.save(filename)
            logger.debug(f"Saved: {filename}")
        self.status = JobStatus.DONE
