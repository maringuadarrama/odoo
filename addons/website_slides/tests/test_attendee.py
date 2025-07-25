# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from http import HTTPStatus
from urllib.parse import parse_qs

from odoo import fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.base.tests.common import HttpCaseWithUserPortal
from odoo.addons.website_slides.tests import common
from odoo.tests import tagged, users

@tagged('post_install', '-at_install')
class TestAttendee(common.SlidesCase):

    @users('user_officer')
    def test_attendee_course_completion_values(self):
        """ Check that once completed, the member_status remains 'completed', except if
            attendee leaves course and is reinvited / rejoins the course, it is then recomputed."""

        def check_course_completion_values(member_status='completed'):
            """ Check that the course completion is still accounted for, with given member_status """
            self.assertEqual(user_portal_channel_partner.member_status, member_status)
            self.assertEqual(user_portal_channel_partner.completion, 100)
            self.assertTrue(self.channel.with_user(self.user_portal).completed)

        user_portal_partner = self.user_portal.partner_id
        user_portal_channel_partner = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': user_portal_partner.id,
        })
        (self.slide | self.slide_2 | self.slide_3).with_user(self.user_portal)._action_mark_completed()
        check_course_completion_values()

        # A new slide should not update status / completion
        self.env['slide.slide'].create({
            'name': 'About completion',
            'channel_id': self.channel.id,
            'slide_category': 'document',
            'is_published': True,
            'completion_time': 2.0,
            'sequence': 10,
        })
        check_course_completion_values()

        # Unpublish a slide user has completed
        self.slide.is_published = False
        check_course_completion_values()

        # Archive attendee
        user_portal_channel_partner.action_archive()
        check_course_completion_values()

        # Invited attendee only gets status update
        self.channel._action_add_members(self.user_portal.partner_id, member_status='invited')
        check_course_completion_values(member_status='invited')

        # Pulbishing a slide user has completed. This will update user values,
        # but only on channel (those are used for diplay and not before joining)
        self.slide.is_published = True
        self.assertEqual(user_portal_channel_partner.member_status, 'invited')
        self.assertEqual(user_portal_channel_partner.completion, 100)
        self.assertEqual(self.channel.with_user(self.user_portal).completion, 75)
        self.assertFalse(self.channel.with_user(self.user_portal).completed)

        # Once they are enrolled (or join), values are now updated and completion is lost.
        self.channel._action_add_members(self.user_portal.partner_id)
        self.assertEqual(user_portal_channel_partner.member_status, 'ongoing')
        self.assertEqual(user_portal_channel_partner.completion, 75)
        self.assertEqual(self.channel.with_user(self.user_portal).completion, 75)
        self.assertFalse(self.channel.with_user(self.user_portal).completed)

    @users('user_officer')
    def test_enroll_to_course(self):
        user_portal_partner = self.user_portal.partner_id
        self.assertFalse(user_portal_partner.id in self.channel.partner_ids.ids)

        # Enroll partner to course
        self.slide_channel_invite_wizard = self.env['slide.channel.invite'].create({
            'channel_id': self.channel.id,
            'partner_ids': [(6, 0, [self.user_portal.partner_id.id])],
            'enroll_mode': True,
        })
        self.slide_channel_invite_wizard.action_invite()

        # The partner should be in the attendees as 'joined'
        user_portal_channel_partner = self.channel.channel_partner_all_ids.filtered(lambda p: p.partner_id.id == user_portal_partner.id)
        self.assertTrue(user_portal_channel_partner)
        self.assertFalse(self.channel.with_user(self.user_portal).is_member_invited)
        self.assertIn(user_portal_channel_partner.id, self.channel.channel_partner_ids.ids)
        self.assertTrue(self.channel.with_user(self.user_portal).is_member)
        self.assertEqual(user_portal_channel_partner.member_status, 'joined')

        # Subscribe enrolled attendees to the chatter
        self.assertIn(user_portal_partner.id, self.channel.message_partner_ids.ids)

    @users('user_officer')
    def test_invite_to_course(self):
        user_portal_partner = self.user_portal.partner_id
        self.assertFalse(user_portal_partner.id in self.channel.partner_ids.ids)

        # Invite partner to course
        self.slide_channel_invite_wizard = self.env['slide.channel.invite'].create({
            'channel_id': self.channel.id,
            'partner_ids': [(6, 0, [self.user_portal.partner_id.id])],
            'send_email': True,
        })
        self.slide_channel_invite_wizard.action_invite()

        # The partner should be in the attendees as 'invited'
        user_portal_channel_partner = self.channel.channel_partner_all_ids.filtered(lambda p: p.partner_id.id == user_portal_partner.id)
        self.assertTrue(user_portal_channel_partner)
        self.assertTrue(self.channel.with_user(self.user_portal).is_member_invited)
        self.assertFalse(user_portal_channel_partner.id in self.channel.channel_partner_ids.ids)
        self.assertFalse(self.channel.with_user(self.user_portal).is_member)
        self.assertEqual(user_portal_channel_partner.member_status, 'invited')

        # Do not subscribe invited members to the chatter
        self.assertFalse(user_portal_partner.id in self.channel.message_partner_ids.ids)

    @users('user_officer')
    def test_invite_archived_attendees_to_course(self):
        # Make user_portal have ongoing progress in the course
        user_portal_partner = self.user_portal.partner_id
        user_portal_channel_partner = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': user_portal_partner.id,
        })
        self.slide.with_user(self.user_portal).sudo().action_mark_completed()
        user_portal_channel_partner.action_archive()
        self.assertEqual(user_portal_channel_partner.member_status, 'ongoing')

        # Invite archived ongoing partner to course
        self.slide_channel_invite_wizard = self.env['slide.channel.invite'].create({
            'channel_id': self.channel.id,
            'partner_ids': [(6, 0, [self.user_portal.partner_id.id])],
            'send_email': True,
        })
        self.slide_channel_invite_wizard.action_invite()

        # The partner should be reactivated in the attendees as 'invited'
        self.assertTrue(user_portal_channel_partner.active)
        self.assertTrue(user_portal_channel_partner.completion > 0)
        self.assertEqual(user_portal_channel_partner.member_status, 'invited')

        # Archive then enroll the attendee
        user_portal_channel_partner.action_archive()
        self.slide_channel_invite_wizard.enroll_mode = True
        self.slide_channel_invite_wizard.flush_recordset()
        self.slide_channel_invite_wizard.action_invite()

        # The partner should be reactivated in the attendees as 'ongoing'
        self.assertTrue(user_portal_channel_partner.active)
        self.assertTrue(user_portal_channel_partner.completion > 0)
        self.assertEqual(user_portal_channel_partner.member_status, 'ongoing')

    @users('user_officer')
    def test_join_invite_enroll_channel(self):
        self.channel.enroll = 'invite'
        user_portal_partner = self.user_portal.partner_id

        # Uninvited partner cannot join the course
        self.channel.with_user(self.user_portal)._action_add_members(user_portal_partner)
        self.assertFalse(user_portal_partner.id in self.channel.partner_ids.ids)

        user_portal_channel_partner = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': user_portal_partner.id,
            'member_status': 'invited'
        })

        self.assertIn(user_portal_partner, self.channel.channel_partner_all_ids.partner_id)
        self.assertFalse(user_portal_partner.id in self.channel.partner_ids.ids)
        # Invited partner can join the course and enroll itself. Sudo is used in controller if invited.
        self.assertTrue(self.channel.with_user(self.user_portal).is_member_invited)
        self.channel.with_user(self.user_portal).sudo()._action_add_members(user_portal_partner)
        self.assertEqual(user_portal_channel_partner.member_status, 'joined')
        self.assertIn(user_portal_partner.id, self.channel.partner_ids.ids)
        self.assertIn(self.user_portal.partner_id.id, self.channel.message_partner_ids.ids)

    @users('user_officer')
    def test_member_default_create(self):
        slide_channel_partner = self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': self.user_portal.partner_id.id
        })

        # By default, partner is enrolled
        self.assertFalse(self.channel.with_user(self.user_portal).is_member_invited)
        self.assertTrue(self.channel.with_user(self.user_portal).is_member)
        self.assertEqual(slide_channel_partner.member_status, 'joined')

    @users('user_officer')
    def test_partners_and_search_on_slide_channel(self):
        ''' Check that partner_ids contains (only) active enrolled partners '''
        invited_cp, joined_cp = self.env['slide.channel.partner'].create([{
            'channel_id': self.channel.id,
            'partner_id': self.user_portal.partner_id.id,
            'member_status': 'invited'
        }, {
            'channel_id': self.channel.id,
            'partner_id': self.user_emp.partner_id.id,
            'member_status': 'joined'
        }])

        # Search partner_ids on model
        invited_cp_channel_ids = self.env['slide.channel'].search([('partner_ids', '=', invited_cp.partner_id.id)])
        self.assertFalse(self.channel in invited_cp_channel_ids)
        joined_cp_channel_ids = self.env['slide.channel'].search([('partner_ids', '=', joined_cp.partner_id.id)])
        self.assertIn(self.channel, joined_cp_channel_ids)

        partner_ids = self.channel.partner_ids
        self.assertFalse(invited_cp.partner_id in partner_ids)
        self.assertIn(joined_cp.partner_id, partner_ids)

        partner_ids = self.channel.partner_ids
        self.assertFalse(invited_cp.partner_id in partner_ids)
        self.assertIn(joined_cp.partner_id, partner_ids)

        invited_cp.action_archive()
        joined_cp.action_archive()

        partner_ids = self.channel.partner_ids
        self.assertFalse(invited_cp.partner_id in partner_ids)
        self.assertFalse(joined_cp.partner_id in partner_ids)

        invited_cp_channel_ids = self.env['slide.channel'].search([('partner_ids', '=', invited_cp.partner_id.id)])
        self.assertFalse(self.channel in invited_cp_channel_ids)
        joined_cp_channel_ids = self.env['slide.channel'].search([('partner_ids', '=', joined_cp.partner_id.id)])
        self.assertFalse(self.channel in joined_cp_channel_ids)

    def test_copy_partner_not_course_member(self):
        """ To check members of the channel after duplication of contact """
        # Adding member
        self.channel._action_add_members(self.customer)
        self.channel.invalidate_recordset()

        # Member count before copy of contact
        member_before = self.env['slide.channel.partner'].search_count([])

        # Duplicating the contact
        self.customer.copy()

        # Member count after copy of contact
        member_after = self.env['slide.channel.partner'].search_count([])
        self.assertEqual(member_before, member_after, "Duplicating the contact should not create a new member")

@tagged('-at_install', 'post_install')
class TestAttendeeCase(HttpCaseWithUserPortal):

    def setUp(self):
        super(TestAttendeeCase, self).setUp()
        self.user_admin = self.env.ref('base.user_admin')
        self.user_admin.write({
            'email': 'mitchell.admin@example.com',
        })
        self.user_emp = mail_new_test_user(
            self.env,
            email='employee@example.com',
            groups='base.group_user',
            login='user_emp',
            name='Eglantine Employee',
            notification_type='email',
        )
        self.user_public = mail_new_test_user(
            self.env, login="user_public", name="User Public", groups="base.group_public"
        )
        self.channel = self.env['slide.channel'].with_user(self.user_admin).create({
            'name': 'All about attendee status - Attendees only',
            'channel_type': 'training',
            'enroll': 'public',
            'visibility': 'public',
            'is_published': True,
        })
        self.channel_connect, self.channel_members, self.channel_link = self.env['slide.channel'].with_user(self.user_admin).create([{
            'name': f'Channel {visibility}',
            'visibility': visibility,
            'is_published': True,
            'enroll': 'invite' if visibility == 'members' else 'public',
        } for visibility in ['connected', 'members', 'link']])
        self.available_channels = self.channel_connect | self.channel_members | self.channel_link | self.channel
        self.slide = self.env['slide.slide'].with_user(self.user_admin).create({
            'name': 'How to understand membership',
            'channel_id': self.channel.id,
            'slide_type': 'article',
            'is_published': True,
            'completion_time': 2.0,
            'sequence': 1,
        })
        self.partner_no_user = self.env['res.partner'].create({
            'country_id': self.env.ref('base.be').id,
            'email': 'partner_no_user@example.com',
            'name': 'Partner Without User',
        })
        # Enrolled by default
        self.channel_partner_emp, self.channel_partner_no_user = self.env['slide.channel.partner'].create([{
            'channel_id': self.channel.id,
            'partner_id': self.user_emp.partner_id.id
        }, {
            'channel_id': self.channel.id,
            'partner_id': self.partner_no_user.id
        }])

    def test_direct_enroll_link_redirection(self):
        ''' Check that the /invite route redirects properly when enrolled user clicks their invitation link.'''
        invite_url_emp = self.channel_partner_emp.invitation_link
        invite_url_no_user = self.channel_partner_no_user.invitation_link

        # No user logged. Partner has a user. Redirects to login.
        res = self.url_open(invite_url_emp, allow_redirects=False)
        res.raise_for_status()
        url = self.parse_http_location(res.headers.get('Location'))
        query = parse_qs(url.query)
        self.assertEqual((res.status_code, url.path), (HTTPStatus.SEE_OTHER, '/web/login'),
            "Should redirect to login page if not logged in.")
        self.assertEqual(query['auth_login'], ['user_emp'],
            "The login should correspond to the invited partner.")
        self.assertEqual(query['redirect'], [f'/slides/{self.channel.id}'],
            "Login should redirect to the course.")

        # No user logged. Partner has no user. Redirects to a prepared signup. Decode is used because of signup prepare.
        res = self.url_open(invite_url_no_user, allow_redirects=False)
        res.raise_for_status()
        url = self.parse_http_location(res.headers.get('Location'))
        query = parse_qs(url.query)
        self.assertEqual((res.status_code, url.path), (HTTPStatus.SEE_OTHER, '/web/signup'),
            "Should redirect to signup page if not logged in and without user.")
        self.assertEqual(query['redirect'], [f'/slides/{self.channel.id}'],
            "Signup should redirect to the course.")

        # Logged user is an attendee of the course
        self.authenticate("user_emp", "user_emp")
        res = self.url_open(invite_url_emp)
        res.raise_for_status()
        url = self.parse_http_location(res.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(url.path, f'/slides/{self.env["ir.http"]._slug(self.channel)}',
            "Should redirect the logged attendee to the course page")

        # Logged user is not an attendee of the course, and has no rights to see it.
        self.channel_partner_emp.sudo().unlink()
        self.channel.visibility = 'members'
        res = self.url_open(invite_url_emp)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(f'slides/{self.env["ir.http"]._slug(self.channel)}' in res.url, "Should not redirect the logged attendee to the course page")

    def test_direct_invite_link_members_visibility_as_archived(self):
        ''' Check that archived attendees are not given access to the course with the link, whatever their status.'''
        self.channel.visibility = 'members'
        self.channel_partner_emp.action_archive()
        invite_url_emp = self.channel_partner_emp.invitation_link

        # No user logged, 'joined' and archived
        res = self.url_open(invite_url_emp)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=expired',
            "Archived 'joined' attendees cannot access 'members only' courses")

        # No user logged, 'invited' and archived
        self.channel_partner_emp.member_status = 'invited'
        self.channel_partner_emp.last_invitation_date = fields.Datetime.now()
        res = self.url_open(invite_url_emp)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=expired',
            "Archived 'invited' attendees cannot access 'members only' courses")

    def test_direct_invite_link_public_visibility(self):
        ''' Check that 'invited' attendees will be redirected to the course with public visibility'''
        self.channel_partner_emp.member_status = 'invited'
        self.channel_partner_emp.last_invitation_date = fields.Datetime.now()
        invite_url_emp = self.channel_partner_emp.invitation_link

        # No user logged.
        res = self.url_open(invite_url_emp)
        self.assertEqual(res.status_code, 200)
        url = self.parse_http_location(res.url)
        self.assertEqual(url.path, f'/slides/{self.channel.id}',
            "Invited partners should always see the public course page")

    def test_direct_invite_link_not_public_visibility(self):
        ''' Check that 'invited' attendees are redirected to courses with 'members' and 'connected' visibilities.'''
        self.channel_partner_emp.member_status = 'invited'
        self.channel_partner_emp.last_invitation_date = fields.Datetime.now()
        invite_url_emp = self.channel_partner_emp.invitation_link

        # No user logged, but access granted via parameters in url.
        self.channel.visibility = 'connected'
        res = self.url_open(invite_url_emp)
        self.assertEqual(res.status_code, 200)
        url = self.parse_http_location(res.url)
        self.assertEqual(url.path, f'/slides/{self.channel.id}',
            "Partners being invited to the course can access the course page")

        self.channel.visibility = 'members'
        res = self.url_open(invite_url_emp)
        self.assertEqual(res.status_code, 200)
        url = self.parse_http_location(res.url)
        self.assertEqual(url.path, f'/slides/{self.channel.id}',
            "Partners being invited to the course can access the course page")

        # Courses must still be published to access.
        self.channel.sudo().is_published = False
        res = self.url_open(invite_url_emp)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=no_rights',
            "Invited partners cannot access non published courses")

        # If removed from invited attendees, the link is not valid anymore.
        self.channel.sudo().is_published = True
        self.channel_partner_emp.sudo().unlink()
        res = self.url_open(invite_url_emp)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=expired',
            "Using an expired link should redirect to the main /slides page")

    def test_generic_invite_link_members_visiblity_as_archived_connected(self):
        ''' Check that connected archived attendees are not given access to 'members' courses, whatever their status.'''
        self.channel_partner_emp.action_archive()
        self.channel.visibility = 'members'

        # Connected, 'invited' and archived
        self.authenticate("user_emp", "user_emp")
        res = self.url_open(f'/slides/{self.channel.id}')
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=no_rights',
            "Archived 'invited' attendees cannot access 'members only' courses")

        # Connected, 'joined' and archived
        self.channel_partner_emp.member_status = 'joined'
        res = self.url_open(f'/slides/{self.channel.id}')
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=no_rights',
            "Archived 'joined' attendees cannot access 'members only' courses")

    def test_generic_invite_link_public_visibility(self):
        ''' Check that generic invite link for public course is accessible, even if not logged.'''
        invite_url = f"/slides/{self.channel.id}"
        res = self.url_open(invite_url)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, invite_url,
            "Public course should be accessible from its invitation link.")

    def test_generic_invite_link_not_public_visibility(self):
        ''' Check that generic route properly the (not) logged user for courses with 'members' and 'connected' visibilities.'''
        invite_url = f"/slides/{self.channel.id}"

        # No user logged
        self.channel.visibility = 'connected'
        res = self.url_open(invite_url)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=no_rights',
            "The public user has no access to connected-only courses.")

        # No user logged
        self.channel.visibility = 'members'
        res = self.url_open(invite_url)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=no_rights',
            "The public user has no access to members-only courses.")

        # User logged but not invited nor enrolled
        self.authenticate("portal", "portal")
        res = self.url_open(invite_url)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=no_rights',
            "An external user has no access to members-only courses.")

        # Logged user now has a pending invitation to the course
        self.env['slide.channel.partner'].create({
            'channel_id': self.channel.id,
            'partner_id': self.user_portal.partner_id.id,
            'member_status': 'invited'
        })

        # User logged and invited
        res = self.url_open(invite_url)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, invite_url,
            "Invited partner should be allowed the access to the course page")

    def test_invite_route_errors_handling(self):
        ''' Check that the /invite route redirects properly when an error is encountered, and current user has no rights to the course.'''
        invite_url_emp = self.channel_partner_emp.invitation_link
        invite_url_no_user = self.channel_partner_no_user.invitation_link
        self.channel.visibility = 'members'

        # Hash is wrong
        invite_url_false_hash = invite_url_emp + 'abc'
        res = self.url_open(invite_url_false_hash)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=hash_fail',
            "A wrong hash should redirect to the main /slides page")

        # Link is for another user
        self.authenticate("user_emp", "user_emp")
        res = self.url_open(invite_url_no_user)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=partner_fail',
            "Using an other user's invitation link should redirect to the course page")

        # slugification can give: "/slides/-ID" which should work, despite resulting in a negative ID
        invite_url = f'/slides/-{self.channel.id}'
        res = self.url_open(invite_url)
        self.assertEqual(res.status_code, 200)
        self.assertIn(invite_url, res.url)

        # No such channel
        max_channel_id = self.env['slide.channel'].search([], order='id desc', limit=1).id
        invite_url = f'/slides/{max_channel_id + 1}'
        res = self.url_open(invite_url)
        self.assertEqual(res.status_code, 200)
        self.assertIn('/slides?invite_error=no_channel', res.url,
            "Should have redirected to the 'no_channel' page as this channel ID does not exist")

        # Expired Link. Redirects to the main slides page.
        self.channel_partner_emp.sudo().unlink()
        res = self.url_open(invite_url_emp)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=expired',
            "Using an expired link should redirect to the main /slides page for non public courses")

    def test_members_invitation_expiration(self):
        ''' Check invitations are expired after 3 months, and that garbage collector remove appropriate records.'''
        # Let user_emp be completed
        self.slide.with_user(self.user_emp).action_mark_completed()
        self.assertEqual(self.channel_partner_emp.member_status, 'completed')
        self.assertTrue(self.channel_partner_emp.completion > 0)

        # Logged user_emp has been reinvited more than three months ago and link should be expired
        self.channel_partner_emp.write({
            'member_status': 'invited',
            'last_invitation_date': fields.Datetime.subtract(fields.Datetime.now(), months=3, days=5)
        })
        self.channel.visibility = 'members'
        res = self.url_open(self.channel_partner_emp.invitation_link)
        self.assertEqual(res.status_code, 200)
        self.assertURLEqual(res.url, '/slides?invite_error=expired',
            "Using an expired link should redirect to the main /slides page")

        # Let user_portal be invited, with completion = 0, outdated
        outdated_portal_membership_values = {
            'channel_id': self.channel.id,
            'partner_id': self.user_portal.partner_id.id,
            'member_status': 'invited',
            'last_invitation_date': fields.Datetime.subtract(fields.Datetime.now(), months=3, days=5)
        }
        channel_partner_portal = self.env['slide.channel.partner'].create(outdated_portal_membership_values)

        # Clean expired records with no progress and 'invited'
        self.env['slide.channel.partner']._gc_slide_channel_partner()
        self.assertTrue(self.channel_partner_emp.exists(), 'Memberships with progress should never be removed.')
        self.assertFalse(channel_partner_portal.exists(), 'Expired invitations with no progress should be removed by the GC.')
        self.assertTrue(self.channel_partner_no_user.exists(), 'Joined members should never be removed.')

        channel_partner_portal = self.env['slide.channel.partner'].create(outdated_portal_membership_values)
        channel_partner_portal.action_archive()
        self.channel_partner_emp.action_archive()
        self.channel_partner_no_user.member_status = 'invited'

        # Clean outdated archived records as well, and ones 'invited' with no last_invitation_date
        self.env['slide.channel.partner']._gc_slide_channel_partner()
        self.assertFalse(channel_partner_portal.exists(), 'Expired invitations should be removed, even if archived')
        self.assertTrue(self.channel_partner_emp.exists(), 'Memberships with progress should never be removed, even archived.')
        self.assertFalse(self.channel_partner_no_user.exists(), 'No Last Invitation Date is considered as expired for invited members')

    def test_invite_email_translation(self):
        "Make sure that invitation emails are translated if unchanged when adding attendees to a course"
        self.env['res.lang']._activate_lang('fr_FR')
        jean = self.env['res.partner'].create({'name': 'Jean', 'lang': 'fr_FR'})

        template = self.env['mail.template'].create({
            'subject': 'Hello',
            'body_html': 'en',
        })
        template.lang = '{{ object.partner_id.lang }}'
        template.render_model = 'slide.channel.partner'

        template.with_context(lang='fr_FR').subject = 'Bonjour'
        template.with_context(lang='fr_FR').body_html = 'fr'

        channel = self.env['slide.channel'].create({'name': 'Test Course'})
        slide_channel_jean = self.env['slide.channel.partner'].create({
            'channel_id': channel.id,
            'partner_id': jean.id,
        })

        wizard = self.env['slide.channel.invite'].create({
            'send_email': True,
            'partner_ids': [jean.id],
            'channel_id': channel.id,
            'template_id': template.id,
        })

        mail_vals = wizard._prepare_mail_values(slide_channel_jean)
        self.assertEqual(
            mail_vals['body_html'],
            '<p>fr</p>',
            "Mail body should have been translated into recipient's language"
        )
        self.assertEqual(
            mail_vals['subject'],
            'Bonjour',
            "Mail subject should have been translated into recipient's language"
        )

    @users('user_emp', 'portal')
    def test_channel_visibility_on_website(self):
        """Check visibility of channels for Internal/Portal users."""
        visible_channel = self.env['slide.channel'].search([
            ('id', 'in', self.available_channels.ids),
            ('is_visible', '=', True),
        ])
        self.assertIn(self.channel, visible_channel)
        self.assertIn(self.channel_connect, visible_channel)
        self.assertNotIn(self.channel_members, visible_channel)
        self.assertNotIn(self.channel_link, visible_channel)

        # Check the inverse condition
        hidden_channel = self.env['slide.channel'].search([
            ('id', 'in', self.available_channels.ids),
            ('is_visible', '!=', True),
        ])
        self.assertIn(self.channel_link, hidden_channel)
        self.assertNotIn(self.channel, hidden_channel)
        self.assertNotIn(self.channel_connect, hidden_channel)

        # Add attendee to channel
        self.channel_link._action_add_members(self.env.user.partner_id)
        self.channel_members._action_add_members(self.env.user.partner_id)

        visible_channel = self.env['slide.channel'].search([
            ('id', 'in', self.available_channels.ids),
            ('is_visible', '=', True),
        ])
        self.assertIn(self.channel_members, visible_channel)
        self.assertIn(self.channel_link, visible_channel)
        self.assertEqual(
            self.env['slide.channel'].search([('is_visible', '=', True)]),
            self.env['slide.channel'].search([('is_visible', '!=', False)]),
        )

    @users('user_public')
    def test_channel_visibility_public_user(self):
        """Check visibility of channels for Public users."""
        visible_channel = self.env['slide.channel'].search([
            ('id', 'in', self.available_channels.ids),
            ('is_visible', '=', True),
        ])
        self.assertIn(self.channel, visible_channel)
        self.assertNotIn(self.channel_connect, visible_channel)
        self.assertNotIn(self.channel_members, visible_channel)
        self.assertNotIn(self.channel_link, visible_channel)

        # Check the inverse condition
        hidden_channel = self.env['slide.channel'].search([
            ('id', 'in', self.available_channels.ids),
            ('is_visible', '!=', True),
        ])
        self.assertIn(self.channel_link, hidden_channel)
        self.assertEqual(
            self.env['slide.channel'].search([('is_visible', '=', True)]),
            self.env['slide.channel'].search([('is_visible', '!=', False)]),
        )

    def test_slide_slide_notification_link(self):
        """Check link shared in content notification mail redirect to appropriate content"""
        self.authenticate("portal", "portal")

        url = self.slide.website_share_url
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertURLEqual(
            response.url,
            f"/slides/{self.channel.id}?access_error=course_content&access_error_slide_id={self.slide.id}&access_error_slide_name=How+to+understand+membership",
            "Unathorized user cannot access non published content",
        )

        # Adding attendee to the course
        self.channel._action_add_members(self.user_portal.partner_id)
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertURLEqual(
            response.url,
            f"/slides/slide/{self.env['ir.http']._slug(self.slide)}",
            "Should redirect to the slide page",
        )
