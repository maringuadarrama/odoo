# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, datetime
from freezegun import freeze_time
from pytz import timezone, utc

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.addons.resource.models.utils import Intervals, sum_intervals
from odoo.addons.test_resource.tests.common import TestResourceCommon
from odoo.tests.common import TransactionCase


def datetime_tz(year, month, day, hour=0, minute=0, second=0, microsecond=0, tzinfo=None):
    """ Return a `datetime` object with a given timezone (if given). """
    dt = datetime(year, month, day, hour, minute, second, microsecond)
    return timezone(tzinfo).localize(dt) if tzinfo else dt


def datetime_str(year, month, day, hour=0, minute=0, second=0, microsecond=0, tzinfo=None):
    """ Return a fields.Datetime value with the given timezone. """
    dt = datetime(year, month, day, hour, minute, second, microsecond)
    if tzinfo:
        dt = timezone(tzinfo).localize(dt).astimezone(utc)
    return fields.Datetime.to_string(dt)


class TestIntervals(TransactionCase):

    def ints(self, pairs):
        recs = self.env['base']
        return [(a, b, recs) for a, b in pairs]

    def test_union(self):
        def check(a, b):
            a, b = self.ints(a), self.ints(b)
            self.assertEqual(list(Intervals(a)), b)

        check([(1, 2), (3, 4)], [(1, 2), (3, 4)])
        check([(1, 2), (2, 4)], [(1, 4)])
        check([(1, 3), (2, 4)], [(1, 4)])
        check([(1, 4), (2, 3)], [(1, 4)])
        check([(3, 4), (1, 2)], [(1, 2), (3, 4)])
        check([(2, 4), (1, 2)], [(1, 4)])
        check([(2, 4), (1, 3)], [(1, 4)])
        check([(2, 3), (1, 4)], [(1, 4)])

    def test_intersection(self):
        def check(a, b, c):
            a, b, c = self.ints(a), self.ints(b), self.ints(c)
            self.assertEqual(list(Intervals(a) & Intervals(b)), c)

        check([(10, 20)], [(5, 8)], [])
        check([(10, 20)], [(5, 10)], [])
        check([(10, 20)], [(5, 15)], [(10, 15)])
        check([(10, 20)], [(5, 20)], [(10, 20)])
        check([(10, 20)], [(5, 25)], [(10, 20)])
        check([(10, 20)], [(10, 15)], [(10, 15)])
        check([(10, 20)], [(10, 20)], [(10, 20)])
        check([(10, 20)], [(10, 25)], [(10, 20)])
        check([(10, 20)], [(15, 18)], [(15, 18)])
        check([(10, 20)], [(15, 20)], [(15, 20)])
        check([(10, 20)], [(15, 25)], [(15, 20)])
        check([(10, 20)], [(20, 25)], [])
        check(
            [(0, 5), (10, 15), (20, 25), (30, 35)],
            [(6, 7), (9, 12), (13, 17), (22, 23), (24, 40)],
            [(10, 12), (13, 15), (22, 23), (24, 25), (30, 35)],
        )

    def test_difference(self):
        def check(a, b, c):
            a, b, c = self.ints(a), self.ints(b), self.ints(c)
            self.assertEqual(list(Intervals(a) - Intervals(b)), c)

        check([(10, 20)], [(5, 8)], [(10, 20)])
        check([(10, 20)], [(5, 10)], [(10, 20)])
        check([(10, 20)], [(5, 15)], [(15, 20)])
        check([(10, 20)], [(5, 20)], [])
        check([(10, 20)], [(5, 25)], [])
        check([(10, 20)], [(10, 15)], [(15, 20)])
        check([(10, 20)], [(10, 20)], [])
        check([(10, 20)], [(10, 25)], [])
        check([(10, 20)], [(15, 18)], [(10, 15), (18, 20)])
        check([(10, 20)], [(15, 20)], [(10, 15)])
        check([(10, 20)], [(15, 25)], [(10, 15)])
        check([(10, 20)], [(20, 25)], [(10, 20)])
        check(
            [(0, 5), (10, 15), (20, 25), (30, 35)],
            [(6, 7), (9, 12), (13, 17), (22, 23), (24, 40)],
            [(0, 5), (12, 13), (20, 22), (23, 24)],
        )


class TestErrors(TestResourceCommon):
    def setUp(self):
        super(TestErrors, self).setUp()

    def test_create_negative_leave(self):
        # from > to
        with self.assertRaises(ValidationError):
            self.env['resource.calendar.leaves'].create({
                'name': 'error cannot return in the past',
                'resource_id': False,
                'calendar_id': self.calendar_jean.id,
                'date_from': datetime_str(2018, 4, 3, 20, 0, 0, tzinfo=self.jean.tz),
                'date_to': datetime_str(2018, 4, 3, 0, 0, 0, tzinfo=self.jean.tz),
            })

        with self.assertRaises(ValidationError):
            self.env['resource.calendar.leaves'].create({
                'name': 'error caused by timezones',
                'resource_id': False,
                'calendar_id': self.calendar_jean.id,
                'date_from': datetime_str(2018, 4, 3, 10, 0, 0, tzinfo='UTC'),
                'date_to': datetime_str(2018, 4, 3, 12, 0, 0, tzinfo='Etc/GMT-6')
            })


class TestCalendar(TestResourceCommon):
    def setUp(self):
        super(TestCalendar, self).setUp()

    def test_get_work_hours_count(self):
        self.env['resource.calendar.leaves'].create({
            'name': 'Global Time Off',
            'resource_id': False,
            'calendar_id': self.calendar_jean.id,
            'date_from': datetime_str(2018, 4, 3, 0, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 3, 23, 59, 59, tzinfo=self.jean.tz),
        })

        self.env['resource.calendar.leaves'].create({
            'name': 'leave for Jean',
            'calendar_id': self.calendar_jean.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 5, 0, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 5, 23, 59, 59, tzinfo=self.jean.tz),
        })

        hours = self.calendar_jean.get_work_hours_count(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.jean.tz),
        )
        self.assertEqual(hours, 32)

        hours = self.calendar_jean.get_work_hours_count(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.jean.tz),
            compute_leaves=False,
        )
        self.assertEqual(hours, 40)

        # leave of size 0
        self.env['resource.calendar.leaves'].create({
            'name': 'zero_length',
            'calendar_id': self.calendar_patel.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 3, 0, 0, 0, tzinfo=self.patel.tz),
            'date_to': datetime_str(2018, 4, 3, 0, 0, 0, tzinfo=self.patel.tz),
        })

        hours = self.calendar_patel.get_work_hours_count(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.patel.tz),
        )
        self.assertEqual(hours, 35)

        # leave of medium size
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'zero_length',
            'calendar_id': self.calendar_patel.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 3, 9, 0, 0, tzinfo=self.patel.tz),
            'date_to': datetime_str(2018, 4, 3, 12, 0, 0, tzinfo=self.patel.tz),
        })

        hours = self.calendar_patel.get_work_hours_count(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.patel.tz),
        )
        self.assertEqual(hours, 32)

        leave.unlink()

        # leave of very small size
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'zero_length',
            'calendar_id': self.calendar_patel.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 3, 0, 0, 0, tzinfo=self.patel.tz),
            'date_to': datetime_str(2018, 4, 3, 0, 0, 10, tzinfo=self.patel.tz),
        })

        hours = self.calendar_patel.get_work_hours_count(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.patel.tz),
        )
        self.assertEqual(hours, 35)

        leave.unlink()

        # no timezone given should be converted to UTC
        # Should equal to a leave between 2018/04/03 10:00:00 and 2018/04/04 10:00:00
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'no timezone',
            'calendar_id': self.calendar_patel.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 3, 4, 0, 0),
            'date_to': datetime_str(2018, 4, 4, 4, 0, 0),
        })

        hours = self.calendar_patel.get_work_hours_count(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.patel.tz),
        )
        self.assertEqual(hours, 28)

        hours = self.calendar_patel.get_work_hours_count(
            datetime_tz(2018, 4, 2, 23, 59, 59, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
        )
        self.assertEqual(hours, 0)

        leave.unlink()

        # 2 weeks calendar week 1
        hours = self.calendar_jules.get_work_hours_count(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.jules.tz),
        )
        self.assertEqual(hours, 30)

        # 2 weeks calendar week 1
        hours = self.calendar_jules.get_work_hours_count(
            datetime_tz(2018, 4, 16, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2018, 4, 20, 23, 59, 59, tzinfo=self.jules.tz),
        )
        self.assertEqual(hours, 30)

        # 2 weeks calendar week 2
        hours = self.calendar_jules.get_work_hours_count(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.jules.tz),
        )
        self.assertEqual(hours, 16)

        # 2 weeks calendar week 2, leave during a day where he doesn't work this week
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'Time Off Jules week 2',
            'calendar_id': self.calendar_jules.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 11, 4, 0, 0, tzinfo=self.jules.tz),
            'date_to': datetime_str(2018, 4, 13, 4, 0, 0, tzinfo=self.jules.tz),
        })

        hours = self.calendar_jules.get_work_hours_count(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.jules.tz),
        )
        self.assertEqual(hours, 16)

        leave.unlink()

        # 2 weeks calendar week 2, leave during a day where he works this week
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'Time Off Jules week 2',
            'calendar_id': self.calendar_jules.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 9, 0, 0, 0, tzinfo=self.jules.tz),
            'date_to': datetime_str(2018, 4, 9, 23, 59, 0, tzinfo=self.jules.tz),
        })

        hours = self.calendar_jules.get_work_hours_count(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.jules.tz),
        )
        self.assertEqual(hours, 8)

        leave.unlink()

        # leave without calendar, should count for anyone in the company
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'small leave',
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 3, 9, 0, 0, tzinfo=self.patel.tz),
            'date_to': datetime_str(2018, 4, 3, 12, 0, 0, tzinfo=self.patel.tz),
        })

        hours = self.calendar_patel.get_work_hours_count(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.patel.tz),
        )
        self.assertEqual(hours, 32)

        # 2 weeks calendar with date_from and date_to to check work_hours
        self.calendar_jules.write({
            "attendance_ids": [
                (5, 0, 0),
                (0, 0, {
                    "name": "Monday (morning)",
                    "day_period": "morning",
                    "dayofweek": "0",
                    "week_type": "0",
                    "hour_from": 8.0,
                    "hour_to": 12.0,
                    "date_from": "2022-01-01",
                    "date_to": "2022-01-16"}),
                (0, 0, {
                    "name": "Monday (morning)",
                    "day_period": "morning",
                    "dayofweek": "0",
                    "week_type": "0",
                    "hour_from": 8.0,
                    "hour_to": 12.0,
                    "date_from": "2022-01-17"}),
                (0, 0, {
                    "name": "Monday (afternoon)",
                    "day_period": "afternoon",
                    "dayofweek": "0",
                    "week_type": "0",
                    "hour_from": 16.0,
                    "hour_to": 20.0,
                    "date_from": "2022-01-17"}),
                (0, 0, {
                    "name": "Monday (morning)",
                    "day_period": "morning",
                    "dayofweek": "0",
                    "week_type": "1",
                    "hour_from": 8.0,
                    "hour_to": 12.0,
                    "date_from": "2022-01-01",
                    "date_to": "2022-01-16"}),
                (0, 0, {
                    "name": "Monday (afternoon)",
                    "day_period": "afternoon",
                    "dayofweek": "0",
                    "week_type": "1",
                    "hour_from": 16.0,
                    "hour_to": 20.0,
                    "date_from": "2022-01-01",
                    "date_to": "2022-01-16"}),
                (0, 0, {
                    "name": "Monday (morning)",
                    "day_period": "morning",
                    "dayofweek": "0",
                    "week_type": "1",
                    "hour_from": 8.0,
                    "hour_to": 12.0,
                    "date_from": "2022-01-17"}),
                (0, 0, {
                    "name": "Monday (afternoon)",
                    "day_period": "afternoon",
                    "dayofweek": "0",
                    "week_type": "1",
                    "hour_from": 16.0,
                    "hour_to": 20.0,
                    "date_from": "2022-01-17"})]})
        hours = self.calendar_jules.get_work_hours_count(
            datetime_tz(2022, 1, 10, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2022, 1, 10, 23, 59, 59, tzinfo=self.jules.tz),
        )
        self.assertEqual(hours, 4)
        hours = self.calendar_jules.get_work_hours_count(
            datetime_tz(2022, 1, 17, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2022, 1, 17, 23, 59, 59, tzinfo=self.jules.tz),
        )
        self.assertEqual(hours, 8)

    def test_calendar_working_hours_count(self):
        calendar = self.env['resource.calendar'].create({
            'name': 'Standard 35 hours/week',
            'company_id': self.env.company.id,
            'tz': 'UTC',
            'attendance_ids': [(5, 0, 0),
                (0, 0, {'name': 'Monday Morning', 'dayofweek': '0', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Monday Lunch', 'dayofweek': '0', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Monday Afternoon', 'dayofweek': '0', 'hour_from': 13, 'hour_to': 16, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Tuesday Morning', 'dayofweek': '1', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Tuesday Lunch', 'dayofweek': '1', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Tuesday Afternoon', 'dayofweek': '1', 'hour_from': 13, 'hour_to': 16, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Wednesday Morning', 'dayofweek': '2', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Wednesday Lunch', 'dayofweek': '2', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Wednesday Afternoon', 'dayofweek': '2', 'hour_from': 13, 'hour_to': 16, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Thursday Morning', 'dayofweek': '3', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Thursday Lunch', 'dayofweek': '3', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Thursday Afternoon', 'dayofweek': '3', 'hour_from': 13, 'hour_to': 16, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Friday Morning', 'dayofweek': '4', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Friday Lunch', 'dayofweek': '4', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Friday Afternoon', 'dayofweek': '4', 'hour_from': 13, 'hour_to': 16, 'day_period': 'afternoon'})
            ],
        })
        res = calendar.get_work_hours_count(
            fields.Datetime.from_string('2017-05-03 14:03:00'),  # Wednesday (8:00-12:00, 13:00-16:00)
            fields.Datetime.from_string('2017-05-04 11:03:00'),  # Thursday (8:00-12:00, 13:00-16:00)
            compute_leaves=False)
        self.assertEqual(res, 5.0)

    def test_calendar_working_hours_24(self):
        self.att_4 = self.env['resource.calendar.attendance'].create({
            'name': 'Att4',
            'calendar_id': self.calendar_jean.id,
            'dayofweek': '2',
            'hour_from': 0,
            'hour_to': 24
        })
        res = self.calendar_jean.get_work_hours_count(
            datetime_tz(2018, 6, 19, 23, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 6, 21, 1, 0, 0, tzinfo=self.jean.tz),
            compute_leaves=True)
        self.assertAlmostEqual(res, 24.0)

    def test_plan_hours(self):
        self.env['resource.calendar.leaves'].create({
            'name': 'global',
            'calendar_id': self.calendar_jean.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 11, 0, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 11, 23, 59, 59, tzinfo=self.jean.tz),
        })

        time = self.calendar_jean.plan_hours(2, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=False)
        self.assertEqual(time, datetime_tz(2018, 4, 10, 10, 0, 0, tzinfo=self.jean.tz))

        time = self.calendar_jean.plan_hours(20, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=False)
        self.assertEqual(time, datetime_tz(2018, 4, 12, 12, 0, 0, tzinfo=self.jean.tz))

        time = self.calendar_jean.plan_hours(5, datetime_tz(2018, 4, 10, 15, 0, 0, tzinfo=self.jean.tz), compute_leaves=True)
        self.assertEqual(time, datetime_tz(2018, 4, 12, 12, 0, 0, tzinfo=self.jean.tz))

        # negative planning
        time = self.calendar_jean.plan_hours(-10, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=True)
        self.assertEqual(time, datetime_tz(2018, 4, 6, 14, 0, 0, tzinfo=self.jean.tz))

        # zero planning with holidays
        time = self.calendar_jean.plan_hours(0, datetime_tz(2018, 4, 11, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=True)
        self.assertEqual(time, datetime_tz(2018, 4, 12, 8, 0, 0, tzinfo=self.jean.tz))
        time = self.calendar_jean.plan_hours(0, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=False)
        self.assertEqual(time, datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.jean.tz))

        # very small planning
        time = self.calendar_jean.plan_hours(0.0002, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=True)
        self.assertEqual(time, datetime_tz(2018, 4, 10, 8, 0, 0, 720000, tzinfo=self.jean.tz))

        # huge planning
        time = self.calendar_jean.plan_hours(3000, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=False)
        self.assertEqual(time, datetime_tz(2019, 9, 16, 16, 0, 0, tzinfo=self.jean.tz))

    def test_plan_days(self):
        self.env['resource.calendar.leaves'].create({
            'name': 'global',
            'calendar_id': self.calendar_jean.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 11, 0, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 11, 23, 59, 59, tzinfo=self.jean.tz),
        })

        time = self.calendar_jean.plan_days(1, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=False)
        self.assertEqual(time, datetime_tz(2018, 4, 10, 16, 0, 0, tzinfo=self.jean.tz))

        time = self.calendar_jean.plan_days(3, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=False)
        self.assertEqual(time, datetime_tz(2018, 4, 12, 16, 0, 0, tzinfo=self.jean.tz))

        time = self.calendar_jean.plan_days(4, datetime_tz(2018, 4, 10, 16, 0, 0, tzinfo=self.jean.tz), compute_leaves=True)
        self.assertEqual(time, datetime_tz(2018, 4, 17, 16, 0, 0, tzinfo=self.jean.tz))

        # negative planning
        time = self.calendar_jean.plan_days(-10, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=True)
        self.assertEqual(time, datetime_tz(2018, 3, 27, 8, 0, 0, tzinfo=self.jean.tz))

        # zero planning
        time = self.calendar_jean.plan_days(0, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=True)
        self.assertEqual(time, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz))

        # very small planning returns False in this case
        # TODO: decide if this behaviour is alright
        time = self.calendar_jean.plan_days(0.0002, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=True)
        self.assertEqual(time, False)

        # huge planning
        # TODO: Same as above
        # NOTE: Maybe allow to set a max limit to the method
        time = self.calendar_jean.plan_days(3000, datetime_tz(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz), compute_leaves=False)
        self.assertEqual(time, False)

    def test_closest_time(self):
        # Calendar:
        # Tuesdays 8-16
        # Fridays 8-13 and 16-23
        dt = datetime_tz(2020, 4, 2, 7, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt)
        self.assertFalse(calendar_dt, "It should not return any value for unattended days")

        dt = datetime_tz(2020, 4, 3, 7, 0, 0, tzinfo=self.john.tz)
        range_start = datetime_tz(2020, 4, 3, 8, 0, 0, tzinfo=self.john.tz)
        range_end = datetime_tz(2020, 4, 3, 19, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt, search_range=(range_start, range_end))
        self.assertFalse(calendar_dt, "It should not return any value if dt outside of range")

        dt = datetime_tz(2020, 4, 3, 7, 0, 0, tzinfo=self.john.tz)  # before
        start = datetime_tz(2020, 4, 3, 8, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt)
        self.assertEqual(calendar_dt, start, "It should return the start of the day")

        dt = datetime_tz(2020, 4, 3, 10, 0, 0, tzinfo=self.john.tz)  # after
        start = datetime_tz(2020, 4, 3, 8, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt)
        self.assertEqual(calendar_dt, start, "It should return the start of the closest attendance")

        dt = datetime_tz(2020, 4, 3, 7, 0, 0, tzinfo=self.john.tz)  # before
        end = datetime_tz(2020, 4, 3, 13, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt, match_end=True)
        self.assertEqual(calendar_dt, end, "It should return the end of the closest attendance")

        dt = datetime_tz(2020, 4, 3, 14, 0, 0, tzinfo=self.john.tz)  # after
        end = datetime_tz(2020, 4, 3, 13, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt, match_end=True)
        self.assertEqual(calendar_dt, end, "It should return the end of the closest attendance")

        dt = datetime_tz(2020, 4, 3, 0, 0, 0, tzinfo=self.john.tz)
        start = datetime_tz(2020, 4, 3, 8, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt)
        self.assertEqual(calendar_dt, start, "It should return the start of the closest attendance")

        dt = datetime_tz(2020, 4, 3, 23, 59, 59, tzinfo=self.john.tz)
        end = datetime_tz(2020, 4, 3, 23, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt, match_end=True)
        self.assertEqual(calendar_dt, end, "It should return the end of the closest attendance")

        # with a resource specific attendance
        self.env['resource.calendar.attendance'].create({
            'name': 'Att4',
            'calendar_id': self.calendar_john.id,
            'dayofweek': '4',
            'hour_from': 5,
            'hour_to': 6,
            'resource_id': self.john.resource_id.id,
        })
        dt = datetime_tz(2020, 4, 3, 5, 0, 0, tzinfo=self.john.tz)
        start = datetime_tz(2020, 4, 3, 8, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt)
        self.assertEqual(calendar_dt, start, "It should not take into account resouce specific attendances")

        dt = datetime_tz(2020, 4, 3, 5, 0, 0, tzinfo=self.john.tz)
        start = datetime_tz(2020, 4, 3, 5, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt, resource=self.john.resource_id)
        self.assertEqual(calendar_dt, start, "It should have taken john's specific attendances")

        dt = datetime_tz(2020, 4, 4, 1, 0, 0, tzinfo='UTC')  # The next day in UTC, but still the 3rd in john's timezone (America/Los_Angeles)
        start = datetime_tz(2020, 4, 3, 16, 0, 0, tzinfo=self.john.tz)
        calendar_dt = self.calendar_john._get_closest_work_time(dt, resource=self.john.resource_id)
        self.assertEqual(calendar_dt, start, "It should have found the attendance on the 3rd April")

    def test_attendance_interval_edge_tz(self):
        # When genereting the attendance intervals in an edge timezone, the last interval shouldn't
        # be truncated if the timezone is correctly set
        self.env.user.tz = "America/Los_Angeles"
        self.calendar_jean.tz = "America/Los_Angeles"
        attendances = self.calendar_jean._attendance_intervals_batch(
            datetime.combine(date(2023, 1, 1), datetime.min.time(), tzinfo=timezone("UTC")),
            datetime.combine(date(2023, 1, 31), datetime.max.time(), tzinfo=timezone("UTC")))
        last_attendance = list(attendances[False])[-1]
        self.assertEqual(last_attendance[0].replace(tzinfo=None), datetime(2023, 1, 31, 8))
        self.assertEqual(last_attendance[1].replace(tzinfo=None), datetime(2023, 1, 31, 15, 59, 59, 999999))

        attendances = self.calendar_jean._attendance_intervals_batch(
            datetime.combine(date(2023, 1, 1), datetime.min.time(), tzinfo=timezone("America/Los_Angeles")),
            datetime.combine(date(2023, 1, 31), datetime.max.time(), tzinfo=timezone("America/Los_Angeles")))
        last_attendance = list(attendances[False])[-1]
        self.assertEqual(last_attendance[0].replace(tzinfo=None), datetime(2023, 1, 31, 8))
        self.assertEqual(last_attendance[1].replace(tzinfo=None), datetime(2023, 1, 31, 16))

    def test_resource_calendar_update(self):
        """ Ensure leave calendar gets set correctly when updating resource calendar. """
        holiday = self.env['resource.calendar.leaves'].create({
            'name': "May Day",
            'calendar_id': self.calendar_jean.id,
            'date_from': datetime_str(2024, 5, 1, 0, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2024, 5, 1, 23, 59, 59, tzinfo=self.jean.tz),
        })

        # Jean takes a leave
        leave = self.env['resource.calendar.leaves'].create({
            'name': "Jean is AFK",
            'calendar_id': self.calendar_jean.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2024, 5, 10, 8, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2024, 5, 10, 16, 0, 0, tzinfo=self.jean.tz),
        })

        # Jean changes working schedule to Jules'
        self.jean.resource_calendar_id = self.calendar_jules
        self.assertEqual(leave.calendar_id, self.calendar_jules, "Leave calendar should update")
        self.assertEqual(holiday.calendar_id, self.calendar_jean, "Global leave shouldn't change")

    def test_compute_work_time_rate_with_one_week_calendar(self):
        """Test Case: check if the computation of the work time rate in the resource.calendar is correct."""
        # Define a mid time
        resource_calendar = self.env['resource.calendar'].create({
            'name': 'Calendar Mid-Time',
            'tz': "Europe/Brussels",
            'two_weeks_calendar': False,
            'full_time_required_hours': 40,
            'attendance_ids': [
                (0, 0, {'name': 'Monday Morning', 'dayofweek': '0', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Monday Lunch', 'dayofweek': '0', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Monday Afternoon', 'dayofweek': '0', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Tuesday Morning', 'dayofweek': '1', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Tuesday Lunch', 'dayofweek': '1', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Tuesday Afternoon', 'dayofweek': '1', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Wednesday Morning', 'dayofweek': '2', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'})
            ]
        })
        self.assertAlmostEqual(resource_calendar.work_time_rate, 50, 2)

        # Define a 4/5
        resource_calendar.write({
            'name': 'Calendar (4 / 5)',
            'attendance_ids': [
                (0, 0, {'name': 'Wednesday Afternoon', 'dayofweek': '2', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Thursday Morning', 'dayofweek': '3', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Thursday Lunch', 'dayofweek': '3', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Thursday Afternoon', 'dayofweek': '3', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'})
            ]
        })
        self.assertAlmostEqual(resource_calendar.work_time_rate, 80, 2)

        # Define a 9/10
        resource_calendar.write({
            'name': 'Calendar (9 / 10)',
            'attendance_ids': [(0, 0, {'name': 'Friday Morning', 'dayofweek': '4', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'})]
        })
        self.assertAlmostEqual(resource_calendar.work_time_rate, 90, 2)

        # Define a Full-Time
        resource_calendar.write({
            'name': 'Calendar Full-Time',
            'attendance_ids': [(0, 0, {'name': 'Friday Afternoon', 'dayofweek': '4', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'})]
        })
        self.assertAlmostEqual(resource_calendar.work_time_rate, 100, 2)

    def test_compute_work_time_rate_with_two_weeks_calendar(self):
        """Test Case: check if the computation of the work time rate in the resource.calendar is correct."""
        def create_attendance_ids(attendance_list):
            return [(0, 0, {'week_type': str(i), **attendance}) for i in range(0, 2) for attendance in attendance_list]

        attendance_list = [
            {'name': 'Monday Morning', 'dayofweek': '0', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'},
            {'name': 'Monday Lunch', 'dayofweek': '0', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'},
            {'name': 'Monday Afternoon', 'dayofweek': '0', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'},
            {'name': 'Tuesday Morning', 'dayofweek': '1', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'},
            {'name': 'Tuesday Lunch', 'dayofweek': '1', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'},
            {'name': 'Tuesday Afternoon', 'dayofweek': '1', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'},
            {'name': 'Wednesday Morning', 'dayofweek': '2', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}
        ]

        # Define a mid time
        resource_calendar = self.env['resource.calendar'].create({
            'name': 'Calendar Mid-Time',
            'tz': "Europe/Brussels",
            'two_weeks_calendar': True,
            'full_time_required_hours': 40,
            'attendance_ids': create_attendance_ids(attendance_list)
        })
        self.assertAlmostEqual(resource_calendar.work_time_rate, 50, 2)

        attendance_list = [
            {'name': 'Wednesday Afternoon', 'dayofweek': '2', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'},
            {'name': 'Thursday Morning', 'dayofweek': '3', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'},
            {'name': 'Thursday Lunch', 'dayofweek': '3', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'},
            {'name': 'Thursday Afternoon', 'dayofweek': '3', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}
        ]

        # Define a 4/5
        resource_calendar.write({
            'name': 'Calendar (4 / 5)',
            'attendance_ids': create_attendance_ids(attendance_list)
        })
        self.assertAlmostEqual(resource_calendar.work_time_rate, 80, 2)

        # Define a 9/10
        resource_calendar.write({
            'name': 'Calendar (9 / 10)',
            'attendance_ids': create_attendance_ids([{'name': 'Friday Morning', 'dayofweek': '4', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}])
        })
        self.assertAlmostEqual(resource_calendar.work_time_rate, 90, 2)

        # Define a Full-Time
        resource_calendar.write({
            'name': 'Calendar Full-Time',
            'attendance_ids': create_attendance_ids([{'name': 'Friday Afternoon', 'dayofweek': '4', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}])
        })
        self.assertAlmostEqual(resource_calendar.work_time_rate, 100, 2)

class TestResMixin(TestResourceCommon):

    def test_adjust_calendar(self):
        # Calendar:
        # Tuesdays 8-16
        # Fridays 8-13 and 16-23
        result = self.john._adjust_to_calendar(
            datetime_tz(2020, 4, 3, 9, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2020, 4, 3, 14, 0, 0, tzinfo=self.john.tz),
        )
        self.assertEqual(result[self.john],(
            datetime_tz(2020, 4, 3, 8, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2020, 4, 3, 13, 0, 0, tzinfo=self.john.tz),
        ))

        result = self.john._adjust_to_calendar(
            datetime_tz(2020, 4, 3, 13, 1, 0, tzinfo=self.john.tz),
            datetime_tz(2020, 4, 3, 14, 0, 0, tzinfo=self.john.tz),
        )
        self.assertEqual(result[self.john],(
            datetime_tz(2020, 4, 3, 16, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2020, 4, 3, 23, 0, 0, tzinfo=self.john.tz),
        ))

        result = self.john._adjust_to_calendar(
            datetime_tz(2020, 4, 4, 9, 0, 0, tzinfo=self.john.tz),  # both a day without attendance
            datetime_tz(2020, 4, 4, 14, 0, 0, tzinfo=self.john.tz),
        )
        self.assertEqual(result[self.john], (None, None))

        result = self.john._adjust_to_calendar(
            datetime_tz(2020, 4, 3, 8, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2020, 4, 4, 14, 0, 0, tzinfo=self.john.tz),  # day without attendance
        )
        self.assertEqual(result[self.john], (
            datetime_tz(2020, 4, 3, 8, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2020, 4, 3, 23, 0, 0, tzinfo=self.john.tz),
        ))

        result = self.john._adjust_to_calendar(
            datetime_tz(2020, 4, 2, 8, 0, 0, tzinfo=self.john.tz),  # day without attendance
            datetime_tz(2020, 4, 3, 14, 0, 0, tzinfo=self.john.tz),
        )
        self.assertEqual(result[self.john], (
            datetime_tz(2020, 4, 3, 8, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2020, 4, 3, 13, 0, 0, tzinfo=self.john.tz),
        ))

        result = self.john._adjust_to_calendar(
            datetime_tz(2020, 3, 31, 0, 0, 0, tzinfo=self.john.tz),  # search between Tuesday and Thursday
            datetime_tz(2020, 4, 2, 23, 59, 59, tzinfo=self.john.tz),
        )
        self.assertEqual(result[self.john], (
            datetime_tz(2020, 3, 31, 8, 0, tzinfo=self.john.tz),
            datetime_tz(2020, 3, 31, 16, 0, tzinfo=self.john.tz),
        ))

        result = self.john._adjust_to_calendar(
            datetime_tz(2020, 3, 31, 0, 0, 0, tzinfo=self.john.tz),  # search between Tuesday and Friday
            datetime_tz(2020, 4, 3, 23, 59, 59, tzinfo=self.john.tz),
        )
        result = self.john._adjust_to_calendar(
            datetime_tz(2020, 3, 31, 8, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2020, 4, 3, 23, 0, 0, tzinfo=self.john.tz),
        )
        # It should find the start and end within the search range
        result = self.paul._adjust_to_calendar(
            datetime_tz(2020, 4, 2, 2, 0, 0, tzinfo='UTC'),
            datetime_tz(2020, 4, 3, 1, 59, 59, tzinfo='UTC'),
        )

        self.assertEqual(result[self.paul], (
            datetime_tz(2020, 4, 2, 4, 0, tzinfo='UTC'),
            datetime_tz(2020, 4, 2, 18, 0, tzinfo='UTC')
        ), "It should have found the start and end of the shift on the same day on April 2nd, 2020")

    def test_adjust_calendar_timezone_before(self):
        # Calendar:
        # Every day 8-16
        self.jean.tz = 'Asia/Tokyo'
        self.calendar_jean.tz = 'Europe/Brussels'

        result = self.jean._adjust_to_calendar(
            datetime_tz(2020, 4, 1, 0, 0, 0, tzinfo='Asia/Tokyo'),
            datetime_tz(2020, 4, 1, 23, 59, 59, tzinfo='Asia/Tokyo'),
        )
        self.assertEqual(result[self.jean], (
            datetime_tz(2020, 4, 1, 8, 0, 0, tzinfo='Asia/Tokyo'),
            datetime_tz(2020, 4, 1, 16, 0, 0, tzinfo='Asia/Tokyo'),
        ), "It should have found a starting time the 1st")

    def test_adjust_calendar_timezone_after(self):
        # Calendar:
        # Tuesdays 8-16
        # Fridays 8-13 and 16-23
        tz = 'Europe/Brussels'
        self.john.tz = tz
        result = self.john._adjust_to_calendar(
            datetime(2020, 4, 2, 23, 0, 0),  # The previous day in UTC, but the 3rd in Europe/Brussels
            datetime(2020, 4, 3, 20, 0, 0),
        )
        self.assertEqual(result[self.john], (
            datetime(2020, 4, 3, 6, 0, 0),
            datetime(2020, 4, 3, 21, 0, 0),
        ), "It should have found a starting time the 3rd")

    def test_work_days_data(self):
        # Looking at Jean's calendar

        # Viewing it as Jean
        data = self.jean._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 16, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {'days': 5, 'hours': 40})

        # Viewing it as Bob
        data = self.bob._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.bob.tz),
            datetime_tz(2018, 4, 6, 16, 0, 0, tzinfo=self.bob.tz),
        )[self.bob.id]
        self.assertEqual(data, {'days': 5, 'hours': 40})


        # Viewing it as Patel
        # Views from 2018/04/01 20:00:00 to 2018/04/06 12:00:00
        data = self.jean._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 6, 16, 0, 0, tzinfo=self.patel.tz),
        )[self.jean.id]
        self.assertEqual(data, {'days': 4.5, 'hours': 36})  # We see only 36 hours

        # Viewing it as John
        # Views from 2018/04/02 09:00:00 to 2018/04/07 02:00:00
        data = self.jean._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2018, 4, 6, 16, 0, 0, tzinfo=self.john.tz),
        )[self.jean.id]
        # still showing as 5 days because of rounding, but we see only 39 hours
        self.assertEqual(data, {'days': 4.875, 'hours': 39})

        # Looking at John's calendar

        # Viewing it as Jean
        # Views from 2018/04/01 15:00:00 to 2018/04/06 14:00:00
        data = self.john._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.john.id]
        self.assertEqual(data, {'days': 1.417, 'hours': 13})

        # Viewing it as Patel
        # Views from 2018/04/01 11:00:00 to 2018/04/06 10:00:00
        data = self.john._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.patel.tz),
        )[self.john.id]
        self.assertEqual(data, {'days': 1.167, 'hours': 10})

        # Viewing it as John
        data = self.john._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.john.tz),
        )[self.john.id]
        self.assertEqual(data, {'days': 2, 'hours': 20})

        # using Jean as a timezone reference
        data = self.john._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.john.tz),
            calendar=self.calendar_jean,
        )[self.john.id]
        self.assertEqual(data, {'days': 5, 'hours': 40})

        # half days
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'half',
            'calendar_id': self.calendar_jean.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 14, 0, 0, tzinfo=self.jean.tz),
        })

        data = self.jean._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {'days': 4.5, 'hours': 36})

        # using John as a timezone reference, leaves are outside attendances
        data = self.john._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.john.tz),
            calendar=self.calendar_jean,
        )[self.john.id]
        self.assertEqual(data, {'days': 5, 'hours': 40})

        leave.unlink()

        # leave size 0
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'zero',
            'calendar_id': self.calendar_jean.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
        })

        data = self.jean._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {'days': 5, 'hours': 40})

        leave.unlink()

        # leave very small size
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'small',
            'calendar_id': self.calendar_jean.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 10, 0, 1, tzinfo=self.jean.tz),
        })

        data = self.jean._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data['days'], 5)
        self.assertAlmostEqual(data['hours'], 40, 2)

    def test_leaves_days_data(self):
        # Jean takes a leave
        self.env['resource.calendar.leaves'].create({
            'name': 'Jean is visiting India',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 10, 8, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 10, 16, 0, 0, tzinfo=self.jean.tz),
        })

        # John takes a leave for Jean
        self.env['resource.calendar.leaves'].create({
            'name': 'Jean is comming in USA',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 12, 8, 0, 0, tzinfo=self.john.tz),
            'date_to': datetime_str(2018, 4, 12, 16, 0, 0, tzinfo=self.john.tz),
        })

        # Jean asks to see how much leave he has taken
        data = self.jean._get_leave_days_data_batch(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.jean.tz),
        )[self.jean.id]
        # Sees only 1 day and 8 hours because, as john is in UTC-7 the second leave is not in
        # the attendances of Jean
        self.assertEqual(data, {'days': 1, 'hours': 8})

        # Patel Asks to see when Jean has taken some leaves
        # Patel should see the same
        data = self.jean._get_leave_days_data_batch(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.patel.tz),
        )[self.jean.id]
        self.assertEqual(data, {'days': 1, 'hours': 8})

        # use Patel as a resource, jean's leaves are not visible
        datas = self.patel._get_leave_days_data_batch(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.patel.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.patel.tz),
            calendar=self.calendar_jean,
        )[self.patel.id]
        self.assertEqual(datas['days'], 0)
        self.assertEqual(datas['hours'], 0)

        # Jean takes a leave for John
        # Gives 3 hours (3/8 of a day)
        self.env['resource.calendar.leaves'].create({
            'name': 'John is sick',
            'calendar_id': self.john.resource_calendar_id.id,
            'resource_id': self.john.resource_id.id,
            'date_from': datetime_str(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 10, 20, 0, 0, tzinfo=self.jean.tz),
        })

        # John takes a leave
        # Gives all day (12 hours)
        self.env['resource.calendar.leaves'].create({
            'name': 'John goes to holywood',
            'calendar_id': self.john.resource_calendar_id.id,
            'resource_id': self.john.resource_id.id,
            'date_from': datetime_str(2018, 4, 13, 7, 0, 0, tzinfo=self.john.tz),
            'date_to': datetime_str(2018, 4, 13, 18, 0, 0, tzinfo=self.john.tz),
        })

        # John asks how much leaves he has
        # He sees that he has only 15 hours of leave in his attendances
        data = self.john._get_leave_days_data_batch(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.john.tz),
        )[self.john.id]
        self.assertEqual(data, {'days': 0.958, 'hours': 10})

        # half days
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'half',
            'calendar_id': self.calendar_jean.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 14, 0, 0, tzinfo=self.jean.tz),
        })

        data = self.jean._get_leave_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {'days': 0.5, 'hours': 4})

        leave.unlink()

        # leave size 0
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'zero',
            'calendar_id': self.calendar_jean.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
        })

        data = self.jean._get_leave_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {'days': 0, 'hours': 0})

        leave.unlink()

        # leave very small size
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'small',
            'calendar_id': self.calendar_jean.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 10, 0, 1, tzinfo=self.jean.tz),
        })

        data = self.jean._get_leave_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data['days'], 0)
        self.assertAlmostEqual(data['hours'], 0, 2)

        leave.unlink()

    def test_list_leaves(self):
        jean_leave = self.env['resource.calendar.leaves'].create({
            'name': "Jean's son is sick",
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': False,
            'date_from': datetime_str(2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 10, 23, 59, 59, tzinfo=self.jean.tz),
        })

        leaves = self.jean.list_leaves(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.jean.tz),
        )
        self.assertEqual(leaves, [(date(2018, 4, 10), 8, jean_leave)])

        # half days
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'half',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 14, 0, 0, tzinfo=self.jean.tz),
        })

        leaves = self.jean.list_leaves(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )
        self.assertEqual(leaves, [(date(2018, 4, 2), 4, leave)])

        leave.unlink()

        # very small size
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'small',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 10, 0, 1, tzinfo=self.jean.tz),
        })

        leaves = self.jean.list_leaves(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )
        self.assertEqual(len(leaves), 1)
        self.assertEqual(leaves[0][0], date(2018, 4, 2))
        self.assertAlmostEqual(leaves[0][1], 0, 2)
        self.assertEqual(leaves[0][2].id, leave.id)

        leave.unlink()

        # size 0
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'zero',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
        })

        leaves = self.jean.list_leaves(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )
        self.assertEqual(leaves, [])

        leave.unlink()

    def test_list_work_time_per_day(self):
        working_time = self.john._list_work_time_per_day(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.john.tz),
        )[self.john.id]
        self.assertEqual(working_time, [
            (date(2018, 4, 10), 8),
            (date(2018, 4, 13), 12),
        ])

        # change john's resource's timezone
        self.john.resource_id.tz = 'Europe/Brussels'
        self.assertEqual(self.john.tz, 'Europe/Brussels')
        self.assertEqual(self.calendar_john.tz, 'America/Los_Angeles')
        working_time = self.john._list_work_time_per_day(
            datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.john.tz),
            datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.john.tz),
        )[self.john.id]
        self.assertEqual(working_time, [
            (date(2018, 4, 10), 8),
            (date(2018, 4, 13), 12),
        ])

        # half days
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'small',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 14, 0, 0, tzinfo=self.jean.tz),
        })

        working_time = self.jean._list_work_time_per_day(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(working_time, [
            (date(2018, 4, 2), 4),
            (date(2018, 4, 3), 8),
            (date(2018, 4, 4), 8),
            (date(2018, 4, 5), 8),
            (date(2018, 4, 6), 8),
        ])

        leave.unlink()

        # very small size
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'small',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 10, 0, 1, tzinfo=self.jean.tz),
        })

        working_time = self.jean._list_work_time_per_day(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(len(working_time), 5)
        self.assertEqual(working_time[0][0], date(2018, 4, 2))
        self.assertAlmostEqual(working_time[0][1], 8, 2)

        leave.unlink()

        # size 0
        leave = self.env['resource.calendar.leaves'].create({
            'name': 'zero',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            'date_to': datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
        })

        working_time = self.jean._list_work_time_per_day(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(working_time, [
            (date(2018, 4, 2), 8),
            (date(2018, 4, 3), 8),
            (date(2018, 4, 4), 8),
            (date(2018, 4, 5), 8),
            (date(2018, 4, 6), 8),
        ])

        leave.unlink()


class TestTimezones(TestResourceCommon):
    def setUp(self):
        super(TestTimezones, self).setUp()

        self.tz1 = 'Etc/GMT+6'
        self.tz2 = 'Europe/Brussels'
        self.tz3 = 'Etc/GMT-10'
        self.tz4 = 'Etc/GMT+10'

    def test_work_hours_count(self):
        # When no timezone => UTC
        count = self.calendar_jean.get_work_hours_count(
            datetime_tz(2018, 4, 10, 8, 0, 0),
            datetime_tz(2018, 4, 10, 12, 0, 0),
        )
        self.assertEqual(count, 4)

        # This timezone is not the same as the calendar's one
        count = self.calendar_jean.get_work_hours_count(
            datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz1),
            datetime_tz(2018, 4, 10, 12, 0, 0, tzinfo=self.tz1),
        )
        self.assertEqual(count, 0)

        # Using two different timezones
        # 10-04-2018 06:00:00 - 10-04-2018 02:00:00
        count = self.calendar_jean.get_work_hours_count(
            datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz2),
            datetime_tz(2018, 4, 10, 12, 0, 0, tzinfo=self.tz3),
        )
        self.assertEqual(count, 0)

        # Using two different timezones
        # 2018-4-10 06:00:00 - 2018-4-10 22:00:00
        count = self.calendar_jean.get_work_hours_count(
            datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz2),
            datetime_tz(2018, 4, 10, 12, 0, 0, tzinfo=self.tz4),
        )
        self.assertEqual(count, 8)

    def test_plan_hours(self):
        dt = self.calendar_jean.plan_hours(10, datetime_tz(2018, 4, 10, 8, 0, 0))
        self.assertEqual(dt, datetime_tz(2018, 4, 11, 10, 0, 0))

        dt = self.calendar_jean.plan_hours(10, datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz4))
        self.assertEqual(dt, datetime_tz(2018, 4, 11, 22, 0, 0, tzinfo=self.tz4))

    def test_plan_days(self):
        dt = self.calendar_jean.plan_days(2, datetime_tz(2018, 4, 10, 8, 0, 0))
        self.assertEqual(dt, datetime_tz(2018, 4, 11, 14, 0, 0))

        # We lose one day because of timezone
        dt = self.calendar_jean.plan_days(2, datetime_tz(2018, 4, 10, 8, 0, 0, tzinfo=self.tz4))
        self.assertEqual(dt, datetime_tz(2018, 4, 12, 4, 0, 0, tzinfo=self.tz4))

    def test_work_data(self):
        # 09-04-2018 10:00:00 - 13-04-2018 18:00:00
        data = self.jean._get_work_days_data_batch(
            datetime_tz(2018, 4, 9, 8, 0, 0),
            datetime_tz(2018, 4, 13, 16, 0, 0),
        )[self.jean.id]
        self.assertEqual(data, {'days': 4.75, 'hours': 38})

        # 09-04-2018 00:00:00 - 13-04-2018 08:00:00
        data = self.jean._get_work_days_data_batch(
            datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz3),
            datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz3),
        )[self.jean.id]
        self.assertEqual(data, {'days': 4, 'hours': 32})

        # 09-04-2018 08:00:00 - 14-04-2018 12:00:00
        data = self.jean._get_work_days_data_batch(
            datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
            datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz4),
        )[self.jean.id]
        self.assertEqual(data, {'days': 5, 'hours': 40})

        # Jules with 2 weeks calendar
        # 02-04-2018 00:00:00 - 6-04-2018 23:59:59
        data = self.jules._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2018, 4, 6, 23, 59, 59, tzinfo=self.jules.tz),
        )[self.jules.id]
        self.assertEqual(data, {'days': 4, 'hours': 30})

        # Jules with 2 weeks calendar
        # 02-04-2018 00:00:00 - 14-04-2018 23:59:59
        data = self.jules._get_work_days_data_batch(
            datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2018, 4, 14, 23, 59, 59, tzinfo=self.jules.tz),
        )[self.jules.id]
        self.assertEqual(data, {'days': 6, 'hours': 46})

        # Jules with 2 weeks calendar
        # 12-29-2014 00:00:00 - 27-12-2019 23:59:59 => 261 weeks
        # 130 weeks type 1: 131*4 = 524 days and 131*30 = 3930 hours
        # 131 weeks type 2: 130*2 = 260 days and 130*16 = 2080 hours
        data = self.jules._get_work_days_data_batch(
            datetime_tz(2014, 12, 29, 0, 0, 0, tzinfo=self.jules.tz),
            datetime_tz(2019, 12, 27, 23, 59, 59, tzinfo=self.jules.tz),
        )[self.jules.id]
        self.assertEqual(data, {'days': 784, 'hours': 6010})

    def test_leave_data(self):
        self.env['resource.calendar.leaves'].create({
            'name': '',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
            'date_to': datetime_str(2018, 4, 9, 14, 0, 0, tzinfo=self.tz2),
        })

        # 09-04-2018 10:00:00 - 13-04-2018 18:00:00
        data = self.jean._get_leave_days_data_batch(
            datetime_tz(2018, 4, 9, 8, 0, 0),
            datetime_tz(2018, 4, 13, 16, 0, 0),
        )[self.jean.id]
        self.assertEqual(data, {'days': 0.5, 'hours': 4})

        # 09-04-2018 00:00:00 - 13-04-2018 08:00:00
        data = self.jean._get_leave_days_data_batch(
            datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz3),
            datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz3),
        )[self.jean.id]
        self.assertEqual(data, {'days': 0.75, 'hours': 6})

        # 09-04-2018 08:00:00 - 14-04-2018 12:00:00
        data = self.jean._get_leave_days_data_batch(
            datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
            datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz4),
        )[self.jean.id]
        self.assertEqual(data, {'days': 0.75, 'hours': 6})

    def test_leaves(self):
        leave = self.env['resource.calendar.leaves'].create({
            'name': '',
            'calendar_id': self.jean.resource_calendar_id.id,
            'resource_id': self.jean.resource_id.id,
            'date_from': datetime_str(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
            'date_to': datetime_str(2018, 4, 9, 14, 0, 0, tzinfo=self.tz2),
        })

        # 09-04-2018 10:00:00 - 13-04-2018 18:00:00
        leaves = self.jean.list_leaves(
            datetime_tz(2018, 4, 9, 8, 0, 0),
            datetime_tz(2018, 4, 13, 16, 0, 0),
        )
        self.assertEqual(leaves, [(date(2018, 4, 9), 4, leave)])

        # 09-04-2018 00:00:00 - 13-04-2018 08:00:00
        leaves = self.jean.list_leaves(
            datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz3),
            datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz3),
        )
        self.assertEqual(leaves, [(date(2018, 4, 9), 6, leave)])

        # 09-04-2018 08:00:00 - 14-04-2018 12:00:00
        leaves = self.jean.list_leaves(
            datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
            datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz4),
        )
        self.assertEqual(leaves, [(date(2018, 4, 9), 6, leave)])

    def test_works(self):
        work = self.jean._list_work_time_per_day(
            datetime_tz(2018, 4, 9, 8, 0, 0),
            datetime_tz(2018, 4, 13, 16, 0, 0),
        )[self.jean.id]
        self.assertEqual(work, [
            (date(2018, 4, 9), 6),
            (date(2018, 4, 10), 8),
            (date(2018, 4, 11), 8),
            (date(2018, 4, 12), 8),
            (date(2018, 4, 13), 8),
        ])

        work = self.jean._list_work_time_per_day(
            datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz3),
            datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz3),
        )[self.jean.id]
        self.assertEqual(len(work), 4)
        self.assertEqual(work, [
            (date(2018, 4, 9), 8),
            (date(2018, 4, 10), 8),
            (date(2018, 4, 11), 8),
            (date(2018, 4, 12), 8),
        ])

        work = self.jean._list_work_time_per_day(
            datetime_tz(2018, 4, 9, 8, 0, 0, tzinfo=self.tz2),
            datetime_tz(2018, 4, 13, 16, 0, 0, tzinfo=self.tz4),
        )[self.jean.id]
        self.assertEqual(work, [
            (date(2018, 4, 9), 8),
            (date(2018, 4, 10), 8),
            (date(2018, 4, 11), 8),
            (date(2018, 4, 12), 8),
            (date(2018, 4, 13), 8),
        ])

    @freeze_time("2022-09-21 15:30:00", tz_offset=-10)
    def test_unavailable_intervals(self):
        resource = self.env['resource.resource'].create({
            'name': 'resource',
            'tz': self.tz3,
        })
        intervals = resource._get_unavailable_intervals(datetime(2022, 9, 21), datetime(2022, 9, 22))
        self.assertEqual(list(intervals.values())[0], [
            (datetime(2022, 9, 21, 0, 0, tzinfo=utc), datetime(2022, 9, 21, 6, 0, tzinfo=utc)),
            (datetime(2022, 9, 21, 10, 0, tzinfo=utc), datetime(2022, 9, 21, 11, 0, tzinfo=utc)),
            (datetime(2022, 9, 21, 15, 0, tzinfo=utc), datetime(2022, 9, 22, 0, 0, tzinfo=utc)),
        ])

    def test_flexible_resource_leave_interval(self):
        """
        Test whole day off for a flexible resource.
        The standard 8 - 17 leave should be converted to a whole day leave interval for the flexible resource.
        """

        flexible_calendar = self.env['resource.calendar'].create({
            'name': 'Flex Calendar',
            'tz': 'UTC',
            'flexible_hours': True,
            'full_time_required_hours': 40,
            'hours_per_day': 8
        })
        flex_resource = self.env['resource.resource'].create({
            'name': 'Test FlexResource',
            'calendar_id': flexible_calendar.id,
        })
        self.env['resource.calendar.leaves'].create({
            'name': 'Standard Time Off',
            'calendar_id': flexible_calendar.id,
            'resource_id': flex_resource.id,
            'date_from': '2025-03-07 08:00:00',
            'date_to': '2025-03-07 17:00:00',
        })

        start_dt = datetime(2025, 3, 7, 8, 0, 0, tzinfo=utc)
        end_dt = datetime(2025, 3, 7, 16, 00, 00, 00, tzinfo=utc)

        intervals = flexible_calendar._leave_intervals_batch(start_dt, end_dt, [flex_resource])
        intervals_list = list(intervals[flex_resource.id])
        self.assertEqual(len(intervals_list), 1, "There should be one leave interval")
        interval = intervals_list[0]
        self.assertEqual(interval[0], start_dt, "The start of the interval should be 08:00:00")
        self.assertEqual(interval[1], end_dt, "The end of the interval should be 16:00:00")

class TestResource(TestResourceCommon):

    def test_calendars_validity_within_period(self):
        calendars = self.jean.resource_id._get_calendars_validity_within_period(
            utc.localize(datetime(2021, 7, 1, 8, 0, 0)),
            utc.localize(datetime(2021, 7, 30, 17, 0, 0)),
        )
        interval = Intervals([(
            utc.localize(datetime(2021, 7, 1, 8, 0, 0)),
            utc.localize(datetime(2021, 7, 30, 17, 0, 0)),
            self.env['resource.calendar.attendance']
        )])

        self.assertEqual(1, len(calendars), "The dict returned by calendars validity should only have 1 entry")
        self.assertEqual(1, len(calendars[self.jean.resource_id.id]), "Jean should only have one calendar")
        jean_entry = calendars[self.jean.resource_id.id]
        jean_calendar = next(iter(jean_entry))
        self.assertEqual(self.jean.resource_calendar_id, jean_calendar, "It should be Jean's Calendar")
        self.assertFalse(jean_entry[jean_calendar] - interval, "Interval should cover all calendar's validity")
        self.assertFalse(interval - jean_entry[jean_calendar], "Calendar validity should cover all interval")

        calendars = self.env['resource.resource']._get_calendars_validity_within_period(
            utc.localize(datetime(2021, 7, 1, 8, 0, 0)),
            utc.localize(datetime(2021, 7, 30, 17, 0, 0)),
        )
        self.assertEqual(1, len(calendars), "The dict returned by calendars validity should only have 1 entry")
        self.assertEqual(1, len(calendars[False]), "False (default) should only have one calendar")
        false_entry = calendars[False]
        false_calendar = next(iter(false_entry))
        self.assertEqual(self.env.company.resource_calendar_id, false_calendar, "It should be company calendar Calendar")
        self.assertFalse(false_entry[false_calendar] - interval, "Interval should cover all calendar's validity")
        self.assertFalse(interval - false_entry[false_calendar], "Calendar validity should cover all interval")

    def test_performance(self):
        calendars = [self.calendar_jean, self.calendar_john, self.calendar_jules, self.calendar_patel]
        calendars_len = len(calendars)
        self.resources_test = self.env['resource.test'].create([{
            'name': 'resource ' + str(i),
            'resource_calendar_id': calendars[i % calendars_len].id,
        } for i in range(0, 50)])

        start = utc.localize(datetime(2021, 7, 7, 12, 0, 0))
        end = utc.localize(datetime(2021, 7, 16, 23, 59, 59))
        with self.assertQueryCount(13):
            work_intervals, _ = self.resources_test.resource_id._get_valid_work_intervals(start, end)

        self.assertEqual(len(work_intervals), 50)

    def test_get_valid_work_intervals(self):
        start = utc.localize(datetime(2021, 7, 7, 12, 0, 0))
        end = utc.localize(datetime(2021, 7, 16, 23, 59, 59))
        work_intervals, _ = self.jean.resource_id._get_valid_work_intervals(start, end)
        sum_work_intervals = sum_intervals(work_intervals[self.jean.resource_id.id])
        self.assertEqual(58, sum_work_intervals, "Sum of the work intervals for the resource jean should be 40h+18h = 58h")

    def test_get_valid_work_intervals_calendars_only(self):
        calendars = [self.calendar_jean, self.calendar_john, self.calendar_jules, self.calendar_patel]
        start = utc.localize(datetime(2021, 7, 7, 12, 0, 0))
        end = utc.localize(datetime(2021, 7, 16, 23, 59, 59))
        _, calendars_intervals = self.env['resource.resource']._get_valid_work_intervals(start, end, calendars)
        sum_work_intervals_jean = sum_intervals(calendars_intervals[self.calendar_jean.id])
        self.assertEqual(58, sum_work_intervals_jean, "Sum of the work intervals for the calendar of jean should be 40h+18h = 58h")
        sum_work_intervals_john = sum_intervals(calendars_intervals[self.calendar_john.id])
        self.assertEqual(26 - 1 / 3600, sum_work_intervals_john, "Sum of the work intervals for the calendar of john should be 20h+6h-1s = 25h59m59s")
        sum_work_intervals_jules = sum_intervals(calendars_intervals[self.calendar_jules.id])
        self.assertEqual(31, sum_work_intervals_jules, "Sum of the work intervals for the calendar of jules should be Wodd:15h+Wpair:16h = 31h")
        sum_work_intervals_patel = sum_intervals(calendars_intervals[self.calendar_patel.id])
        self.assertEqual(49, sum_work_intervals_patel, "Sum of the work intervals for the calendar of patel should be 14+35h = 49h")

    def test_switch_two_weeks_resource(self):
        """
            Check that it is possible to switch the company's default calendar
        """
        self.env.company.resource_calendar_id = self.two_weeks_resource
        company_resource = self.env.company.resource_calendar_id
        # Switch two times to be sure to test both cases
        company_resource.switch_calendar_type()
        company_resource.switch_calendar_type()

    def test_create_company_using_two_weeks_resource(self):
        """
            Check that we can create a new company
            if the default company calendar is two weeks
        """
        self.env.company.resource_calendar_id = self.two_weeks_resource
        self.env['res.company'].create({'name': 'New Company'})

    def test_empty_working_hours_for_two_weeks_resource(self):
        resource = self._define_calendar_2_weeks(
            'Two weeks resource',
            [],
            'Europe/Brussels'
        )
        resource_attendance = self.env['resource.calendar.attendance'].create({
            'name': 'test',
            'calendar_id': self.calendar_jean.id,
            'hour_from': 0,
            'hour_to': 0
        })
        resource_hour = resource._get_hours_per_day(resource_attendance)
        self.assertEqual(resource_hour, 0.0)

    def test_resource_without_calendar(self):
        resource = self.env['resource.resource'].create({
            'name': 'resource',
            'calendar_id': False,
        })

        resource.company_id.resource_calendar_id = False
        unavailabilities = resource._get_unavailable_intervals(datetime(2024, 7, 11), datetime(2024, 7, 12))
        self.assertFalse(unavailabilities)
