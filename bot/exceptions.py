class HordeBotException(Exception):
    pass

class HordeBotReplyException(HordeBotException):
    reply: str

class ModelNotServed(HordeBotReplyException):
    reply = "Unfortunately it appears all models in this category are currently not being served. Please select another cateogory"

class UnknownStyle(HordeBotReplyException):
    reply = "We could not discover this style in our database. Please pick one from [styles](https://github.com/amiantos/AI-Horde-Styles-Previews/blob/main/previews.md) or [categories](https://github.com/db0/Stable-Horde-Styles/blob/main/categories.json)"

class CurrentlyImpossible(HordeBotReplyException):
    reply = "It is not possible to fulfil this request using this style at the moment. Please select a different style and try again."

class UnknownError(HordeBotReplyException):
    reply = "Something went wrong when trying to fulfil your request. Please try again later"

class AllCensored(HordeBotReplyException):
    reply = "Unfortunately all images from this request were censored by the automatic safety filer. Please tweak your prompt to avoid nsfw terms and try again."

class NotValidRequest(HordeBotReplyException):
    reply = "This is not a valid request."
