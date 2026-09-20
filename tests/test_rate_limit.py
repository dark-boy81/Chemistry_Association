"""
تست‌های واحد محدودکننده‌ی نرخ (bot/utils/rate_limit.py) با ساعت ساختگی.

اجرا:  python -m unittest discover -s tests -v
"""
import unittest

from bot.utils.rate_limit import RateLimiter, format_wait


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def test_min_interval(self):
        rl = RateLimiter(max_events=10, window_seconds=3600, min_interval=30, clock=self.clock)
        self.assertTrue(rl.check("u").allowed)
        self.clock.advance(10)
        d = rl.check("u")
        self.assertFalse(d.allowed)
        self.assertEqual(d.retry_after, 20)
        self.clock.advance(20)
        self.assertTrue(rl.check("u").allowed)

    def test_window_cap(self):
        rl = RateLimiter(max_events=3, window_seconds=60, clock=self.clock)
        for _ in range(3):
            self.assertTrue(rl.check("u").allowed)
            self.clock.advance(1)
        d = rl.check("u")
        self.assertFalse(d.allowed)
        self.assertEqual(d.retry_after, 57)  # اولین رویداد ۳ ثانیه پیش بوده
        self.clock.advance(57)
        self.assertTrue(rl.check("u").allowed)

    def test_notify_only_once_per_block(self):
        rl = RateLimiter(max_events=1, window_seconds=60, clock=self.clock)
        self.assertTrue(rl.check("u").allowed)
        first = rl.check("u")
        second = rl.check("u")
        self.assertTrue(first.notify)
        self.assertFalse(second.notify)  # اسپم بعدی بی‌صدا نادیده گرفته می‌شود
        self.clock.advance(60)
        self.assertTrue(rl.check("u").allowed)  # بعد از مجاز شدن، دوره‌ی جدید
        self.assertTrue(rl.check("u").notify)  # مسدودی بعدی دوباره یک‌بار اطلاع می‌دهد

    def test_keys_are_independent(self):
        rl = RateLimiter(max_events=1, window_seconds=60, clock=self.clock)
        self.assertTrue(rl.check("a").allowed)
        self.assertFalse(rl.check("a").allowed)
        self.assertTrue(rl.check("b").allowed)

    def test_blocked_attempts_do_not_extend_the_block(self):
        rl = RateLimiter(max_events=1, window_seconds=60, clock=self.clock)
        rl.check("u")
        for _ in range(20):
            self.clock.advance(2)
            rl.check("u")  # اسپم مداوم
        self.clock.advance(20)  # جمعاً ۶۰ ثانیه از رویداد مجاز اول
        self.assertTrue(rl.check("u").allowed)

    def test_cleanup_removes_stale_keys(self):
        rl = RateLimiter(max_events=1, window_seconds=60, clock=self.clock)
        for i in range(2100):
            rl.check(i)
        self.clock.advance(61)
        rl.check("new")  # با عبور از آستانه، کلیدهای منقضی پاک می‌شوند
        self.assertLess(len(rl._state), 100)

    def test_format_wait(self):
        self.assertEqual(format_wait(45), "45 ثانیه")
        self.assertEqual(format_wait(60), "1 دقیقه")
        self.assertEqual(format_wait(61), "2 دقیقه")


if __name__ == "__main__":
    unittest.main()
