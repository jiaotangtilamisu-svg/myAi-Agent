"""Supervisor routing metadata and report cache; specialist memories use separate keys."""

import json
import uuid

from app.auth.agent_context import require_agent_user
from app.services.redis_service import redis_service

TTL = 3600


def key(user):
    require_agent_user(user)
    return "mall:agent:supervisor:" + user


async def acquire(user):
    token = uuid.uuid4().hex
    if not await redis_service.client.set(key(user) + ":lock", token, ex=300, nx=True):
        raise ValueError("SUPERVISOR_BUSY")
    return token


async def load(user):
    raw = await redis_service.client.get(key(user) + ":routing")
    value = json.loads(raw) if raw else {}
    return {"lastRoute": value.get("lastRoute")} if isinstance(value, dict) else {}


async def save(user, token, message, context, report):
    base = key(user)
    payload = json.dumps(report, ensure_ascii=False, allow_nan=False)
    if len(payload.encode()) > 512 * 1024:
        raise ValueError("Supervisor report exceeds bound")
    code = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[4])
redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4])
return 1
"""
    if not await redis_service.client.eval(
        code,
        3,
        base + ":lock",
        base + ":routing",
        base + ":result:" + str(message),
        token,
        json.dumps(context),
        payload,
        TTL,
    ):
        raise ValueError("Supervisor lease expired")


async def release(user, token):
    await redis_service.client.eval(
        "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0",
        1,
        key(user) + ":lock",
        token,
    )


async def result(user, message):
    if type(message) is not int or message < 1:
        raise ValueError("Invalid message identifier")
    raw = await redis_service.client.get(key(user) + ":result:" + str(message))
    return json.loads(raw) if raw else None


def hint_key(user):
    require_agent_user(user)
    return "mall:agent:aftersales:supervisor:" + user


async def hint(user):
    raw = await redis_service.client.get(hint_key(user))
    value = json.loads(raw) if raw else {}
    return {
        k: v
        for k, v in value.items()
        if k in {"orderId", "policyQuery", "kind", "businessIntent"} and isinstance(v, str)
    }


async def save_hint(user, value):
    await redis_service.client.setex(
        hint_key(user), TTL, json.dumps(value, ensure_ascii=False)
    )
