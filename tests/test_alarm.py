"""Session alert logic: when the tile flashes and what a click does."""

import time
from datetime import datetime

import pytest

from core import alarm

# 14:00:00 local time on an ordinary day.
NOW = time.mktime((2026, 10, 7, 14, 0, 0, 0, 0, -1))
END = NOW + 50 * 60   # 14:50
WARN = END - 5 * 60   # 14:45


def hm(stamp):
    moment = datetime.fromtimestamp(stamp)
    return (moment.hour, moment.minute, moment.second)


class TestEndTime:
    def test_later_today(self):
        end = alarm.next_occurrence(14, 50, NOW)
        assert end == END and hm(end) == (14, 50, 0)

    def test_a_time_already_past_means_tomorrow(self):
        end = alarm.next_occurrence(9, 0, NOW)
        assert hm(end) == (9, 0, 0)
        assert 18 * 3600 < end - NOW < 20 * 3600

    def test_this_very_minute_means_tomorrow_not_now(self):
        assert alarm.next_occurrence(14, 0, NOW + 20) > NOW + 23 * 3600

    def test_default_is_the_next_fifty_past(self):
        assert hm(alarm.default_end(50, NOW)) == (14, 50, 0)
        assert hm(alarm.default_end(50, NOW + 55 * 60)) == (15, 50, 0)

    def test_default_is_never_only_moments_away(self):
        # 14:47: offering 14:50 would be useless; offer 15:50.
        assert hm(alarm.default_end(50, NOW + 47 * 60)) == (15, 50, 0)

    def test_default_follows_the_minute_last_used(self):
        assert hm(alarm.default_end(20, NOW)) == (14, 20, 0)
        assert hm(alarm.default_end(0, NOW)) == (15, 0, 0)


class TestSequence:
    def test_idle_then_warning_then_ended(self):
        a = alarm.arm(END, 5, NOW)
        assert alarm.phase(a, WARN - 1) == alarm.IDLE
        assert alarm.phase(a, WARN) == alarm.WARNING
        assert alarm.phase(a, END - 1) == alarm.WARNING
        assert alarm.phase(a, END) == alarm.ENDED

    def test_no_alarm_never_flashes(self):
        assert alarm.phase(None, NOW) == alarm.IDLE
        assert alarm.flashing(None, NOW) is None
        assert alarm.acknowledge(None, NOW) is None

    def test_flashes_from_the_warning_until_clicked(self):
        a = alarm.arm(END, 5, NOW)
        assert alarm.flashing(a, WARN - 1) is None
        assert alarm.flashing(a, WARN) == alarm.WARNING
        a = alarm.acknowledge(a, WARN + 10)
        assert a is not None and a.warn_acked
        assert alarm.flashing(a, WARN + 11) is None
        assert alarm.flashing(a, END - 1) is None

    def test_flashes_again_at_the_end_until_clicked(self):
        a = alarm.acknowledge(alarm.arm(END, 5, NOW), WARN)
        assert alarm.flashing(a, END) == alarm.ENDED
        assert alarm.acknowledge(a, END + 5) is None  # finished

    def test_unanswered_warning_becomes_the_end_flash(self):
        a = alarm.arm(END, 5, NOW)
        assert alarm.flashing(a, END - 1) == alarm.WARNING
        assert alarm.flashing(a, END) == alarm.ENDED

    def test_a_click_while_quiet_changes_nothing(self):
        a = alarm.arm(END, 5, NOW)
        assert alarm.acknowledge(a, NOW + 60) == a

    def test_zero_warning_skips_straight_to_the_end(self):
        a = alarm.arm(END, 0, NOW)
        assert alarm.flashing(a, END - 1) is None
        assert alarm.flashing(a, END) == alarm.ENDED

    @pytest.mark.parametrize("minutes", [1, 2, 3, 4, 5])
    def test_each_warning_length_starts_on_time(self, minutes):
        a = alarm.arm(END, minutes, NOW)
        assert alarm.flashing(a, END - 60 * minutes - 1) is None
        assert alarm.flashing(a, END - 60 * minutes) == alarm.WARNING

    def test_warning_is_kept_between_zero_and_five(self):
        assert alarm.arm(END, 12, NOW).warn_minutes == 5
        assert alarm.arm(END, -3, NOW).warn_minutes == 0

    def test_set_inside_the_warning_window_does_not_flash_at_once(self):
        a = alarm.arm(END, 5, END - 180)  # three minutes to go
        assert a.warn_acked
        assert alarm.flashing(a, END - 170) is None
        assert alarm.flashing(a, END) == alarm.ENDED

    def test_end_flash_gives_up_after_the_limit(self):
        a = alarm.arm(END, 5, NOW)
        assert alarm.flashing(a, END + alarm.END_FLASH_LIMIT - 1) == alarm.ENDED
        assert not alarm.is_spent(a, END + alarm.END_FLASH_LIMIT - 1)
        assert alarm.flashing(a, END + alarm.END_FLASH_LIMIT) is None
        assert alarm.is_spent(a, END + alarm.END_FLASH_LIMIT)

    def test_flash_alternates_by_the_second(self):
        assert alarm.flash_on(1000.0) and alarm.flash_on(1000.9)
        assert not alarm.flash_on(1001.0)
        assert alarm.flash_on(1002.0)


class TestDescribe:
    def test_twelve_and_twenty_four_hour(self):
        a = alarm.arm(END, 5, NOW)
        assert alarm.describe(a, NOW, twenty_four=False) == "2:50, 5 min warning"
        assert alarm.describe(a, NOW, twenty_four=True) == "14:50, 5 min warning"

    def test_no_warning(self):
        assert alarm.describe(alarm.arm(END, 0, NOW), NOW, False) == "2:50, no warning"

    def test_tomorrow_is_said_out_loud(self):
        # A mistyped (already past) end time arms for tomorrow; the menu says so.
        a = alarm.arm(alarm.next_occurrence(9, 0, NOW), 5, NOW)
        assert alarm.describe(a, NOW, False) == "9:00 tomorrow, 5 min warning"
