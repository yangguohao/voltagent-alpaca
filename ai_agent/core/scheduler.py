"""Market-day scheduler: wake at premarket, sleep after postmarket."""

from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

from ai_agent.config.settings import Settings
from ai_agent.core.agent import TradingAgent
from ai_agent.observability.logger import get_logger

logger = get_logger("scheduler")


def _run_async(coro):
    asyncio.run(coro)


def _tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.market_timezone)


def _now(settings: Settings) -> datetime:
    return datetime.now(_tz(settings))


def _premarket_time(settings: Settings) -> dt_time:
    return dt_time(settings.premarket_hour, settings.premarket_minute)


def _postmarket_time(settings: Settings) -> dt_time:
    return dt_time(settings.postmarket_hour, settings.postmarket_minute)


def _intraday_end_time(settings: Settings) -> dt_time:
    return dt_time(settings.intraday_end_hour, settings.intraday_end_minute)


def _is_weekday(day: date) -> bool:
    return day.weekday() < 5


def _combine(day: date, clock: dt_time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, clock, tzinfo=tz)


def _next_trading_day_premarket(now: datetime, settings: Settings) -> datetime:
    tz = now.tzinfo or _tz(settings)
    candidate = _combine(now.date(), _premarket_time(settings), tz)
    if now >= candidate:
        candidate += timedelta(days=1)
    while not _is_weekday(candidate.date()):
        candidate += timedelta(days=1)
    return candidate


def _in_trading_window(now: datetime, settings: Settings) -> bool:
    if not _is_weekday(now.date()):
        return False
    current = now.time()
    return _premarket_time(settings) <= current <= _postmarket_time(settings)


def _sleep_until(target: datetime) -> None:
    while True:
        remaining = (target - datetime.now(target.tzinfo)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 60))


def _next_intraday_slot(now: datetime, interval_minutes: int) -> datetime:
    minute = ((now.minute // interval_minutes) + 1) * interval_minutes
    hour = now.hour
    if minute >= 60:
        minute = 0
        hour += 1
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


async def _run_intraday_loop(agent: TradingAgent, settings: Settings) -> None:
    tz = _tz(settings)
    end_time = _intraday_end_time(settings)
    premarket = _premarket_time(settings)
    interval = settings.intraday_interval_minutes

    while True:
        now = datetime.now(tz)
        if now.time() > end_time:
            break
        if now.time() >= premarket:
            await agent.run_intraday_cycle()

        now = datetime.now(tz)
        if now.time() > end_time:
            break

        next_run = _next_intraday_slot(now, interval)
        if next_run.time() > end_time:
            break

        sleep_s = (next_run - now).total_seconds()
        if sleep_s > 0:
            logger.info("Next intraday cycle at %s (sleep %.0fs)", next_run.strftime("%H:%M"), sleep_s)
            await asyncio.sleep(sleep_s)


async def _run_trading_day(agent: TradingAgent, settings: Settings) -> None:
    tz = _tz(settings)
    now = datetime.now(tz)
    logger.info("=== Trading day %s ===", now.date())

    await agent.run_premarket()
    await _run_intraday_loop(agent, settings)

    postmarket_at = _combine(now.date(), _postmarket_time(settings), tz)
    now = datetime.now(tz)
    if now < postmarket_at:
        logger.info("Waiting for postmarket at %s", postmarket_at.strftime("%H:%M %Z"))
        _sleep_until(postmarket_at)

    await agent.run_postmarket()
    logger.info("=== Trading day complete ===")


def run_daemon(agent: TradingAgent, settings: Settings) -> None:
    """Run forever: sleep outside market hours, trade during the session."""
    logger.info(
        "Daemon started (tz=%s, premarket=%02d:%02d, postmarket=%02d:%02d, intraday every %d min)",
        settings.market_timezone,
        settings.premarket_hour,
        settings.premarket_minute,
        settings.postmarket_hour,
        settings.postmarket_minute,
        settings.intraday_interval_minutes,
    )

    while True:
        now = _now(settings)
        if not _in_trading_window(now, settings):
            wake_at = _next_trading_day_premarket(now, settings)
            logger.info("Outside trading window — sleeping until %s", wake_at.isoformat())
            _sleep_until(wake_at)
            continue

        _run_async(_run_trading_day(agent, settings))

        wake_at = _next_trading_day_premarket(_now(settings), settings)
        logger.info("Session finished — sleeping until %s", wake_at.isoformat())
        _sleep_until(wake_at)


def create_scheduler(agent: TradingAgent, settings: Settings):
    """Legacy cron scheduler (kept for compatibility). Prefer run_daemon()."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler(timezone=settings.market_timezone)

    scheduler.add_job(
        lambda: _run_async(agent.run_premarket()),
        CronTrigger(hour=settings.premarket_hour, minute=settings.premarket_minute, timezone=settings.market_timezone),
        id="premarket",
        name="Premarket analysis",
    )
    scheduler.add_job(
        lambda: _run_async(agent.run_intraday_cycle()),
        CronTrigger(
            hour=f"{settings.premarket_hour}-{settings.intraday_end_hour}",
            minute=f"*/{settings.intraday_interval_minutes}",
            timezone=settings.market_timezone,
        ),
        id="intraday",
        name="Intraday cycle",
    )
    scheduler.add_job(
        lambda: _run_async(agent.run_postmarket()),
        CronTrigger(hour=settings.postmarket_hour, minute=settings.postmarket_minute, timezone=settings.market_timezone),
        id="postmarket",
        name="Postmarket sync",
    )
    return scheduler
