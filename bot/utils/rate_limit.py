"""
محدودکننده‌ی نرخ (Rate Limiter) ساده و درون‌حافظه‌ای.

برای مقیاس فعلی (یک instance، چند صد کاربر) همین کافی است و نیازی به Redis نیست.
نکته‌ها:
- وضعیت فقط در حافظه‌ی همین process نگه داشته می‌شود؛ با ری‌استارت/دیپلوی صفر می‌شود.
  برای جلوگیری از اسپم عادی کافی است. اگر روزی چند instance شدید، باید به جای حافظه از
  دیتابیس یا Redis استفاده شود.
- check() هیچ await ندارد، پس در event loop تک‌ریسمانی ربات اتمیک است.

الگوی استفاده:
    decision = limiter.check(user_id)
    if not decision.allowed:
        if decision.notify:            # فقط بار اول هر دوره‌ی مسدودی پیام بده، نه برای هر اسپم
            await update.message.reply_text(f"... {format_wait(decision.retry_after)} ...")
        return
"""
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Hashable

_CLEANUP_THRESHOLD = 2000  # اگر تعداد کلیدها از این بیشتر شد، کلیدهای منقضی پاک می‌شوند


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after: int = 0  # ثانیه‌ی باقی‌مانده تا مجاز شدن (فقط وقتی allowed=False)
    notify: bool = False  # آیا الان باید به کاربر پیام «صبر کنید» داد؟ (یک‌بار در هر دوره‌ی مسدودی)


class _KeyState:
    __slots__ = ("events", "notified")

    def __init__(self, max_events: int) -> None:
        self.events: Deque[float] = deque(maxlen=max_events)
        self.notified = False


class RateLimiter:
    """
    max_events در هر window_seconds ثانیه مجاز است، و (اختیاری) بین دو رویداد پشت‌سرهم
    حداقل min_interval ثانیه فاصله باشد. هر check موفق یک رویداد ثبت می‌کند.
    """

    def __init__(
        self,
        *,
        max_events: int,
        window_seconds: float,
        min_interval: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_events < 1 or window_seconds <= 0:
            raise ValueError("max_events و window_seconds باید مثبت باشند")
        self.max_events = max_events
        self.window = window_seconds
        self.min_interval = min_interval
        self._clock = clock
        self._state: Dict[Hashable, _KeyState] = {}

    def check(self, key: Hashable) -> RateDecision:
        now = self._clock()
        state = self._state.get(key)
        if state is None:
            if len(self._state) >= _CLEANUP_THRESHOLD:
                self._cleanup(now)
            state = self._state[key] = _KeyState(self.max_events)

        events = state.events
        while events and now - events[0] >= self.window:
            events.popleft()

        wait = 0.0
        if self.min_interval and events:
            wait = max(wait, self.min_interval - (now - events[-1]))
        if len(events) >= self.max_events:
            wait = max(wait, self.window - (now - events[0]))

        if wait > 0:
            notify = not state.notified
            state.notified = True
            return RateDecision(allowed=False, retry_after=max(1, math.ceil(wait)), notify=notify)

        events.append(now)
        state.notified = False
        return RateDecision(allowed=True)

    def _cleanup(self, now: float) -> None:
        stale = [k for k, st in self._state.items() if not st.events or now - st.events[-1] >= self.window]
        for k in stale:
            del self._state[k]


def format_wait(seconds: int) -> str:
    """۴۵ → «۴۵ ثانیه»، ۱۲۰ → «۲ دقیقه» (به بالا گرد می‌شود)."""
    if seconds < 60:
        return f"{seconds} ثانیه"
    return f"{math.ceil(seconds / 60)} دقیقه"


# --- محدودکننده‌های پروژه (کلید = آیدی عددی تلگرام کاربر) ---

# «ارتباط با ادمین»: حداقل ۳۰ ثانیه بین دو پیام و حداکثر ۱۰ پیام در ساعت
contact_limiter = RateLimiter(max_events=10, window_seconds=3600, min_interval=30)

# ارسال فایل فیش: حداکثر ۶ فایل در دقیقه (چه معتبر چه نامعتبر)
receipt_limiter = RateLimiter(max_events=6, window_seconds=60)
