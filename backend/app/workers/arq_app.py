from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings
from app.workers.funnel_worker import run_funnel_pipeline_ctx

settings = get_settings()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [run_funnel_pipeline_ctx]
    max_jobs = 10
    job_timeout = 600


async def get_arq_pool():
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))
