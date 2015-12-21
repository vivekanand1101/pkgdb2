# -*- coding: utf-8 -*-
#
# Copyright © 2013-2014  Red Hat, Inc.
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
pkgdb tests for the Collection object.
'''

__requires__ = ['SQLAlchemy >= 0.8']
import pkg_resources

import mock
import unittest
import sys
import os

from datetime import date

from mock import patch
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '..'))

import pkgdb2
import pkgdb2.lib as pkgdblib
from tests import (FakeFasUser, FakeFasUserAdmin, Modeltests,
                   FakeFasGroupValid, FakeFasGroupInvalid,
                   create_collection, create_package_acl,
                   create_package_acl2, create_package_critpath)


class PkgdbLibtests(Modeltests):
    """ PkgdbLib tests. """

    @patch('pkgdb2.lib.utils.get_bz_email_user')
    def test_add_package(self, mock_func):
        """ Test the add_package function. """
        create_collection(self.session)

        mock_func.return_value = 1

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='test',
                          pkg_summary='test package',
                          pkg_description='test description',
                          pkg_status='Approved',
                          pkg_collection='f18',
                          pkg_poc='ralph',
                          pkg_review_url=None,
                          pkg_upstream_url='http://example.org',
                          user=FakeFasUser()
                          )
        self.session.rollback()

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='test',
                          pkg_summary='test package',
                          pkg_description='test description',
                          pkg_status='Approved',
                          pkg_collection='f18',
                          pkg_poc='group::tests',
                          pkg_review_url=None,
                          pkg_upstream_url='http://example.org',
                          user=FakeFasUserAdmin()
                          )
        self.session.rollback()

        pkgdb2.lib.utils.get_packagers = mock.MagicMock()
        pkgdb2.lib.utils.get_packagers.reset_mock()

        # Configuration to query FAS isn't set
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_summary='Drop down terminal',
                          pkg_description='Drop down terminal desc',
                          pkg_status='Approved',
                          pkg_collection='f18',
                          pkg_poc='ralph',
                          pkg_review_url=None,
                          pkg_upstream_url='http://guake.org',
                          user=FakeFasUserAdmin())

        pkgdb2.lib.utils.get_packagers = mock.MagicMock()
        pkgdb2.lib.utils.get_packagers.return_value = ['pingou']

        # 'Ralph' is not in the packager group
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_summary='Drop down terminal',
                          pkg_description='Drop down terminal desc',
                          pkg_status='Approved',
                          pkg_collection='f18',
                          pkg_poc='ralph',
                          pkg_review_url=None,
                          pkg_upstream_url='http://guake.org',
                          user=FakeFasUserAdmin())

        pkgdb2.lib.utils.get_fas_group = mock.MagicMock()
        pkgdb2.lib.utils.get_fas_group.return_value = FakeFasGroupInvalid

        # Invalid FAS group, not ending with -sig
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='fedocal',
                          pkg_summary='web calendar for Fedora',
                          pkg_description='Web-based calendar system',
                          pkg_status='Approved',
                          pkg_collection='master, f18',
                          pkg_poc='group::infra-group',
                          pkg_review_url=None,
                          pkg_upstream_url=None,
                          user=FakeFasUserAdmin())

        # Invalid FAS group returned
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='fedocal',
                          pkg_summary='web calendar for Fedora',
                          pkg_description='Web-based calendar system',
                          pkg_status='Approved',
                          pkg_collection='master, f18',
                          pkg_poc='group::infra-sig',
                          pkg_review_url=None,
                          pkg_upstream_url=None,
                          user=FakeFasUserAdmin())

        pkgdb2.lib.utils.get_packagers = mock.MagicMock()
        pkgdb2.lib.utils.get_packagers.return_value = ['ralph', 'pingou']

        msg = pkgdblib.add_package(self.session,
                                   namespace='rpms',
                                   pkg_name='guake',
                                   pkg_summary='Drop down terminal',
                                   pkg_description='Drop down terminal desc',
                                   pkg_status='Approved',
                                   pkg_collection='f18',
                                   pkg_poc='ralph',
                                   pkg_review_url=None,
                                   pkg_upstream_url='http://guake.org',
                                   user=FakeFasUserAdmin())
        self.assertEqual(msg, 'Package created')
        self.session.commit()
        packages = pkgdblib.model.Package.all(self.session)
        self.assertEqual(1, len(packages))
        self.assertEqual('guake', packages[0].name)

        pkgdblib.add_package(self.session,
                             namespace='rpms',
                             pkg_name='geany',
                             pkg_summary='GTK IDE',
                             pkg_description='Lightweight IDE for GNOME',
                             pkg_status='Approved',
                             pkg_collection='master, f18',
                             pkg_poc='ralph',
                             pkg_review_url=None,
                             pkg_upstream_url=None,
                             user=FakeFasUserAdmin())
        self.session.commit()
        packages = pkgdblib.model.Package.all(self.session)
        self.assertEqual(2, len(packages))
        self.assertEqual('guake', packages[0].name)
        self.assertEqual('geany', packages[1].name)

        pkgdb2.lib.utils.get_fas_group = mock.MagicMock()
        pkgdb2.lib.utils.get_fas_group.return_value = FakeFasGroupValid

        pkgdblib.add_package(self.session,
                             namespace='rpms',
                             pkg_name='fedocal',
                             pkg_summary='web calendar for Fedora',
                             pkg_description='Web-based calendar system',
                             pkg_status='Approved',
                             pkg_collection='master, f18',
                             pkg_poc='group::infra-sig',
                             pkg_review_url=None,
                             pkg_upstream_url=None,
                             user=FakeFasUserAdmin())
        self.session.commit()
        packages = pkgdblib.model.Package.all(self.session)
        self.assertEqual(3, len(packages))
        self.assertEqual('guake', packages[0].name)
        self.assertEqual('geany', packages[1].name)
        self.assertEqual('fedocal', packages[2].name)

    def test_get_acl_package(self):
        """ Test the get_acl_package function. """
        create_package_acl(self.session)

        packages = pkgdblib.model.Package.all(self.session)
        self.assertEqual(4, len(packages))
        self.assertEqual('guake', packages[0].name)

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(len(pkg_acl), 2)
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].acls[0].fas_name, 'pingou')

        # No EOL collection, so no change
        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake', eol=True)
        self.assertEqual(len(pkg_acl), 2)
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].acls[0].fas_name, 'pingou')

        pkg_acl = pkgdblib.get_acl_package(
            self.session, 'rpms', 'guake', pkg_clt='master')[0]
        self.assertEqual(pkg_acl.collection.branchname, 'master')
        self.assertEqual(pkg_acl.package.name, 'guake')
        self.assertEqual(pkg_acl.acls[0].fas_name, 'pingou')

        # Package does not exist
        self.assertRaises(NoResultFound,
                          pkgdblib.get_acl_package,
                          self.session,
                          'rpms',
                          'test',
                          'master')

        # Collection does not exist
        pkg_acl = pkgdblib.get_acl_package(
            self.session, 'rpms', 'guake', 'unknown')
        self.assertEqual(pkg_acl, [])

    @patch('pkgdb2.lib.utils.get_bz_email_user')
    def test_set_acl_package(self, mock_func):
        """ Test the set_acl_package function. """
        self.test_add_package()

        mock_func.return_value = 1

        # Not allowed to set acl on non-existant package
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.set_acl_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='test',
                          pkg_branch='f17',
                          pkg_user='pingou',
                          acl='nothing',
                          status='Appr',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # Not allowed to set non-existant collection
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.set_acl_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f16',
                          pkg_user='pingou',
                          acl='nothing',
                          status='Appr',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # Not allowed to set non-existant status
        self.assertRaises(IntegrityError,
                          pkgdblib.set_acl_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          acl='commit',
                          pkg_user='pingou',
                          status='Appro',
                          user=FakeFasUserAdmin(),
                          )
        self.session.rollback()

        # Not allowed to set non-existant acl
        self.assertRaises(IntegrityError,
                          pkgdblib.set_acl_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          pkg_user='pingou',
                          acl='nothing',
                          status='Approved',
                          user=FakeFasUserAdmin(),
                          )
        self.session.rollback()

        # Not allowed to set acl for yourself
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.set_acl_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          pkg_user='pingou',
                          acl='approveacls',
                          status='Approved',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # Not allowed to set acl for someone else
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.set_acl_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          pkg_user='ralph',
                          acl='commit',
                          status='Approved',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # Not allowed to set acl approveacl to a group
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.set_acl_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          pkg_user='group::perl',
                          acl='approveacls',
                          status='Approved',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # Group must ends with -sig
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.set_acl_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          pkg_user='group::perl',
                          acl='commit',
                          status='Approved',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # Group cannot have approveacls
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.set_acl_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          pkg_user='group::gtk-sig',
                          acl='approveacls',
                          status='Approved',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        ## Working ones

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(len(pkg_acl[0].acls), 4)

        # Adding auto-approve ACL should work fine
        user = FakeFasUser()
        user.username = 'blahblah'
        pkgdblib.set_acl_package(self.session,
                                 namespace='rpms',
                                 pkg_name='guake',
                                 pkg_branch='f18',
                                 pkg_user='blahblah',
                                 acl='watchbugzilla',
                                 status='Approved',
                                 user=user,
                                 )
        self.session.commit()

        # Adding non-auto-approve ACL should not work fine
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.set_acl_package,
            self.session,
            namespace='rpms',
            pkg_name='guake',
            pkg_branch='f18',
            pkg_user='blahblah',
            acl='approveacls',
            status='Approved',
            user=user,
        )
        self.session.commit()

        # You can ask for new ACLs
        pkgdblib.set_acl_package(self.session,
                                 namespace='rpms',
                                 pkg_name='guake',
                                 pkg_branch='f18',
                                 pkg_user='pingou',
                                 acl='approveacls',
                                 status='Awaiting Review',
                                 user=FakeFasUser(),
                                 )
        self.session.commit()

        # You can obsolete your own ACLs
        pkgdblib.set_acl_package(self.session,
                                 namespace='rpms',
                                 pkg_name='guake',
                                 pkg_branch='f18',
                                 pkg_user='pingou',
                                 acl='approveacls',
                                 status='Obsolete',
                                 user=FakeFasUser(),
                                 )
        self.session.commit()

        # You can remove your own ACLs
        pkgdblib.set_acl_package(self.session,
                                 namespace='rpms',
                                 pkg_name='guake',
                                 pkg_branch='f18',
                                 pkg_user='pingou',
                                 acl='approveacls',
                                 status='Removed',
                                 user=FakeFasUser(),
                                 )
        self.session.commit()

        # You can approve your own ACLs on a new branch
        pkgdblib.set_acl_package(self.session,
                                 namespace='rpms',
                                 pkg_name='guake',
                                 pkg_branch='el6',
                                 pkg_user='pingou',
                                 acl='approveacls',
                                 status='Awaiting Review',
                                 user=FakeFasUser(),
                                 )
        self.session.commit()

        # An admin can approve you ACLs
        pkgdblib.set_acl_package(self.session,
                                 namespace='rpms',
                                 pkg_name='guake',
                                 pkg_branch='f18',
                                 pkg_user='pingou',
                                 acl='commit',
                                 status='Approved',
                                 user=FakeFasUserAdmin(),
                                 )
        self.session.commit()

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(len(pkg_acl[0].acls), 7)

    @patch('pkgdb2.lib.utils')
    def test_update_pkg_poc(self, mock_func):
        """ Test the update_pkg_poc function. """
        self.test_add_package()

        mock_func.get_packagers.return_value = [
            'pingou', 'toshio', 'ralph']
        mock_func.get_bz_email_user.return_value = 1
        mock_func.get_fas_group.return_value = FakeFasGroupValid()

        # Package must exists
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_poc,
                          self.session,
                          namespace='rpms',
                          pkg_name='test',
                          pkg_branch='f17',
                          user=FakeFasUser(),
                          pkg_poc='toshio',
                          )
        self.session.rollback()

        # Collection must exists
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_poc,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f16',
                          user=FakeFasUser(),
                          pkg_poc='toshio',
                          )
        self.session.rollback()

        # User must be the actual Point of Contact (or an admin of course,
        # or part of the group)
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_poc,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          user=FakeFasUser(),
                          pkg_poc='toshio',
                          )
        self.session.rollback()

        # Groups must end with -sig
        user = FakeFasUser()
        user.username = 'ralph'
        # Change PoC to a group
        pkgdblib.update_pkg_poc(
            self.session,
            namespace='rpms',
            pkg_name='guake',
            pkg_branch='f18',
            user=user,
            pkg_poc='group::perl-sig',
        )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'group::perl-sig')

        # User must be in the group it takes the PoC from
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_poc,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          user=user,
                          pkg_poc='ralph',
                          )
        self.session.rollback()

        # User must be in the POC of the branch specified
        user = FakeFasUser()
        user.username = 'ralph'
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_poc,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          user=user,
                          pkg_poc='orphan',
                          former_poc='toshio',
                          )

        user.groups.append('perl-sig')
        pkgdblib.update_pkg_poc(
            self.session,
            namespace='rpms',
            pkg_name='guake',
            pkg_branch='f18',
            user=user,
            pkg_poc='ralph',
        )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'ralph')

        pkgdb2.lib.utils.get_packagers = mock.MagicMock()
        pkgdb2.lib.utils.get_packagers.return_value = ['pingou', 'toshio']

        # PoC can change PoC
        user = FakeFasUser()
        user.username = 'ralph'
        pkgdblib.update_pkg_poc(self.session,
                                namespace='rpms',
                                pkg_name='guake',
                                pkg_branch='f18',
                                user=user,
                                pkg_poc='toshio',
                                )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'toshio')

        # PoC must be a packager, even for admin
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_poc,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          user=FakeFasUserAdmin,
                          pkg_poc='kevin',
                          )
        self.session.rollback()

        pkgdb2.lib.utils.get_packagers = mock.MagicMock()
        pkgdb2.lib.utils.get_packagers.return_value = ['pingou', 'kevin']

        # Admin can change PoC
        pkgdblib.update_pkg_poc(self.session,
                                namespace='rpms',
                                pkg_name='guake',
                                pkg_branch='f18',
                                user=FakeFasUserAdmin(),
                                pkg_poc='kevin',
                                )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'kevin')

        # Orphan -> status changed to Orphaned
        user = FakeFasUser()
        user.username = 'kevin'
        pkgdblib.update_pkg_poc(self.session,
                                namespace='rpms',
                                pkg_name='guake',
                                pkg_branch='f18',
                                user=user,
                                pkg_poc='orphan',
                                )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'orphan')
        self.assertEqual(pkg_acl[0].status, 'Orphaned')

        # Take orphaned package -> status changed to Approved
        pkgdblib.update_pkg_poc(self.session,
                                namespace='rpms',
                                pkg_name='guake',
                                pkg_branch='f18',
                                user=FakeFasUser(),
                                pkg_poc=FakeFasUser().username,
                                )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'pingou')
        self.assertEqual(pkg_acl[0].status, 'Approved')

    def test_create_session(self):
        """ Test the create_session function. """
        session = pkgdblib.create_session('sqlite:///:memory:')
        self.assertTrue(session is not None)

    def test_search_package(self):
        """ Test the search_package function. """
        self.test_add_package()
        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='gu*',
                                       pkg_branch='f18',
                                       pkg_poc=None,
                                       orphaned=None,
                                       status=None,
                                       )
        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0].name, 'guake')
        self.assertEqual(pkgs[0].upstream_url, 'http://guake.org')

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='g*',
                                       pkg_branch='f18',
                                       pkg_poc=None,
                                       orphaned=None,
                                       status=None,
                                       )
        self.assertEqual(len(pkgs), 2)
        self.assertEqual(pkgs[0].name, 'geany')
        self.assertEqual(pkgs[1].name, 'guake')

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='g*',
                                       pkg_branch='f18',
                                       pkg_poc=None,
                                       orphaned=None,
                                       status=None,
                                       limit=1
                                       )
        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0].name, 'geany')

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='g*',
                                       pkg_branch='f18',
                                       pkg_poc=None,
                                       orphaned=None,
                                       status=None,
                                       limit=1,
                                       page=1
                                       )
        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0].name, 'geany')

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='g*',
                                       pkg_branch='f18',
                                       pkg_poc=None,
                                       orphaned=None,
                                       status=None,
                                       limit=1,
                                       page=2
                                       )
        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0].name, 'guake')

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='g*',
                                       pkg_branch='f18'
                                       )
        self.assertEqual(len(pkgs), 2)
        self.assertEqual(pkgs[0].name, 'geany')
        self.assertEqual(pkgs[1].name, 'guake')

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='docker',
                                       pkg_name='g*',
                                       pkg_branch='f18',
                                       )
        self.assertEqual(len(pkgs), 0)

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='g*',
                                       pkg_branch='f18',
                                       pkg_poc=None,
                                       orphaned=None,
                                       status=None,
                                       limit=2,
                                       page=2
                                       )
        self.assertEqual(len(pkgs), 0)

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='g*',
                                       pkg_branch='f18',
                                       pkg_poc=None,
                                       orphaned=None,
                                       status=None,
                                       page=2
                                       )
        self.assertEqual(len(pkgs), 0)

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='gu*',
                                       pkg_branch='f18',
                                       pkg_poc=None,
                                       orphaned=True,
                                       status=None,
                                       )
        self.assertEqual(len(pkgs), 0)

        pkgs = pkgdblib.search_package(self.session,
                                       namespace='rpms',
                                       pkg_name='gu*',
                                       pkg_branch='f18',
                                       pkg_poc=None,
                                       orphaned=None,
                                       status='Retired',
                                       )
        self.assertEqual(len(pkgs), 0)

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.search_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='g*',
                          pkg_branch='f18',
                          pkg_poc=None,
                          orphaned=None,
                          status=None,
                          limit='a'
                          )

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.search_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='g*',
                          pkg_branch='f18',
                          pkg_poc=None,
                          orphaned=None,
                          status=None,
                          page='a'
                          )

    def test_update_pkg_status(self):
        """ Test the update_pkg_status function. """
        create_package_acl(self.session)

        # Wrong package
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_status,
                          self.session,
                          namespace='rpms',
                          pkg_name='test',
                          pkg_branch='f17',
                          status='Retired',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # Wrong collection
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_status,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f16',
                          status='Orphaned',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # User not allowed to retire the package on f18
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_status,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          status='Retired',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # Wrong status
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_status,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          status='Depreasdcated',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # User not allowed to change status to Allowed
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_status,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='f18',
                          status='Allowed',
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        # Admin can retire package
        pkgdblib.update_pkg_status(self.session,
                                   namespace='rpms',
                                   pkg_name='guake',
                                   pkg_branch='f18',
                                   status='Retired',
                                   user=FakeFasUserAdmin()
                                   )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'orphan')
        self.assertEqual(pkg_acl[0].status, 'Retired')

        # User can orphan package
        pkgdblib.update_pkg_status(self.session,
                                   namespace='rpms',
                                   pkg_name='guake',
                                   pkg_branch='master',
                                   status='Orphaned',
                                   user=FakeFasUser()
                                   )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'orphan')
        self.assertEqual(pkg_acl[0].status, 'Retired')
        self.assertEqual(pkg_acl[1].collection.branchname, 'master')
        self.assertEqual(pkg_acl[1].package.name, 'guake')
        self.assertEqual(pkg_acl[1].point_of_contact, 'orphan')
        self.assertEqual(pkg_acl[1].status, 'Orphaned')

        # Admin must give a poc when un-orphan/un-retire a package
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_status,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='master',
                          status='Approved',
                          user=FakeFasUserAdmin()
                          )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'orphan')
        self.assertEqual(pkg_acl[0].status, 'Retired')
        self.assertEqual(pkg_acl[1].collection.branchname, 'master')
        self.assertEqual(pkg_acl[1].package.name, 'guake')
        self.assertEqual(pkg_acl[1].point_of_contact, 'orphan')
        self.assertEqual(pkg_acl[1].status, 'Orphaned')

        # Admin can un-orphan package
        pkgdblib.update_pkg_status(self.session,
                                   namespace='rpms',
                                   pkg_name='guake',
                                   pkg_branch='master',
                                   status='Approved',
                                   poc="pingou",
                                   user=FakeFasUserAdmin()
                                   )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'orphan')
        self.assertEqual(pkg_acl[0].status, 'Retired')
        self.assertEqual(pkg_acl[1].collection.branchname, 'master')
        self.assertEqual(pkg_acl[1].package.name, 'guake')
        self.assertEqual(pkg_acl[1].point_of_contact, 'pingou')
        self.assertEqual(pkg_acl[1].status, 'Approved')

        # Admin can un-retire package
        pkgdblib.update_pkg_status(self.session,
                                   namespace='rpms',
                                   pkg_name='guake',
                                   pkg_branch='f18',
                                   status='Approved',
                                   poc="pingou",
                                   user=FakeFasUserAdmin()
                                   )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].point_of_contact, 'pingou')
        self.assertEqual(pkg_acl[0].status, 'Approved')
        self.assertEqual(pkg_acl[1].collection.branchname, 'master')
        self.assertEqual(pkg_acl[1].package.name, 'guake')
        self.assertEqual(pkg_acl[1].point_of_contact, 'pingou')
        self.assertEqual(pkg_acl[1].status, 'Approved')

        # Not Admin and status is not Orphaned nor Retired
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_pkg_status,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='master',
                          status='Removed',
                          user=FakeFasUser()
                          )

    def test_search_collection(self):
        """ Test the search_collection function. """
        create_collection(self.session)

        collections = pkgdblib.search_collection(
            self.session, 'Fedora EPEL*')
        self.assertEqual(len(collections), 0)

        collections = pkgdblib.search_collection(self.session, 'f*',
                                                 status='EOL')
        self.assertEqual(len(collections), 0)

        collections = pkgdblib.search_collection(self.session, 'f*')
        self.assertEqual(len(collections), 2)
        self.assertEqual(
            "Collection(u'Fedora', u'17', u'Active', owner:u'toshio')",
            collections[0].__repr__())

        collections = pkgdblib.search_collection(
            self.session,
            'f*',
            limit=1)
        self.assertEqual(len(collections), 1)

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.search_collection,
                          self.session,
                          'f*',
                          limit='a'
                          )

        collections = pkgdblib.search_collection(
            self.session,
            'f*',
            limit=1,
            page=2)
        self.assertEqual(len(collections), 1)

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.search_collection,
                          self.session,
                          'f*',
                          page='a'
                          )

    def test_add_collection(self):
        """ Test the add_collection function. """

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_collection,
                          session=self.session,
                          clt_name='Fedora',
                          clt_version='19',
                          clt_status='Active',
                          clt_branchname='f19',
                          clt_disttag='.fc19',
                          clt_koji_name='f19',
                          clt_allow_retire=False,
                          user=FakeFasUser(),
                          )
        self.session.rollback()

        pkgdblib.add_collection(self.session,
                                clt_name='Fedora',
                                clt_version='19',
                                clt_status='Active',
                                clt_branchname='f19',
                                clt_disttag='.fc19',
                                clt_koji_name='f19',
                                clt_allow_retire=False,
                                user=FakeFasUserAdmin(),
                                )
        self.session.commit()
        collection = pkgdblib.model.Collection.by_name(self.session, 'f19')
        self.assertEqual(
            "Collection(u'Fedora', u'19', u'Active', owner:u'admin')",
            collection.__repr__())

    def test_update_collection_status(self):
        """ Test the update_collection_status function. """
        create_collection(self.session)

        collection = pkgdblib.model.Collection.by_name(self.session, 'f18')
        self.assertEqual(collection.status, 'Active')

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.update_collection_status,
                          self.session,
                          'f18',
                          'EOL',
                          user=FakeFasUser(),
                          )

        pkgdblib.update_collection_status(
            self.session, 'f18', 'EOL', user=FakeFasUserAdmin())
        self.session.commit()

        msg = pkgdblib.update_collection_status(
            self.session, 'f18', 'EOL', user=FakeFasUserAdmin())
        self.assertEqual(msg, 'Collection "f18" already had this status')

        collection = pkgdblib.model.Collection.by_name(self.session, 'f18')
        self.assertEqual(collection.status, 'EOL')

    def test_search_packagers(self):
        """ Test the search_packagers function. """
        pkg = pkgdblib.search_packagers(self.session, 'pin*')
        self.assertEqual(pkg, [])

        create_package_acl(self.session)

        pkg = pkgdblib.search_packagers(self.session, 'pi*')
        self.assertEqual(len(pkg), 1)
        self.assertEqual(pkg[0][0], 'pingou')

        pkg = pkgdblib.search_packagers(self.session, 'pi*', page=0)
        self.assertEqual(len(pkg), 1)
        self.assertEqual(pkg[0][0], 'pingou')

        pkg = pkgdblib.search_packagers(self.session, 'pi*', limit=1, page=1)
        self.assertEqual(len(pkg), 1)
        self.assertEqual(pkg[0][0], 'pingou')

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.search_packagers,
                          self.session,
                          'p*',
                          limit='a'
                          )

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.search_packagers,
                          self.session,
                          'p*',
                          page='a'
                          )

    def test_get_acl_packager(self):
        """ Test the get_acl_packager function. """
        acls = pkgdblib.get_acl_packager(self.session, 'pingou')
        self.assertEqual(acls, [])

        create_package_acl2(self.session)

        acls = pkgdblib.get_acl_packager(self.session, 'pingou')
        self.assertEqual(len(acls), 11)
        self.assertEqual(acls[0][0].packagelist.package.name, 'guake')
        self.assertEqual(acls[0][0].packagelist.collection.branchname, 'f18')
        self.assertEqual(acls[1][0].packagelist.collection.branchname, 'f18')
        self.assertEqual(acls[2][0].packagelist.collection.branchname, 'master')
        self.assertEqual(acls[3][0].packagelist.collection.branchname, 'master')

        # Wrong page provided
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.get_acl_packager,
            self.session,
            'pingou',
            page='a')

        acls = pkgdblib.get_acl_packager(
            self.session, 'pingou', acls='commit')
        self.assertEqual(len(acls), 6)
        self.assertEqual(acls[0][0].packagelist.package.name, 'guake')
        self.assertEqual(acls[0][0].packagelist.collection.branchname, 'f18')
        self.assertEqual(acls[1][0].packagelist.package.name, 'guake')
        self.assertEqual(acls[1][0].packagelist.collection.branchname, 'master')

        acls = pkgdblib.get_acl_packager(
            self.session, 'pingou', acls='commit', page=2, limit=2)
        self.assertEqual(len(acls), 2)
        self.assertEqual(acls[0][0].packagelist.package.name, 'geany')
        self.assertEqual(acls[0][0].packagelist.collection.branchname, 'master')
        self.assertEqual(acls[1][0].packagelist.package.name, 'fedocal')
        self.assertEqual(acls[1][0].packagelist.collection.branchname, 'master')

        acls = pkgdblib.get_acl_packager(
            self.session, 'pingou', acls=['commit', 'watchbugzilla'])
        self.assertEqual(len(acls), 9)
        self.assertEqual(acls[0][0].packagelist.package.name, 'guake')
        self.assertEqual(acls[0][0].packagelist.collection.branchname, 'f18')
        self.assertEqual(acls[1][0].packagelist.package.name, 'guake')
        self.assertEqual(acls[1][0].packagelist.collection.branchname, 'master')

        acls = pkgdblib.get_acl_packager(
            self.session, 'pingou', acls=['commit'], poc=True)
        self.assertEqual(len(acls), 3)
        self.assertEqual(acls[0][0].packagelist.package.name, 'guake')
        self.assertEqual(acls[0][0].packagelist.collection.branchname, 'f18')
        self.assertEqual(acls[1][0].packagelist.package.name, 'guake')
        self.assertEqual(acls[1][0].packagelist.collection.branchname, 'master')

        acls = pkgdblib.get_acl_packager(
            self.session, 'pingou', acls=['commit'], poc=False)
        self.assertEqual(len(acls), 3)
        self.assertEqual(acls[0][0].packagelist.package.name, 'geany')
        self.assertEqual(acls[0][0].packagelist.collection.branchname, 'master')
        self.assertEqual(acls[1][0].packagelist.package.name, 'fedocal')
        self.assertEqual(acls[1][0].packagelist.collection.branchname, 'master')
        self.assertEqual(acls[2][0].packagelist.package.name, 'fedocal')
        self.assertEqual(acls[2][0].packagelist.collection.branchname, 'f18')

    def test_get_pending_acl_user(self):
        """ Test the get_pending_acl_user function. """
        pending_acls = pkgdblib.get_pending_acl_user(
            self.session, 'pingou')
        self.assertEqual(pending_acls, [])

        create_package_acl(self.session)

        pending_acls = sorted(pkgdblib.get_pending_acl_user(
            self.session, 'pingou'))
        self.assertEqual(len(pending_acls), 2)
        self.assertEqual(pending_acls[0]['package'], 'guake')
        self.assertEqual(pending_acls[0]['collection'], 'master')
        self.assertEqual(pending_acls[0]['acl'], 'approveacls')
        self.assertEqual(pending_acls[0]['status'], 'Awaiting Review')
        self.assertEqual(pending_acls[1]['package'], 'guake')
        self.assertEqual(pending_acls[1]['collection'], 'master')
        self.assertEqual(pending_acls[1]['acl'], 'commit')
        self.assertEqual(pending_acls[1]['status'], 'Awaiting Review')

    def test_get_acl_user_package(self):
        """ Test the get_acl_user_package function. """
        pending_acls = pkgdblib.get_acl_user_package(
            self.session, 'pingou', 'rpms', 'guake')
        self.assertEqual(pending_acls, [])

        create_package_acl(self.session)

        pending_acls = pkgdblib.get_acl_user_package(
            self.session, 'pingou', 'rpms', 'geany')
        self.assertEqual(len(pending_acls), 0)

        pending_acls = pkgdblib.get_acl_user_package(
            self.session, 'pingou', 'rpms', 'guake')
        self.assertEqual(len(pending_acls), 5)

        pending_acls = pkgdblib.get_acl_user_package(
            self.session, 'toshio', 'rpms', 'guake', status='Awaiting Review')
        self.assertEqual(len(pending_acls), 1)
        self.assertEqual(pending_acls[0]['package'], 'guake')
        self.assertEqual(pending_acls[0]['collection'], 'master')
        self.assertEqual(pending_acls[0]['acl'], 'commit')
        self.assertEqual(pending_acls[0]['status'], 'Awaiting Review')

    def test_has_acls(self):
        """ Test the has_acls function. """
        self.assertFalse(
            pkgdblib.has_acls(
                self.session, 'pingou', 'rpms', 'guake',
                acl='approveacl', branch='master'))

        create_package_acl(self.session)

        self.assertTrue(
            pkgdblib.has_acls(
                self.session, 'pingou', 'rpms', 'guake',
                acl='commit', branch='master'))

        self.assertTrue(pkgdblib.has_acls(
            self.session, 'pingou', 'rpms', 'guake', acl='commit'))
        self.assertTrue(pkgdblib.has_acls(
            self.session, 'pingou', 'rpms', 'guake', acl='approveacls'))
        self.assertFalse(pkgdblib.has_acls(
            self.session, 'toshio', 'rpms', 'guake', acl='commit'))
        self.assertFalse(pkgdblib.has_acls(
            self.session, 'toshio', 'rpms', 'guake', acl=['commit', 'approveacls']))

    def test_get_status(self):
        """ Test the get_status function. """
        obs = pkgdblib.get_status(self.session)

        acl_status = ['Approved', 'Awaiting Review', 'Denied', 'Obsolete',
                      'Removed']
        self.assertEqual(obs['acl_status'], acl_status)

        pkg_status = ['Approved', 'Orphaned', 'Removed', 'Retired']
        self.assertEqual(obs['pkg_status'], pkg_status)

        clt_status = ['Active', 'EOL', 'Under Development']
        self.assertEqual(obs['clt_status'], clt_status)

        pkg_acl = ['approveacls', 'commit', 'watchbugzilla', 'watchcommits']
        self.assertEqual(obs['pkg_acl'], pkg_acl)

        obs = pkgdblib.get_status(self.session, 'acl_status')
        self.assertEqual(obs.keys(), ['acl_status'])
        self.assertEqual(obs['acl_status'], acl_status)

        obs = pkgdblib.get_status(self.session, ['acl_status', 'pkg_acl'])
        self.assertEqual(obs.keys(), ['pkg_acl', 'acl_status'])
        self.assertEqual(obs['pkg_acl'], pkg_acl)
        self.assertEqual(obs['acl_status'], acl_status)

    def test_get_package_maintained(self):
        """ Test the get_package_maintained function. """
        create_package_acl(self.session)

        pkg = pkgdblib.get_package_maintained(
            self.session, 'pingou', poc=True)
        self.assertEqual(len(pkg), 1)
        self.assertEqual(pkg[0][0].name, 'guake')
        expected = set(['master', 'f18'])
        branches = set([pkg[0][1][0].branchname, pkg[0][1][1].branchname])
        self.assertEqual(branches.symmetric_difference(expected), set())
        self.assertEqual(len(pkg[0][1]), 2)

        pkg = pkgdblib.get_package_maintained(
            self.session, 'pingou', poc=False)
        self.assertEqual(pkg, [])

        pkg = pkgdblib.get_package_maintained(self.session, 'ralph')
        self.assertEqual(pkg, [])

    def test_get_package_watch(self):
        """ Test the get_package_watch function. """
        create_package_acl(self.session)

        pkg = pkgdblib.get_package_watch(self.session, 'pingou')
        self.assertEqual(len(pkg), 1)
        self.assertEqual(pkg[0][0].name, 'guake')
        expected = set(['master', 'f18'])
        branches = set([pkg[0][1][0].branchname, pkg[0][1][1].branchname])
        self.assertEqual(branches.symmetric_difference(expected), set())
        self.assertEqual(len(pkg[0][1]), 2)

        pkg = pkgdblib.get_package_watch(
            self.session, 'pingou', branch='master')
        self.assertEqual(len(pkg), 1)
        self.assertEqual(pkg[0][0].name, 'guake')
        expected = set(['master'])
        branches = set([pkg[0][1][0].branchname])
        self.assertEqual(branches.symmetric_difference(expected), set())
        self.assertEqual(len(pkg[0][1]), 1)

        pkg = pkgdblib.get_package_watch(
            self.session, 'pingou', pkg_status='Awaiting Review')
        self.assertEqual(pkg, [])

        pkg = pkgdblib.get_package_watch(self.session, 'ralph')
        self.assertEqual(pkg, [])

    def test_edit_collection(self):
        """ Test the edit_collection function. """
        create_collection(self.session)

        collection = pkgdblib.search_collection(self.session, 'f18')[0]

        out = pkgdblib.edit_collection(self.session, collection,
                                       user=FakeFasUserAdmin())
        self.assertEqual(out, None)

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.edit_collection,
                          self.session,
                          collection)

        out = pkgdblib.edit_collection(
            self.session,
            collection,
            clt_name='Fedora youhou!',
            clt_version='Awesome 18',
            clt_status='EOL',
            clt_branchname='f18_b',
            clt_disttag='fc18',
            user=FakeFasUserAdmin(),
        )

        self.assertEqual(out, 'Collection "f18_b" edited')

        collections = pkgdblib.search_collection(self.session, 'f18')
        self.assertEqual(collections, [])

        collection = pkgdblib.search_collection(self.session, 'f18_b')[0]
        self.assertEqual(collection.name, 'Fedora youhou!')
        self.assertEqual(collection.status, 'EOL')

    def test_edit_package(self):
        """ Test the edit_package function. """
        create_package_acl(self.session)

        package = pkgdblib.search_package(self.session, 'rpms', 'guake')[0]

        out = pkgdblib.edit_package(
            self.session, package, user=FakeFasUserAdmin())
        self.assertEqual(out, None)

        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.edit_package,
                          self.session,
                          package)

        out = pkgdblib.edit_package(
            self.session,
            package,
            pkg_name='Fedora youhou!',
            pkg_summary='Youhou Fedora is awesome!',
            pkg_status='Orphaned',
            pkg_description='this package says how awesome fedora is',
            pkg_review_url='http://bugzilla.rh.com/42',
            pkg_upstream_url='https://fedoraproject.org',
            user=FakeFasUserAdmin(),
        )

        self.assertEqual(out, 'Package "Fedora youhou!" edited')

        collections = pkgdblib.search_package(self.session, 'rpms', 'guake')
        self.assertEqual(collections, [])

        package = pkgdblib.search_package(
            self.session, 'rpms', 'Fedora youhou!')[0]
        self.assertEqual(package.name, 'Fedora youhou!')
        self.assertEqual(package.review_url, 'http://bugzilla.rh.com/42')
        self.assertEqual(package.summary, 'Youhou Fedora is awesome!')
        self.assertEqual(package.status, 'Orphaned')

    def test_get_top_maintainers(self):
        """ Test the get_top_maintainers funtion. """
        create_package_acl(self.session)

        top = pkgdblib.get_top_maintainers(self.session)
        self.assertEqual(
            top, [(u'group::gtk-sig', 1), (u'josef', 1), (u'pingou', 1)])

    def test_get_top_poc(self):
        """ Test the get_top_poc function. """
        create_package_acl(self.session)

        top = pkgdblib.get_top_poc(self.session)
        self.assertEqual(
            top, [(u'pingou', 3), (u'group::gtk-sig', 1), (u'josef', 1)])

    def test_search_logs(self):
        """ Test the search_logs function. """
        self.test_add_package()

        # Wrong limit
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.search_logs,
                          self.session,
                          limit='a'
                          )

        # Wrong offset
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.search_logs,
                          self.session,
                          page='a'
                          )

        # Wrong package name
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.search_logs,
                          self.session,
                          package='asdads'
                          )

        logs = pkgdblib.search_logs(self.session)

        self.assertEqual(len(logs), 23)
        self.assertEqual(logs[22].description, "user: admin created "
                         "package: guake on branch: f18 for point of "
                         "contact: ralph")
        self.assertEqual(logs[22].user, "admin")
        self.assertEqual(logs[19].description, "user: admin set for ralph "
                         "acl: watchcommits of package: guake from: "
                         " to: Approved on branch: f18")

        logs = pkgdblib.search_logs(self.session, limit=3, page=2)

        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0].description, "user: admin set for "
                         "group::infra-sig acl: watchcommits of package: "
                         "fedocal from:  to: Approved on branch: "
                         "master")
        self.assertEqual(logs[0].user, "admin")

        exp = "Log(user=u'admin', description=u'user: admin set for "\
              "group::infra-sig acl: watchcommits of package: fedocal from:"\
              "  to: Approved on branch: master"
        self.assertTrue(logs[0].__repr__().startswith(exp))

        logs = pkgdblib.search_logs(self.session, count=True)
        self.assertEqual(logs, 23)

        logs = pkgdblib.search_logs(self.session, from_date=date.today())
        self.assertEqual(len(logs), 23)

        logs = pkgdblib.search_logs(
            self.session, from_date=date.today(), package='guake')
        self.assertEqual(len(logs), 5)

        logs = pkgdblib.search_logs(self.session, packager='admin')
        self.assertEqual(len(logs), 23)

        logs = pkgdblib.search_logs(self.session, packager='pingou')
        self.assertEqual(len(logs), 0)

    def test_unorphan_package(self):
        """ Test the unorphan_package function. """
        create_package_acl(self.session)

        # Wrong package name
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.unorphan_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='asd',
                          pkg_branch='master',
                          pkg_user='pingou',
                          user=FakeFasUser()
                          )
        self.session.rollback()

        # Wrong collection
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.unorphan_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='asd',
                          pkg_user='pingou',
                          user=FakeFasUser()
                          )
        self.session.rollback()

        # Package is not orphaned
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.unorphan_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='master',
                          pkg_user='pingou',
                          user=FakeFasUser()
                          )
        self.session.rollback()

        # PKGDB2_BUGZILLA_* configuration not set
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.unorphan_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='master',
                          pkg_user='pingou',
                          user=FakeFasUser()
                          )
        self.session.rollback()

        if pkgdb2.APP.config['PKGDB2_BUGZILLA_IN_TESTS']:
            pkgdb2.lib.utils.get_bz_email_user = mock.MagicMock()
            pkgdb2.lib.utils.get_bz_email_user.return_value = FakeFasUser
        else:
            pkgdb2.lib.utils.set_bugzilla_owner = mock.MagicMock()
        self.session.commit()

        # Orphan package
        pkgdblib.update_pkg_poc(self.session,
                                namespace='rpms',
                                pkg_name='guake',
                                pkg_branch='master',
                                user=FakeFasUserAdmin(),
                                pkg_poc='orphan',
                                )
        self.session.commit()

        # User cannot unorphan for someone else
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.unorphan_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='master',
                          pkg_user='ralph',
                          user=FakeFasUser()
                          )
        self.session.rollback()

        # User must be a packager
        user = FakeFasUser()
        user.groups = ['cla_done']
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.unorphan_package,
                          self.session,
                          namespace='rpms',
                          pkg_name='guake',
                          pkg_branch='master',
                          pkg_user='pingou',
                          user=user
                          )
        self.session.rollback()

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[1].collection.branchname, 'master')
        self.assertEqual(pkg_acl[1].package.name, 'guake')
        self.assertEqual(pkg_acl[1].point_of_contact, 'orphan')
        self.assertEqual(pkg_acl[1].status, 'Orphaned')

        pkgdblib.unorphan_package(
            self.session,
            namespace='rpms',
            pkg_name='guake',
            pkg_branch='master',
            pkg_user='pingou',
            user=FakeFasUser()
        )
        self.session.commit()

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(pkg_acl[1].collection.branchname, 'master')
        self.assertEqual(pkg_acl[1].package.name, 'guake')
        self.assertEqual(pkg_acl[1].point_of_contact, 'pingou')
        self.assertEqual(pkg_acl[1].status, 'Approved')

    def test_add_branch(self):
        """ Test the add_branch function. """
        create_package_acl(self.session)

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(len(pkg_acl), 2)
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].acls[0].fas_name, 'pingou')
        self.assertEqual(pkg_acl[1].collection.branchname, 'master')

        # Create a new collection
        new_collection = pkgdblib.model.Collection(
            name='Fedora',
            version='19',
            status='Active',
            owner='toshio',
            branchname='f19',
            dist_tag='.fc19',
        )
        self.session.add(new_collection)
        self.session.commit()

        # User cannot branch, admins are required
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_branch,
                          session=self.session,
                          clt_from='master',
                          clt_to='f19',
                          user=FakeFasUser()
                          )

        # Inexistant collection to branch from
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_branch,
                          session=self.session,
                          clt_from='blah',
                          clt_to='f19',
                          user=FakeFasUserAdmin()
                          )

        # Inexistant collection to branch to
        self.assertRaises(pkgdblib.PkgdbException,
                          pkgdblib.add_branch,
                          session=self.session,
                          clt_from='master',
                          clt_to='blah',
                          user=FakeFasUserAdmin()
                          )

        pkgdblib.add_branch(
            session=self.session,
            clt_from='master',
            clt_to='f19',
            user=FakeFasUserAdmin()
        )

        pkg_acl = pkgdblib.get_acl_package(self.session, 'rpms', 'guake')
        self.assertEqual(len(pkg_acl), 3)
        self.assertEqual(pkg_acl[0].collection.branchname, 'f18')
        self.assertEqual(pkg_acl[0].package.name, 'guake')
        self.assertEqual(pkg_acl[0].acls[0].fas_name, 'pingou')
        self.assertEqual(len(pkg_acl[0].acls), 2)
        self.assertEqual(pkg_acl[1].collection.branchname, 'master')
        self.assertEqual(len(pkg_acl[1].acls), 5)
        self.assertEqual(pkg_acl[2].collection.branchname, 'f19')
        self.assertEqual(len(pkg_acl[2].acls), 5)

    def test_get_critpath_packages(self):
        """ Test the get_critpath_packages method of pkgdblib. """
        create_package_acl(self.session)

        pkg_list = pkgdblib.get_critpath_packages(self.session)
        self.assertEqual(pkg_list, [])

        pkg_list = pkgdblib.get_critpath_packages(
            self.session, branch='master')
        self.assertEqual(pkg_list, [])

        create_package_critpath(self.session)

        pkg_list = pkgdblib.get_critpath_packages(self.session)
        self.assertEqual(len(pkg_list), 2)
        self.assertEqual(
            pkg_list[0].point_of_contact, "kernel-maint")
        self.assertEqual(
            pkg_list[0].collection.branchname, "f18")
        self.assertEqual(
            pkg_list[1].point_of_contact, "group::kernel-maint")
        self.assertEqual(
            pkg_list[1].collection.branchname, "master")

        pkg_list = pkgdblib.get_critpath_packages(
            self.session, branch='master')
        self.assertEqual(len(pkg_list), 1)
        self.assertEqual(
            pkg_list[0].point_of_contact, "group::kernel-maint")
        self.assertEqual(
            pkg_list[0].collection.branchname, "master")

    def test_get_groups(self):
        """ Test the get_groups function. """
        groups = pkgdblib.get_groups(self.session)
        self.assertEqual(groups, [])

        create_package_acl(self.session)

        groups = pkgdblib.get_groups(self.session)
        self.assertEqual(groups, ['gtk-sig'])

    def test_set_critpath_packages(self):
        """ Test the set_critpath_packages function. """
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.set_critpath_packages,
            session=self.session,
            namespace='rpms',
            pkg_name='master',
            pkg_branch='blah',
            user=FakeFasUser()
        )

        create_package_acl(self.session)
        create_package_critpath(self.session)

        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.set_critpath_packages,
            session=self.session,
            namespace='rpms',
            pkg_name='guake',
            pkg_branch='el4',
            user=FakeFasUserAdmin()
        )

    def test_notify(self):
        """ Test the notify function. """
        create_package_acl(self.session)

        data = pkgdblib.notify(self.session, acls='commit')
        self.assertEqual(
            data,
            {u'guake': u'pingou', u'geany': u'group::gtk-sig,josef'}
        )

        data = pkgdblib.notify(self.session)
        self.assertEqual(
            data,
            {u'guake': u'pingou', u'geany': u'group::gtk-sig,josef'})

    def test_set_monitor_package(self):
        """ Test the set_monitor_package function. """
        self.assertFalse(
            pkgdblib.has_acls(
                self.session, 'pingou', 'rpms', 'guake',
                acl='approveacl', branch='master'))

        # Fails: package not found
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.set_monitor_package,
            session=self.session,
            namespace='rpms',
            pkg_name='guake',
            status=True,
            user=FakeFasUser()
        )

        create_package_acl(self.session)

        self.assertTrue(
            pkgdblib.has_acls(
                self.session, 'pingou', 'rpms', 'guake',
                acl='commit', branch='master'))

        # Fails: user not a packager
        user = FakeFasUser()
        user.username = 'Toshio'
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.set_monitor_package,
            session=self.session,
            namespace='rpms',
            pkg_name='guake',
            status=True,
            user=user
        )

        # Works
        msg = pkgdblib.set_monitor_package(
            session=self.session,
            namespace='rpms',
            pkg_name='guake',
            status=True,
            user=FakeFasUser()
        )

        self.assertEqual(msg, 'Monitoring status of rpms/guake set to True')

        # Works
        msg = pkgdblib.set_monitor_package(
            session=self.session,
            namespace='rpms',
            pkg_name='guake',
            status=True,
            user=FakeFasUser()
        )

        self.assertEqual(msg, 'Monitoring status un-changed')

        # Works: user is a pkgdb admin
        self.assertFalse(
            pkgdblib.has_acls(
                self.session, 'kevin', 'rpms', 'guake',
                acl='commit', branch='master'))

        user = FakeFasUserAdmin()
        user.username = 'kevin'
        msg = pkgdblib.set_monitor_package(
            session=self.session,
            namespace='rpms',
            pkg_name='guake',
            status=False,
            user=FakeFasUser()
        )
        self.assertEqual(msg, 'Monitoring status of rpms/guake set to False')

    @patch('pkgdb2.lib.utils')
    def test_add_new_branch_request(self, mock_func):
        """ Test the add_new_branch_request method of pkgdblib. """
        create_package_acl(self.session)

        mock_func.get_packagers.return_value = ['pingou', 'toshio']

        # Invalid package
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_new_branch_request,
            session=self.session,
            namespace='rpms',
            pkg_name='foobar',
            clt_to='el6',
            user=FakeFasUserAdmin()
        )

        # Invalid collection_to
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_new_branch_request,
            session=self.session,
            namespace='rpms',
            pkg_name='guake',
            clt_to='foobar',
            user=FakeFasUserAdmin()
        )

        # Invalid collection_from
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_new_branch_request,
            session=self.session,
            namespace='rpms',
            pkg_name='guake',
            clt_to='el6',
            user=FakeFasUserAdmin()
        )

        # valid entry
        user = FakeFasUser()
        user.username = 'toshio'
        pkgdblib.add_new_branch_request(
            session=self.session,
            namespace='rpms',
            pkg_name='guake',
            clt_to='el6',
            user=user
        )

    @patch('pkgdb2.lib.utils.get_rhel_pkg')
    def test_search_actions(self, getrhelpkg_func):
        """ Test the search_actions method of pkgdblib. """
        getrhelpkg_func.return_value = []
        create_package_acl(self.session)

        # Wrong limit
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.search_actions,
            self.session,
            limit='a'
        )

        # Wrong offset
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.search_actions,
            self.session,
            page='a'
        )

        # Wrong package name
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.search_actions,
            self.session,
            package='asdads'
        )

        # Check before insert
        actions = pkgdblib.search_actions(
            self.session,
            package='guake'
        )
        self.assertEqual(actions, [])

        pkgdb2.lib.utils.get_packagers = mock.MagicMock()
        pkgdb2.lib.utils.get_packagers.return_value = ['pingou']

        if not os.environ.get('OFFLINE'):
            # Insert
            pkgdblib.add_new_branch_request(
                session=self.session,
                namespace='rpms',
                pkg_name='guake',
                clt_to='el6',
                user=FakeFasUser()
            )

            # Check after insert
            # One thing awaiting review:
            actions = pkgdblib.search_actions(
                self.session,
                namespace='rpms',
                package='guake',
                page=1,
                limit=50,
            )
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0].user, 'pingou')
            self.assertEqual(actions[0].package.name, 'guake')
            self.assertEqual(actions[0].collection.branchname, 'el6')

            # But nothing pending
            actions = pkgdblib.search_actions(
                self.session,
                namespace='rpms',
                package='guake',
                status='Pending',
                page=1,
                limit=50,
            )
            self.assertEqual(len(actions), 0)

    def test_get_admin_action(self):
        """ Test the get_admin_action method of pkgdblib. """

        action = pkgdblib.get_admin_action(self.session, 1)
        self.assertEqual(action, None)

        # Unretire the package
        self.test_add_new_branch_request()
        self.session.commit()

        action = pkgdblib.get_admin_action(self.session, 1)
        self.assertNotEqual(action, None)
        self.assertEqual(action.action, 'request.branch')
        self.assertEqual(action.user, 'toshio')
        self.assertEqual(action.status, 'Pending')
        self.assertEqual(action.package.name, 'guake')
        self.assertEqual(action.collection.branchname, 'el6')
        self.assertEqual(action.info, None)

        action = pkgdblib.get_admin_action(self.session, 2)
        self.assertEqual(action, None)

    def test_edit_action_status(self):
        """ Test the edit_action_status method of pkgdblib. """

        action = pkgdblib.get_admin_action(self.session, 1)
        self.assertEqual(action, None)

        # Unretire the package
        self.test_add_new_branch_request()
        self.session.commit()

        action = pkgdblib.get_admin_action(self.session, 1)
        self.assertNotEqual(action, None)
        self.assertEqual(action.action, 'request.branch')
        self.assertEqual(action.user, 'toshio')
        self.assertEqual(action.status, 'Pending')
        self.assertEqual(action.package.name, 'guake')
        self.assertEqual(action.collection.branchname, 'el6')
        self.assertEqual(action.info, None)

        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.edit_action_status,
            self.session,
            admin_action=action,
            action_status='foo',
            user=FakeFasUser()
        )

        action = pkgdblib.get_admin_action(self.session, 1)

        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.edit_action_status,
            self.session,
            admin_action=action,
            action_status='foo',
            user=FakeFasUserAdmin()
        )

        # Pending status but unknown user
        user = FakeFasUser()
        user.username = 'shaiton'
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.edit_action_status,
            self.session,
            admin_action=action,
            action_status='Pending',
            user=user
        )

        # Awaiting Review status but user is requester
        user = FakeFasUser()
        user.username = 'toshio'
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.edit_action_status,
            self.session,
            admin_action=action,
            action_status='Awaiting Review',
            user=user
        )

        # Obsolete status but user is not requester
        user = FakeFasUserAdmin()
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.edit_action_status,
            self.session,
            admin_action=action,
            action_status='Obsolete',
            user=user
        )

        action = pkgdblib.get_admin_action(self.session, 1)

        msg = pkgdblib.edit_action_status(
            self.session,
            admin_action=action,
            action_status='Pending',
            user=FakeFasUserAdmin()
        )

        self.assertEqual(msg, 'Nothing to change.')

        msg = pkgdblib.edit_action_status(
            self.session,
            admin_action=action,
            action_status='Approved',
            user=FakeFasUserAdmin()
        )

        self.assertEqual(
            msg,
            'user: admin updated action: 1 of guake from `Pending` to '
            '`Approved`'
        )

        action = pkgdblib.get_admin_action(self.session, 1)

        self.assertNotEqual(action, None)
        self.assertEqual(action.action, 'request.branch')
        self.assertEqual(action.user, 'toshio')
        self.assertEqual(action.status, 'Approved')
        self.assertEqual(action.package.name, 'guake')
        self.assertEqual(action.collection.branchname, 'el6')
        self.assertEqual(action.info, None)

    @patch('pkgdb2.lib.utils.get_packagers')
    def test_add_unretire_request(self, mock_func):
        """ Test the add_unretire_request method of pkgdblib. """

        mock_func.return_value = ['pingou']

        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_unretire_request,
            self.session,
            namespace='rpms',
            pkg_name='foo',
            pkg_branch='master',
            review_url=None,
            user=FakeFasUser()
        )

        self.test_add_new_branch_request()
        self.session.commit()

        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_unretire_request,
            self.session,
            namespace='rpms',
            pkg_name='guake',
            pkg_branch='foo',
            review_url=None,
            user=FakeFasUser()
        )

        msg = pkgdblib.add_unretire_request(
            self.session,
            namespace='rpms',
            pkg_name='guake',
            pkg_branch='master',
            review_url=None,
            user=FakeFasUser()
        )
        self.assertEqual(
            msg, 'user: pingou requested branch: master to be unretired '
            'for package guake')

    @patch('pkgdb2.lib.utils.get_packagers')
    def test_add_new_package_request(self, mock_func):
        """ Test the add_new_package_request method to pkgdblib. """

        mock_func.return_value = ['pingou']

        # Branch `foo` not found
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_new_package_request,
            session=self.session,
            pkg_name='guake',
            pkg_summary='Drop-down terminal for GNOME',
            pkg_description='desc',
            pkg_status='Approved',
            pkg_collection='foo',
            pkg_poc='pingou',
            user=FakeFasUser(),
            pkg_review_url='https://bz.rh.c/123',
            pkg_upstream_url=None,
            pkg_critpath=False,
        )

        self.test_add_new_branch_request()
        self.session.commit()

        # Again, branch not found
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_new_package_request,
            session=self.session,
            pkg_name='guake',
            pkg_summary='Drop-down terminal for GNOME',
            pkg_description='desc',
            pkg_status='Approved',
            pkg_collection='foo',
            pkg_poc='pingou',
            user=FakeFasUser(),
            pkg_review_url='https://bz.rh.c/123',
            pkg_upstream_url=None,
            pkg_critpath=False,
        )

        # Package already exists
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_new_package_request,
            session=self.session,
            pkg_name='guake',
            pkg_summary='Drop-down terminal for GNOME',
            pkg_description='desc',
            pkg_status='Approved',
            pkg_collection='master',
            pkg_poc='pingou',
            user=FakeFasUser(),
            pkg_review_url='https://bz.rh.c/123',
            pkg_upstream_url=None,
            pkg_critpath=False,
        )

        msg = pkgdblib.add_new_package_request(
            session=self.session,
            pkg_name='zsh',
            pkg_summary='Powerful interactive shell',
            pkg_description='desc',
            pkg_status='Approved',
            pkg_collection='master',
            pkg_poc='pingou',
            user=FakeFasUser(),
            pkg_review_url='https://bz.rh.c/123',
            pkg_upstream_url=None,
            pkg_critpath=False,
        )
        self.assertEqual(
            msg, 'user: pingou request package: zsh on branch master')

    def test_add_namespace(self):
        """ Test the add_namespace method to pkgdblib. """
        # Before:
        namespaces = pkgdblib.get_status(
            self.session, 'namespaces')['namespaces']
        self.assertEqual(namespaces, ['docker', 'rpms'])

        # User is not an admin
        user = FakeFasUser()
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_namespace,
            self.session,
            'foo',
            user
        )

        # Namespace already exists
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.add_namespace,
            self.session,
            'rpms',
            user
        )

        # Works
        user = FakeFasUserAdmin()
        msg = pkgdblib.add_namespace(
            self.session,
            'foo',
            user
        )
        self.assertEqual(msg, 'Namespace "foo" created')

        # After:
        namespaces = pkgdblib.get_status(
            self.session, 'namespaces')['namespaces']
        self.assertEqual(namespaces, ['docker', 'foo', 'rpms'])

    def test_drop_namespace(self):
        """ Test the drop_namespace method to pkgdblib. """

        self.test_add_namespace()

        # Before:
        namespaces = pkgdblib.get_status(
            self.session, 'namespaces')['namespaces']
        self.assertEqual(namespaces, ['docker', 'foo', 'rpms'])

        # User is not an admin
        user = FakeFasUser()
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.drop_namespace,
            self.session,
            'foo',
            user
        )

        # Namespace does not exist
        self.assertRaises(
            pkgdblib.PkgdbException,
            pkgdblib.drop_namespace,
            self.session,
            'foobar',
            user
        )

        # Works
        user = FakeFasUserAdmin()
        msg = pkgdblib.drop_namespace(
            self.session,
            'foo',
            user
        )
        self.assertEqual(msg, 'Namespace "foo" removed')

        # After:
        namespaces = pkgdblib.get_status(
            self.session, 'namespaces')['namespaces']
        self.assertEqual(namespaces, ['docker', 'rpms'])


if __name__ == '__main__':
    SUITE = unittest.TestLoader().loadTestsFromTestCase(PkgdbLibtests)
    unittest.TextTestRunner(verbosity=2).run(SUITE)
