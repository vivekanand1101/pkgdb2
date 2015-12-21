# -*- coding: utf-8 -*-
#
# Copyright © 2015  Red Hat, Inc.
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
pkgdb tests for orphaning/retiring a package whose PoC is a group.
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
import pkgdb2.lib as pkgdblib
import pkgdb2.lib.model as model
from tests import Modeltests, FakeFasUser, FakeFasUserAdmin, \
    create_collection, create_package


class PkgdbOrphanGrouptests(Modeltests):
    """ pkgdb orphan group tests. """

    @patch('pkgdb2.lib.utils.set_bugzilla_owner')
    def test_orphan_group_package(self, bz_owner):
        """ Test the is_pkgdb_admin function of pkgdb2. """
        bz_owner.return_value = None

        create_collection(self.session)
        create_package(self.session)

        guake_pkg = model.Package.by_name(self.session, 'rpms', 'guake')
        fedocal_pkg = model.Package.by_name(self.session, 'rpms', 'fedocal')

        f18_collec = model.Collection.by_name(self.session, 'f18')
        devel_collec = model.Collection.by_name(self.session, 'master')

        # Pkg: guake - Collection: master - Approved
        pkgltg = model.PackageListing(
            point_of_contact='group::infra-sig',
            status='Approved',
            package_id=guake_pkg.id,
            collection_id=devel_collec.id,
        )
        self.session.add(pkgltg)

        # Pkg: guake - Collection: f18 - Approved
        pkgltg = model.PackageListing(
            point_of_contact='pingou',
            status='Approved',
            package_id=guake_pkg.id,
            collection_id=f18_collec.id,
        )
        self.session.add(pkgltg)

        # Pkg: fedocal - Collection: master - Approved
        pkgltg = model.PackageListing(
            point_of_contact='group::infra-sig',
            status='Approved',
            package_id=fedocal_pkg.id,
            collection_id=devel_collec.id,
        )
        self.session.add(pkgltg)

        user = FakeFasUser()

        # Orphan allowed (?)
        msg = pkgdblib.update_pkg_status(
            self.session, namespace='rpms', pkg_name='fedocal',
            pkg_branch='master', status='Orphaned', user=user, poc='orphan')

        self.assertEqual(
            msg,
            'user: pingou updated package: fedocal status from: Approved to '
            'Orphaned on branch: master')

        # Retired blocked
        msg = pkgdblib.update_pkg_status(
            self.session, namespace='rpms', pkg_name='guake',
            pkg_branch='master', status='Retired', user=user, poc='orphan')

        self.assertEqual(
            msg,
            'user: pingou updated package: guake status from: Approved to '
            'Retired on branch: master')


if __name__ == '__main__':
    SUITE = unittest.TestLoader().loadTestsFromTestCase(PkgdbOrphanGrouptests)
    unittest.TextTestRunner(verbosity=2).run(SUITE)
