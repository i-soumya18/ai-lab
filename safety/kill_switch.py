"""Redis-backed kill switch for the AI Lab Goal OS.

Setting the kill switch causes all running GoalExecutor loops to abort
at their next step boundary. Maximum latency = one agent timeout (120 s).

Usage:
    from safety.kill_switch import activate, deactivate, is_killed

    await activate(redis)      # halt all goals
    await deactivate(redis)    # resume
    killed = await is_killed(redis)
"""
from __future__ import annotations

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger()

KILL_SWITCH_KEY = "system:killswitch"


async def activate(redis: Redis) -> None:
    """Activate the kill switch — all running goals will abort at their next check."""
    await redis.set(KILL_SWITCH_KEY, "1")
    logger.warning("kill_switch.activated")


async def deactivate(redis: Redis) -> None:
    """Deactivate the kill switch — goals can run again."""
    await redis.delete(KILL_SWITCH_KEY)
    logger.info("kill_switch.deactivated")


async def is_killed(redis: Redis) -> bool:
    """Return True if the kill switch is currently active.

    Works correctly whether redis was created with decode_responses=True (returns str)
    or decode_responses=False (returns bytes).
    """
    val = await redis.get(KILL_SWITCH_KEY)
    if val is None:
        return False
    # Handle both str and bytes depending on Redis client configuration
    return val in ("1", b"1")
