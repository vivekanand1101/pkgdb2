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

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '..'))

import pkgdb2
from tests import (Modeltests, create_package_acl)


class FlaskUiPackagersTest(Modeltests):
    """ Flask tests. """

    def setUp(self):
        """ Set up the environnment, ran before every tests. """
        super(FlaskUiPackagersTest, self).setUp()

        pkgdb2.APP.config['TESTING'] = True
        pkgdb2.SESSION = self.session
        pkgdb2.ui.SESSION = self.session
        pkgdb2.ui.acls.SESSION = self.session
        pkgdb2.ui.admin.SESSION = self.session
        pkgdb2.ui.collections.SESSION = self.session
        pkgdb2.ui.packagers.SESSION = self.session
        pkgdb2.ui.packages.SESSION = self.session
        self.app = pkgdb2.APP.test_client()

    def test_list_packagers(self):
        """ Test the list_packagers function. """

        output = self.app.get('/packagers/')
        self.assertEqual(output.status_code, 200)
        self.assertTrue('<h1>Search packagers</h1>' in output.data)

        output = self.app.get('/packagers/?limit=abc&page=def')
        self.assertEqual(output.status_code, 200)
        self.assertTrue('<h1>Search packagers</h1>' in output.data)

    def test_packager_info(self):
        """ Test the packager_info function. """
        create_package_acl(self.session)

        output = self.app.get('/packager/pingou/')
        self.assertEqual(output.status_code, 200)
        self.assertTrue('pingou</h1>' in output.data)
        self.assertTrue('<a href="/package/rpms/guake/">' in output.data)

        output = self.app.get('/packager/random/')
        self.assertEqual(output.status_code, 200)
        self.assertTrue(
            '<li class="errors">No packager of this name found.</li>'
            in output.data)

    def test_packager_requests(self):
        """ Test the packager_requests function. """

        output = self.app.get('/packager/pingou/requests')
        self.assertEqual(output.status_code, 200)
        self.assertTrue("<h1>pingou's requests</h1>" in output.data)
        self.assertTrue(
            'Restrict to package: <input type="text" name="package" />'
            in output.data)

        output = self.app.get(
            'packager/pingou/requests?page=abc&limit=def&status=ghi&package=test')
        self.assertEqual(output.status_code, 200)
        self.assertTrue("<h1>pingou's requests</h1>" in output.data)
        self.assertTrue(
            'Restrict to package: <input type="text" name="package" />'
            in output.data)
        self.assertTrue(
            'class="errors">Incorrect limit provided, using default</'
            in output.data)
        self.assertTrue(
            '<li class="errors">No package exists</li>' in output.data)

        output = self.app.get('packager/pingou/requests?package=guake')
        self.assertEqual(output.status_code, 200)
        self.assertTrue("<h1>pingou's requests</h1>" in output.data)
        self.assertTrue(
            'Restrict to package: <input type="text" name="package" />'
            in output.data)


if __name__ == '__main__':
    SUITE = unittest.TestLoader().loadTestsFromTestCase(FlaskUiPackagersTest)
    unittest.TextTestRunner(verbosity=2).run(SUITE)
