# -*- coding: utf-8 -*-
#
# Copyright © 2013  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions
# of the GNU General Public License v.2, or (at your option) any later
# version.  This program is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY expressed or implied, including the
# implied warranties of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.  You
# should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# Any Red Hat trademarks that are incorporated in the source
# code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission
# of Red Hat, Inc.
#

'''
pkgdb tests for the Flask application.
'''

__requires__ = ['SQLAlchemy >= 0.8']
import pkg_resources

import unittest
import sys
import os

from mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '..'))

import pkgdb2
from tests import (
    Modeltests, FakeFasUser, FakeFasUserAdmin, user_set,
    create_collection, create_package, create_admin_actions,
)


class FlaskUiAdminTest(Modeltests):
    """ Flask tests. """

    def setUp(self):
        """ Set up the environnment, ran before every tests. """
        super(FlaskUiAdminTest, self).setUp()

        pkgdb2.APP.config['TESTING'] = True
        pkgdb2.SESSION = self.session
        pkgdb2.ui.SESSION = self.session
        pkgdb2.ui.acls.SESSION = self.session
        pkgdb2.ui.admin.SESSION = self.session
        pkgdb2.ui.collections.SESSION = self.session
        pkgdb2.ui.packagers.SESSION = self.session
        pkgdb2.ui.packages.SESSION = self.session
        self.app = pkgdb2.APP.test_client()

    @patch('pkgdb2.is_admin')
    def test_admin(self, login_func):
        """ Test the admin function. """
        login_func.return_value = None

        user = FakeFasUserAdmin()
        with user_set(pkgdb2.APP, user):
            output = self.app.get('/admin/')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Admin interface</h1>' in output.data)

    @patch('pkgdb2.is_admin')
    def test_admin_log(self, login_func):
        """ Test the admin_log function. """
        login_func.return_value = None

        user = FakeFasUserAdmin()
        with user_set(pkgdb2.APP, user):
            output = self.app.get('/admin/log/')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Logs</h1>' in output.data)
            self.assertTrue(
                'Restrict to package: <input type="text" name="package" />'
                in output.data)

            output = self.app.get(
                '/admin/log/?page=abc&limit=def&from_date=ghi&package=test')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Logs</h1>' in output.data)
            self.assertTrue(
                'Restrict to package: <input type="text" name="package" />'
                in output.data)
            self.assertTrue(
                'class="errors">Incorrect limit provided, using default</'
                in output.data)
            self.assertTrue(
                'class="errors">Incorrect from_date provided, using default</'
                in output.data)
            self.assertTrue(
                '<li class="errors">No package exists</li>' in output.data)

            output = self.app.get('/admin/log/?from_date=2013-10-19')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Logs</h1>' in output.data)
            self.assertTrue(
                'Restrict to package: <input type="text" name="package" />'
                in output.data)
            self.assertTrue(
                '<p class=\'error\'>No logs found in the database.</p>'
                in output.data)

    @patch('pkgdb2.is_admin')
    def test_admin_actions(self, login_func):
        """ Test the admin_actions function. """
        login_func.return_value = None

        user = FakeFasUserAdmin()
        with user_set(pkgdb2.APP, user):
            output = self.app.get('/admin/actions/')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Actions</h1>' in output.data)
            self.assertTrue(
                'Restrict to package: <input type="text" name="package" />'
                in output.data)

            output = self.app.get(
                '/admin/actions/?page=abc&limit=def&status=ghi&package=test')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Actions</h1>' in output.data)
            self.assertTrue(
                'Restrict to package: <input type="text" name="package" />'
                in output.data)
            self.assertTrue(
                'class="errors">Incorrect limit provided, using default</'
                in output.data)
            self.assertTrue(
                '<li class="errors">No package exists</li>' in output.data)

            output = self.app.get('/admin/actions/?package=guake')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Actions</h1>' in output.data)
            self.assertTrue(
                'Restrict to package: <input type="text" name="package" />'
                in output.data)
            self.assertTrue(
                '<p>No actions found</p>' in output.data)

            # Create some actions to see
            create_collection(pkgdb2.SESSION)
            create_package(pkgdb2.SESSION)
            create_admin_actions(pkgdb2.SESSION, n=2)

            # set the pagination
            pkgdb2.APP.config['ITEMS_PER_PAGE'] = 1

            # Check the list
            output = self.app.get('/admin/actions/?status=all')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Actions</h1>' in output.data)
            self.assertTrue(
                'Restrict to package: <input type="text" name="package" />'
                in output.data)
            # 3 actions = 3 pages
            self.assertTrue('<td>1 / 3</td>' in output.data)

            # Reset the pagination
            pkgdb2.APP.config['ITEMS_PER_PAGE'] = 50


    @patch('pkgdb2.fas_login_required')
    def test_admin_action_edit_status(self, login_func):
        """ Test the admin_action_edit_status function. """
        login_func.return_value = None

        user = FakeFasUser()

        with user_set(pkgdb2.APP, user):
            output = self.app.get('/admin/action/1/status')
            self.assertEqual(output.status_code, 302)

        user = FakeFasUserAdmin()

        with user_set(pkgdb2.APP, user):
            output = self.app.get('/admin/action/1/status')
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<li class="errors">No action found with this identifier.</li>'
                in output.data)

        # Have another test create a pending Admin Action
        from test_flask_ui_packages import FlaskUiPackagesTest
        uitest = FlaskUiPackagesTest('test_package_request_branch')
        uitest.session = self.session
        uitest.app = self.app
        uitest.test_package_request_branch()

        with user_set(pkgdb2.APP, user):
            # Before
            # No action Pending
            output = self.app.get('/admin/actions/?status=Pending')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Actions</h1>' in output.data)
            self.assertFalse(
                '<td class="col_odd">request.branch</td>' in output.data)
            self.assertFalse(
                '<td class="col_odd" >Awaiting Review</td>' in output.data)

            # But one action in total
            output = self.app.get('/admin/actions/?status=All')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Actions</h1>' in output.data)
            self.assertTrue(
                '<td class="col_odd">request.branch</td>' in output.data)
            self.assertEqual(
                output.data.count('<td class="col_odd">request.branch</td>'),
                1
            )
            self.assertTrue(
                '<td class="col_odd" >\n        Awaiting Review\n      </td>'
                in output.data)

            # One action Awaiting Review
            output = self.app.get('/admin/actions/?status=Awaiting Review')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Actions</h1>' in output.data)
            self.assertTrue(
                '<td class="col_odd">request.branch</td>' in output.data)
            self.assertEqual(
                output.data.count('<td class="col_odd">request.branch</td>'),
                1
            )
            self.assertTrue(
                '<td class="col_odd" >\n        Awaiting Review\n      </td>'
                in output.data)

            # Update
            output = self.app.get('/admin/action/1/status')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Update admin action: 1</h1>' in output.data)

            csrf_token = output.data.split(
                'name="csrf_token" type="hidden" value="')[1].split('">')[0]

            data = {
                'status': 'Approved',
                'csrf_token': csrf_token,
            }

            output = self.app.post('/admin/action/1/status', data=data,
                                   follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<li class="message">user: admin updated action: 1 of guake '
                'from `Awaiting Review` to `Approved`</li>' in output.data)

            # After
            output = self.app.get('/admin/actions/')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<h1>Actions</h1>' in output.data)
            self.assertFalse(
                '<td class="col_odd">request.branch</td>' in output.data)


if __name__ == '__main__':
    SUITE = unittest.TestLoader().loadTestsFromTestCase(FlaskUiAdminTest)
    unittest.TextTestRunner(verbosity=2).run(SUITE)
