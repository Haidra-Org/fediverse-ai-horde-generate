
import requests, json, os, time, base64
import threading
from requests.exceptions import MissingSchema
from bot.logger import logger
from bot.enums import JobStatus
from PIL import Image, ImageFont, ImageDraw, ImageFilter, ImageOps
from io import BytesIO
from horde_sdk.ai_horde_api.ai_horde_clients import AIHordeAPISimpleClient
from horde_sdk.ai_horde_api.apimodels import ImageGenerateAsyncRequest, ImageGeneration


HORDE_URL = "https://aihorde.net"

class HordeMultiGen:
    def __init__(self, submit_dicts, unique_id):
        self.submit_dicts = submit_dicts
        self.unique_id = unique_id
        self.status = JobStatus.INIT
        self.jobs = []
        giter = 0
        logger.debug(submit_dicts)
        for submit_dict in self.submit_dicts:
            job_unique_id = str(giter) + '_' + str(self.unique_id)
            self.jobs.append(HordeGenerate(submit_dict, job_unique_id, True))
            giter += 1
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
            "Client-Agent": "db0_mastodon_bot:1.0.0:(discord)db0#1625"
        }
        self.filenames = []
        self.seeds = []
        self.imgs = []
        self.img_ids = []
        self.generations: list[ImageGeneration]
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
        simple_client = AIHordeAPISimpleClient()
        genResults, _ = simple_client.image_generate_request(
            ImageGenerateAsyncRequest(
                apikey='0000000000',
                **self.submit_dict
            ),
        )
        self.generations = genResults.generations
        for giter in range(len(self.generations)):
            if self.generations[giter].censored:
                logger.info("Image received censored")
                self.status = JobStatus.CENSORED
                return
            try:
                img = simple_client.download_image_from_generation(self.generations[giter])
                self.imgs.append(img)
                self.img_ids.append(self.generations[giter].id_)
            except Exception:
                logger.error("Error reading image data")
                self.status = JobStatus.FAULTED
                return
            filename = f"{self.unique_id}_{giter}_horde_generation.jpg"
            self.filenames.append(filename)
            self.seeds.append(self.generations[giter].seed)
            img.save(filename)
            logger.debug(f"Saved: {filename}")
        self.status = JobStatus.DONE
