import asyncio
import logging
import subprocess
import time

import redis.asyncio as redis
import uvicorn
from fastapi import Depends, FastAPI, File, UploadFile, Form, HTTPException
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from pydantic import BaseModel
from PIL import Image 
import random
# from BASEER import Baseer

from config import settings

app = FastAPI(dependencies=[Depends(RateLimiter(times=1, seconds=5))])
logger = logging.getLogger(__name__)
# .env variables can be validated and accessed from the config, here to set a log level
logging.basicConfig(level=settings.LOG_LEVEL.upper())


class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str

# TODO: Create a control panel for the admin to change these values and save them in the database
MAX_IMAGE_WIDTH = 1024
MAX_IMAGE_HEIGHT = 1024

MIN_IMAGE_WIDTH = 256
MIN_IMAGE_HEIGHT = 256

def image_validation(file: UploadFile):
    # PIL Image validation
    try:
        image = Image.open(file.file)
        image.verify()
    except:
        return "The image seems corrupted or unsupported."
    
    # Max size validation
    if image.width > MAX_IMAGE_WIDTH and image.height > MAX_IMAGE_HEIGHT:
        return "The given image exceeds the allowed size ("+str(MAX_IMAGE_HEIGHT)+"×"+str(MAX_IMAGE_WIDTH)+")."
    if image.width < MIN_IMAGE_WIDTH or image.height < MIN_IMAGE_HEIGHT:
        return "The given image is smaller than the allowed size ("+str(MIN_IMAGE_HEIGHT)+"×"+str(MIN_IMAGE_WIDTH)+")."
    
    return True

@app.get("/")
def root():
    # endpoints can be marked as `async def` if they do async work, otherwise use `def`
    # which will make the request run on a thread "awaited"
    return {"message":"Welcome to BASEER API. To use the API send an image to '/predict' POST endpoint"}


@app.get("/specs")
def specs():
    return {"max_width": MAX_IMAGE_WIDTH, "max_height": MAX_IMAGE_HEIGHT, "accepted_formats": ["jpg", "png"]}

@app.post("/predict")
def predict(file: UploadFile = File(None), is_dummy: bool = Form(False)):

    is_dummy = bool(is_dummy)
    if is_dummy:
        dummy_captions = [ "صورة لحصان يركض على الشاطئ", "رجلان يرتديان شماغ يتصافحان", "خيمة في وسط الرمال وسيارات حولها", "مناظر خلابة لجبال الألب في سويسرا","غروب الشمس الرائع في صحراء دبي","زهرة الفراولة الحمراء في حقل خضراء","صورة فوتوغرافية لمسجد الشيخ زايد في أبوظبي","طيور البطريق القطبية في جنوب القطب الجنوبي","مناظر خلابة للشلالات الطبيعية في فيكتوريا","غروب الشمس في البحر الأحمر","صورة فوتوغرافية لقصر الحمراء في غرناطة","تفاح أحمر وجوافة حمراء على طاولة خشبية","ربيع السويداء السورية وأشجار الزيتون الخضراء"]

        # return a random dummy caption 
        return {"prediction": random.choice(dummy_captions),"image_validation": image_validation(file)}

    if file.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(status_code=415, detail="Unsupported file given.")
    
    image_val = image_validation(file)
    if(image_val != True):
        raise HTTPException(status_code=415, detail=image_val)        

    return HTTPException(status_code=501, detail=f"This feature is under development.")
    # return {"prediction": prediction}

# @app.get("/user", response_model=UserResponse)
# def current_user():
#     # this endpoint's repsonse will match the UserResponse model
#     return {
#         "user_id": "0123456789",
#         "email": "me@kylegill.com",
#         "name": "Kyle Gill",
#         "extra_field_ignored_by_model": "This field is ignored by the response model",
#     }


# @app.get("/cached", response_model=UserResponse)
# @cache(expire=30)  # cache for 30 seconds
# async def cached():
#     # for demonstration purposes, this is a slow endpoint that waits 5 seconds
#     await asyncio.sleep(5)
#     return {
#         "user_id": "0123456789",
#         "email": "cached@kylegill.com",
#         "name": "Kyle Gill",
#     }


@app.on_event("startup")
async def startup():
    redis_url = f"redis://{settings.REDISUSER}:{settings.REDISPASSWORD}@{settings.REDISHOST}:{settings.REDISPORT}"
    try:
        red = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await FastAPILimiter.init(red)
    except Exception:
        raise Exception(
            "Redis connection failed, ensure redis is running on the default port 6379"
        )

    FastAPICache.init(RedisBackend(red), prefix="fastapi-cache")


@app.middleware("http")
async def time_request(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["Server-Timing"] = str(process_time)
    logger.info(f"{request.method} {round(process_time, 5)}s {request.url}")
    return response


def dev():
    try:
        subprocess.check_output(["redis-cli", "ping"], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        logger.warning(
            "Redis is not already running, have you started it with redis-server?"
        )
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
