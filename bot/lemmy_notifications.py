import os
import json
from bot.horde import HordeMultiGen, JobStatus
from bot.lemmy_ctrl import lemmy, lemmy_image_community_id
from bot.style import Styling
from bot.exceptions import HordeBotReplyException, HordeBotException
from bot.logger import logger

class LemmyMentionHandler:

    def __init__(self, mention):
        self.status = JobStatus.INIT
        self.mention = mention
        self.mention_id = self.mention['person_mention']['id']
        self.actor_id = self.mention['creator']['actor_id']
        self.comment_id = self.mention['person_mention']['comment_id']
        self.mention_content = self.mention['comment']['content']

    def is_finished(self):
        return self.status in [JobStatus.DONE, JobStatus.FAULTED]

    @logger.catch(reraise=True)
    def handle_notification(self):
        self.handle_mention()

    def handle_mention(self):
        submit_ratings = False # TODO: Add logic to submit ratings to ratings DB when relevant
        self.status = JobStatus.WORKING
        logger.debug(f"Handling mention {self.mention_id}")
        # logger.debug([self.mention_id, last_parsed_notification, self.mention_id < last_parsed_notification])
        try:
            styling = Styling(self.mention_content, self.actor_id)
            gen: HordeMultiGen = styling.request_images(self.mention_id)
        except HordeBotReplyException as err:
            self.reply_faulted(err.reply)
            return
        except HordeBotException:
            logger.info(f"{self.comment_id} is not a generation request, skipping")
            lemmy.mention.mark_as_read(self.mention_id, True)
            self.status = JobStatus.DONE
            return
        media_dicts = []
        image_body = ''
        done_jobs = gen.get_all_done_jobs()
        for job in done_jobs:
            for iter_fn in range(len(job.filenames)):
                logger.debug(f"Uploading {job.filenames[iter_fn]}...")
                for iter in range(3):
                    try:
                        image_data = lemmy.image.upload(
                            image=job.filenames[iter_fn],
                        )[0]
                        media_dicts.append(image_data)
                        image_body += f"![Image with seed {job.seeds[iter_fn]} generated via AI Horde through @aihorde@lemmy.dbzer0.com. Prompt: {job.prompt}]({image_data['image_url']})"
                        break
                    except Exception as err:
                        # If a file fails, we skip it
                        if iter >= 2:
                            continue
                        logger.warning(f"Error '{err}' when uploading files. Retry {iter+1}/3")                
                logger.debug(f"Uploaded {job.filenames[iter_fn]}")
        if len(media_dicts) == 0:
            self.reply_faulted("Something went wrong when trying to fulfil your request. Please try again later")
            self.cleanup_files(gen)
            return
        if self.actor_id not in json.loads(os.getenv("CROSSPOST_IGNORE_LIST")):            
            logger.info(f"Posting to Bot Art")
            post_result = lemmy.post(
                community_id=lemmy_image_community_id,
                name=f"{styling.style}: {styling.prompt}"[0:200],
                url=media_dicts[0]["image_url"],
                body=f"Prompt: {styling.prompt}\n\nStyle: {styling.style}\n\n{image_body}"
            )
            if not post_result:
                self.reply_faulted("Failed to upload generated images to Lemmy. Please try again later")
                self.cleanup_files(gen)
                return
        post_stub = post_result['post_view']['post']['ap_id'].split('//')[1]
        post_url = f"https://lemmyverse.link/{post_stub}"
        comment_body = (
            f"[Here are some images]({post_url}) matching your request\n\n"
            f"Prompt: {styling.prompt}\n\n"
            f"Style: {styling.style}\n\n"
            f"{image_body}"
        )
        logger.info(f"replying to {self.comment_id}: {self.mention_content}")
        for iter in range(4):
            try:
                lemmy.comment.create(
                    post_id = self.mention['comment']['post_id'], 
                    content = comment_body, 
                    parent_id = self.comment_id, 
                    )                
                break
            except Exception as err:
                if iter >= 3:
                    self.reply_faulted("Something went wrong when trying to fulfil your request. Please try again later")
                    self.cleanup_files(gen)
                    return
                logger.warning(f"Network error when replying. Retry {iter+1}/3")
        self.cleanup_files(gen)
        lemmy.mention.mark_as_read(self.mention_id, True)
        self.status = JobStatus.DONE

    def cleanup_files(self,gen):
        for fn in gen.get_all_filenames():
            os.remove(fn)


    def handle_dm(self):
        logger.debug(f"Handling notification {self.mention_id} as a DM")
        lemmy.mention.mark_as_read(self.mention_id, True)
        self.status = JobStatus.DONE

    def set_faulted(self):
        self.status = JobStatus.FAULTED
        lemmy.mention.mark_as_read(self.mention_id, True)

    def reply_faulted(self,message):
        self.set_faulted()
        lemmy.comment.create(
            post_id = self.mention['comment']['post_id'], 
            content = message, 
            parent_id = self.comment_id, 
        )