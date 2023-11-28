import collections.abc
import datetime
import json
import logging
from typing import Final, Any

import httpx
import fastapi
import os

import pydantic
import schedule

logger = logging.getLogger(__name__)

CITY: Final[str] = os.getenv('CITY')
OPENWEATHERMAP_API_KEY: Final[str] = os.getenv('OPENWEATHERMAP_API_KEY')
SERVER_PATH: Final[str] = os.getenv('SERVER_PATH')
app = fastapi.FastAPI(root_path=SERVER_PATH)
route = fastapi.APIRouter()

some_db: dict[str, Any] = {}  # there can be ur DB

geocoding_url = f'http://api.openweathermap.org/geo/1.0/direct?q={CITY}&appid={OPENWEATHERMAP_API_KEY}'


@app.middleware("http")
async def _errors_handling(
        request: fastapi.Request,
        call_next: collections.abc.Callable
) -> fastapi.responses.JSONResponse:
    try:
        return await call_next(request)
    except Exception as exc:
        return fastapi.responses.JSONResponse(status_code=400, content={'reason': str(exc)})


async def _get_geocoding() -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        res = await client.get(url=geocoding_url)
    return json.loads(res.text)


async def _get_lat_lon() -> tuple[str, str]:
    response = await _get_geocoding()
    return response.get('lat'), response.get('lon')


async def _get_temp() -> int | None:
    lat, lon = await _get_lat_lon()
    request_url = f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}'

    async with httpx.AsyncClient() as client:
        res = await client.get(url=request_url)
    response = json.loads(res.text)
    return response.get('main', {}).get('temp', None)


async def _save_temp() -> None:
    if temp := await _get_temp():
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        some_db[current_date] = temp


class Date(pydantic.BaseModel):
    year: str
    month: str
    day: str


class Token(pydantic.BaseModel):
    auth_token = pydantic.Field(min_length=32)


class CheckToken:
    def __call__(self, token: Token) -> None:
        logger.info('token verified')


@route.get(
    path='/get-weather',
    dependencies=[
        fastapi.Depends(CheckToken)
    ]
)
async def get_weather(
        date: Date
) -> fastapi.responses.JSONResponse | None:
    temp = some_db.get(f'{date.year}.{date.month}.{date.day}')
    if temp:
        return fastapi.responses.JSONResponse(content={
            'temp': temp
        })
    return None

app.include_router(route)
app.add_middleware(_errors_handling)
schedule.every().hour.do(_save_temp())  # would be better to delegate it to celery and do it in async way
