"""User-isolated shopping memory; only requirements and measured baselines persist."""

import json
import uuid

from app.auth.agent_context import require_agent_user
from app.services.redis_service import redis_service

TTL = 3600


def key(user_id):
    require_agent_user(user_id)
    return "mall:agent:shopping:" + user_id


async def acquire(user_id):
    base = key(user_id)
    token = uuid.uuid4().hex
    if not await redis_service.client.set(base + ":lock", token, nx=True, ex=120):
        raise ValueError("SHOPPING_BUSY")
    return token


async def load(user_id):
    value = await redis_service.client.get(key(user_id))
    if value is None:
        return {}
    result = json.loads(value)
    if not isinstance(result, dict):
        raise TypeError("Invalid shopping context")
    return result


async def save(user_id, token, message_id, context, result):
    base = key(user_id)
    report = json.dumps(result, ensure_ascii=False)
    if len(report.encode("utf-8")) > 256 * 1024:
        raise ValueError("Shopping result exceeds safe bound")
    script = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[4])
redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4])
return 1
"""
    ok = await redis_service.client.eval(
        script,
        3,
        base + ":lock",
        base,
        base + ":result:" + str(message_id),
        token,
        json.dumps(context, ensure_ascii=False),
        report,
        TTL,
    )
    if not ok:
        raise ValueError("Shopping context lock expired")


async def release(user_id, token):
    script = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0"
    await redis_service.client.eval(script, 1, key(user_id) + ":lock", token)


async def result(user_id, message_id):
    if type(message_id) is not int or message_id < 1:
        raise ValueError("Invalid message identifier")
    raw = await redis_service.client.get(key(user_id) + ":result:" + str(message_id))
    return json.loads(raw) if raw else None
