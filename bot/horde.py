
import requests, json, os, time, base64
import threading
from . import JobStatus, logger
from PIL import Image, ImageFont, ImageDraw, ImageFilter, ImageOps
from io import BytesIO

HORDE_URL = "https://stablehorde.net"

class HordeMultiGen:
    def __init__(self, submit_dicts, unique_id):
        self.submit_dicts = submit_dicts
        self.unique_id = unique_id
        self.status = JobStatus.INIT
        self.jobs = []
        iter = 0
        for submit_dict in self.submit_dicts:
            job_unique_id = str(iter) + '_' + str(self.unique_id)
            self.jobs.append(HordeGenerate(submit_dict, job_unique_id, True))
            iter += 1
        
    def all_gens_done(self):
        return len(self.get_all_ongoing_jobs()) == 0
    
    def get_all_done_jobs(self):
        jobs = []
        for job in self.jobs:
            if job.status != JobStatus.DONE:
                continue
            jobs.append(job)
        return(jobs)

    def get_all_ongoing_jobs(self):
        jobs = []
        for job in self.jobs:
            if job.status in [JobStatus.FAULTED, JobStatus.DONE]:
                continue
            jobs.append(job)
        return(jobs)

    def get_all_filenames(self):
        filenames = []
        for job in self.get_all_done_jobs():
            filenames.append(job.filename)
        return(filenames)

    def get_all_seeds(self):
        seeds = []
        for job in self.get_all_done_jobs():
            seeds.append(job.seed)
        return(seeds)

    def get_all_images(self):
        imgs = []
        for job in self.get_all_done_jobs():
            imgs.append(job.img)
        return(imgs)


class HordeGenerate:

    def __init__(self, submit_dict, unique_id, asynchronous=False):
        self.submit_dict = submit_dict
        self.unique_id = unique_id
        self.status = JobStatus.INIT
        self.headers = {"apikey": os.environ['HORDE_API']}
        self.filename = None
        self.seed = None
        self.img = None
        self.thread = None
        if asynchronous:
            self.thread = threading.Thread(target=self.generate_image, args=())
            self.thread.daemon = True
            self.thread.start()
        else:
            self.generate_image()
            

    def generate_image(self):
        logger.debug(f"Submitting: {self.submit_dict}")
        self.status = JobStatus.WORKING
        try:
            submit_req = requests.post(f'{HORDE_URL}/api/v2/generate/async', json = self.submit_dict, headers = self.headers)
        except Exception:
            self.status = JobStatus.FAULTED
            return
        if not submit_req.ok:
            self.status = JobStatus.FAULTED
            return
        submit_results = submit_req.json()
        # logger.debug(submit_results)
        req_id = submit_results['id']
        is_done = False
        while not is_done:
            try:
                chk_req = requests.get(f'{HORDE_URL}/api/v2/generate/check/{req_id}')
            except Exception:
                self.status = JobStatus.FAULTED
                return
            if not chk_req.ok:
                logger.error(chk_req.text)
                self.status = JobStatus.FAULTED
                return
            chk_results = chk_req.json()
            logger.debug(chk_results)
            is_done = chk_results['done']
            time.sleep(0.8)
        try:
            retrieve_req = requests.get(f'{HORDE_URL}/api/v2/generate/status/{req_id}')
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
            final_submit_dict = request_data.get_submit_dict()
            if "source_image" in final_submit_dict:
                final_submit_dict["source_image"] = f"img2img request with size: {len(final_submit_dict['source_image'])}"
            logger.error(f"Something went wrong when generating the request. Please contact the horde administrator with your request details: {final_submit_dict}")
            self.status = JobStatus.FAULTED
            return
        results = results_json['generations']
        for iter in range(len(results)):
            b64img = results[iter]["img"]
            base64_bytes = b64img.encode('utf-8')
            img_bytes = base64.b64decode(base64_bytes)
            try:
                self.img = Image.open(BytesIO(img_bytes))
            except Exception:
                logger.error("Error reading image data")
                self.status = JobStatus.FAULTED
                return
            self.filename = f"{self.unique_id}_{iter}_horde_generation.jpg"
            self.seed = results[iter]["seed"]
            self.img.save(self.filename)
            # logger.debug(self.filename)        
        self.status = JobStatus.DONE
