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
PkgDB internal API to interact with the database.
'''

import operator
import json

import sqlalchemy

from datetime import timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import SQLAlchemyError

from fedora.client.fas2 import FASError

import pkgdb2
from pkgdb2.lib import model
import pkgdb2.lib.utils
from pkgdb2.lib.exceptions import PkgdbException, PkgdbBugzillaException


ACLS = ['commit', 'watchbugzilla', 'watchcommits', 'approveacls']

## Apparently some of our methods have too many arguments
# pylint: disable=R0913
## to many branches
# pylint: disable=R0912
## or to many variables
# pylint: disable=R0914
## Ignore warnings about TODOs
# pylint: disable=W0511
## Ignore variable name that are too short
# pylint: disable=C0103

def _validate_poc(pkg_poc):
    """ Validate is the provided ``pkg_poc`` is a valid poc for a package.

    A valid poc is defined as:
        - a user part of the `packager` group
        - an existing group of type `pkgdb`

    :arg pkg_poc: the username of the new Point of contact (POC).

    """
    if pkg_poc == 'orphan':
        return
    if pkg_poc.startswith('group::'):
        # if pkg_poc is a group:
        group = pkg_poc.split('group::')[1]

        # is pkg_poc a group ending with -sig
        if not group.endswith('-sig'):
            raise PkgdbException(
                'Invalid group "%s" all groups should ends with "-sig".' %
                group)

        # is pkg_poc a valid group (of type pkgdb)
        try:
            group_obj = pkgdb2.lib.utils.get_fas_group(group)
        except FASError as err:  # pragma: no cover
            pkgdb2.LOG.exception(err)
            raise PkgdbException('Could not find group "%s" ' % group)
        if group_obj.group_type != 'pkgdb':
            raise PkgdbException(
                'Invalid group "%s" all groups maintaining packages in pkgdb '
                'should be of type "pkgdb".' % group)
    else:
        # if pkg_poc is a packager
        packagers = pkgdb2.lib.utils.get_packagers()
        if pkg_poc not in packagers \
                and pkg_poc not in pkgdb2.APP.config.get(
                    'AUTOAPPROVE_PKGERS', []):
            raise PkgdbException(
                'User "%s" is not in the packager group' % pkg_poc)


def _validate_pkg(session, rhel_ver, pkg_name):
    """ Validate if the specified package is in the specified RHEL version
    or not.
    """
    rhel_vers = [
        item.version
        for item in search_collection(session, pattern='*el*')
    ]
    rhel_pkgs = pkgdb2.lib.utils.get_rhel_pkg(rhel_vers)

    if rhel_ver in rhel_pkgs and rhel_pkgs[rhel_ver]:
        if pkg_name in rhel_pkgs[rhel_ver]['packages']:
            arches = set([
                'i686' if arch == 'i386' else arch
                for arch in rhel_pkgs[rhel_ver]['arches']
            ])
            pkg_arches = set([
                'i686' if arch == 'i386' else arch
                for arch in rhel_pkgs[rhel_ver]['packages'][pkg_name]['arch']
            ])

            valid = True
            if pkg_arches == ['noarch']:
                # noarch == all arches
                valid = False
            else:
                diff = arches.symmetric_difference(pkg_arches)
                if len(diff) == 1 and sorted(diff) == ['noarch']:
                    # Present on all compiled arches
                    valid = False
                elif len(diff) == 0:
                    # Present on all arches
                    valid = False

            if valid is False:
                raise PkgdbException(
                    'There is already a package named %s in RHEL-%s. '
                    'If you really wish to have an EPEL branch for it '
                    'open a ticket on the rel-eng trac' % (
                        pkg_name, rhel_ver))


def _validate_fas_user(username):
    """ Validate that the provided ``username`` is associated to a valid FAS
    account.

    :arg username: the username of the user to search in FAS.

    """
    if username == 'orphan':
        return

    user = pkgdb2.lib.utils.get_bz_email_user(username)

    if not user:
        raise PkgdbException(
            'User "%s" could not be found in FAS' % username)


def create_session(db_url, debug=False, pool_recycle=3600):
    """ Create the Session object to use to query the database.

    :arg db_url: URL used to connect to the database. The URL contains
    information with regards to the database engine, the host to connect
    to, the user and password and the database name.
      ie: <engine>://<user>:<password>@<host>/<dbname>
    :kwarg debug: a boolean specifying wether we should have the verbose
        output of sqlalchemy or not.
    :return a Session that can be used to query the database.

    """
    engine = sqlalchemy.create_engine(db_url,
                                      echo=debug,
                                      pool_recycle=pool_recycle)
    scopedsession = scoped_session(sessionmaker(bind=engine))
    return scopedsession


def add_package(
        session, namespace, pkg_name, pkg_summary, pkg_description,
        pkg_status, pkg_collection, pkg_poc, user, pkg_review_url=None,
        pkg_upstream_url=None, pkg_critpath=False):
    """ Create a new Package in the database and adds the corresponding
    PackageListing entry.

    :arg session: session with which to connect to the database.
    :arg namespace: the namespace of the package created, defaults to
        'rpms'.
    :arg pkg_name: the name of the package.
    :arg pkg_summary: a summary description of the package.
    :arg pkg_description: the description of the package.
    :arg pkg_status: the status of the package.
    :arg pkg_collection: the collection in which had the package.
    :arg pkg_poc: the point of contact for this package in this collection
    :arg user: the user performing the action
    :kwarg pkg_review_url: the url of the review-request on the bugzilla
    :kwarg pkg_upstream_url: the url of the upstream project.
    :kwarg pkg_critpath: a boolean specifying if the package is marked as
        being in critpath.
    :returns: a message informating that the package has been successfully
        created.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - You are not allowed to add a package, only pkgdb admin can
            - Something went wrong when adding the Package to the database
            - Something went wrong when adding ACLs for this package in the
                database
            - Group is incorrect
    :raises sqlalchemy.orm.exc.NoResultFound: when there is no collection
        found in the database with the name ``pkg_collection``.

    """
    if user is None or not pkgdb2.is_pkgdb_admin(user):
        raise PkgdbException("You're not allowed to add a package")

    _validate_poc(pkg_poc)

    if isinstance(pkg_collection, (str, unicode)):
        if ',' in pkg_collection:
            pkg_collection = [item.strip()
                              for item in pkg_collection.split(',')]
        else:
            pkg_collection = [pkg_collection]

    package = model.Package(
        namespace=namespace,
        name=pkg_name,
        summary=pkg_summary,
        description=pkg_description,
        status=pkg_status,
        review_url=pkg_review_url,
        upstream_url=pkg_upstream_url,
    )
    session.add(package)
    try:
        session.flush()
    except SQLAlchemyError, err:  # pragma: no cover
        pkgdb2.LOG.exception(err)
        session.rollback()
        raise PkgdbException('Could not create package')

    for collec in pkg_collection:
        collection = model.Collection.by_name(session, collec)
        pkglisting = package.create_listing(point_of_contact=pkg_poc,
                                            collection=collection,
                                            statusname=pkg_status,
                                            critpath=pkg_critpath)
        session.add(pkglisting)
        try:
            session.flush()
        except SQLAlchemyError, err:  # pragma: no cover
            pkgdb2.LOG.exception(err)
            session.rollback()
            raise PkgdbException('Could not add packages to collections')
        else:
            pkgdb2.lib.utils.log(session, package, 'package.new', dict(
                agent=user.username,
                package_name=package.name,
                package_listing=pkglisting.to_json(),
            ))

    # Add all new ACLs to the owner
    acls = ACLS
    if pkg_poc.startswith('group::'):
        acls = ['commit', 'watchbugzilla', 'watchcommits']

    for collec in pkg_collection:
        for acl in acls:
            set_acl_package(
                session=session,
                namespace=namespace,
                pkg_name=pkg_name,
                pkg_branch=collec,
                pkg_user=pkg_poc,
                acl=acl,
                status='Approved',
                user=user)
    try:
        session.flush()
        return 'Package created'
    except SQLAlchemyError, err:  # pragma: no cover
        pkgdb2.LOG.exception(err)
        raise PkgdbException('Could not add ACLs')


def get_acl_package(
        session, namespace, pkg_name, pkg_clt=None, eol=False):
    """ Return the ACLs for the specified package.

    :arg session: session with which to connect to the database.
    :arg pkg_name: the name of the package to retrieve the ACLs for.
    :kwarg namespace: the namespace of the package.
    :kward pkg_clt: the branche name of the collection or collections to
        retrieve the ACLs of.
    :kwarg eol: a boolean to specify whether to include results for
        EOL collections or not. Defaults to False.
        If True, it will return results for all collections (including EOL).
        If False, it will return results only for non-EOL collections.
    :returns: a list of ``PackageListing``.
    :rtype: list(PackageListing)
    :raises sqlalchemy.orm.exc.NoResultFound: when there is no package
        found in the database with the name ``pkg_name``.

    """
    package = model.Package.by_name(session, namespace, pkg_name)
    pkglisting = model.PackageListing.by_package_id(session, package.id)

    if pkg_clt:
        if isinstance(pkg_clt, basestring):
            pkg_clt = [pkg_clt]
        tmp = []
        for pkglist in pkglisting:
            if pkglist.collection.branchname in pkg_clt:
                tmp.append(pkglist)
        pkglisting = tmp

    if not eol:
        tmp = []
        for pkglist in pkglisting:
            if pkglist.collection.status != 'EOL':
                tmp.append(pkglist)
        pkglisting = tmp

    return pkglisting


def set_acl_package(session, namespace, pkg_name, pkg_branch, pkg_user,
                    acl, status, user, force=False):
    """ Set the specified ACLs for the specified package.

    :arg session: session with which to connect to the database.
    :arg namespace: the namespace of the package.
    :arg pkg_name: the name of the package.
    :arg pkg_branch: the name of the collection.
    :arg pkg_user: the FAS user for which the ACL should be set/change.
    :arg status: the status of the ACLs.
    :arg user: the user making the action.
    :kwarg force: a boolean to force creating the ACLs w/o checking if the
        user is an admin or not
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - The ``pkg_name`` does not correspond to any package in the
                database.
            - The ``pkg_branch`` does not correspond to any collection in
                the database.
            - You are not allowed to perform the action, are allowed:
                - pkgdb admins.
                - People with 'approveacls' rights.
                - Anyone for 'watchcommits' and 'watchbugzilla' acls.
                - Anyone to set status to 'Awaiting review', 'Removed' and
                    'Obsolete'.
                .. note:: groups cannot have 'approveacls' rights.

    """
    if acl not in pkgdb2.APP.config['AUTO_APPROVE'] \
            and status not in ('Removed', 'Obsolete'):
        _validate_poc(pkg_user)

    if pkg_user.startswith('group:'):
        _validate_poc(pkg_user)
    else:
        _validate_fas_user(pkg_user)

    try:
        package = model.Package.by_name(session, namespace, pkg_name)
    except NoResultFound:
        raise PkgdbException('No package found by this name')

    try:
        collection = model.Collection.by_name(session, pkg_branch)
    except NoResultFound:
        raise PkgdbException('No collection found by the name of %s'
                             % pkg_branch)

    if not force and not pkgdb2.is_pkg_admin(
            session, user, namespace, package.name, pkg_branch):
        if user.username != pkg_user and not pkg_user.startswith('group::'):
            raise PkgdbException('You are not allowed to update ACLs of '
                                 'someone else.')
        elif user.username == pkg_user and status not in \
                ('Awaiting Review', 'Removed', 'Obsolete', '') \
                and acl not in pkgdb2.APP.config['AUTO_APPROVE']:
            raise PkgdbException(
                'You are not allowed to approve or deny '
                'ACLs for yourself.')

    if acl == 'approveacls' and (
            pkg_user.startswith('group::')
            or pkg_user in pkgdb2.APP.config.get('AUTOAPPROVE_PKGERS', [])):
        raise PkgdbException(
            'Groups cannot have "approveacls".')

    pkglisting = model.PackageListing.by_pkgid_collectionid(
        session, package.id, collection.id)
    if not pkglisting:
        pkglisting = package.create_listing(point_of_contact=pkg_user,
                                            collection=collection,
                                            statusname='Approved')
        session.add(pkglisting)
        session.flush()
        pkgdb2.lib.utils.log(session, package, 'package.branch.new', dict(
            agent=user.username,
            package=package.to_json(acls=False),
            package_listing=pkglisting.to_json(),
        ))

    if pkglisting.point_of_contact == pkg_user and status != 'Approved' \
            and acl.startswith('watch'):
        raise PkgdbException(
            'You cannot remove `Watch*` ACLs from the Point of Contact.')

    create = False
    personpkg = model.PackageListingAcl.get(
        session, pkg_user, pkglisting.id, acl=acl)
    if not personpkg:
        personpkg = model.PackageListingAcl.create(
            session, pkg_user, pkglisting.id, acl=acl, status=status)
        create = True

    if not create:
        if personpkg.status == status:
            return

    prev_status = personpkg.status
    if create:
        prev_status = ''

    if not status:
        session.delete(personpkg)
    else:
        personpkg.status = status
    session.flush()
    return pkgdb2.lib.utils.log(session, package, 'acl.update', dict(
        agent=user.username,
        username=pkg_user,
        acl=acl,
        previous_status=prev_status,
        status=status,
        package_name=pkglisting.package.name,
        package_listing=pkglisting.to_json(),
    ))


def update_pkg_poc(session, namespace, pkg_name, pkg_branch, pkg_poc, user,
                   former_poc=None):
    """ Change the point of contact of a package.

    :arg session: session with which to connect to the database.
    :arg namespace: the namespace of the package.
    :arg pkg_name: the name of the package.
    :arg pkg_branch: the branchname of the collection.
    :arg pkg_poc: name of the new point of contact for the package.
    :arg user: the user making the action.
    :kwarg former_poc: used to restrict orphaning the package of a specified
        user which may or may not be the POC of the specified branch.
    :returns: a message informing that the point of contact has been
        successfully changed.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - The ``pkg_name`` does not correspond to any package in the
                database.
            - The ``pkg_branch`` does not correspond to any collection in
                the database.
            - You are not allowed to perform the action, are allowed:
                - pkgdb admins.
                - current point of contact.
                - anyone on orphaned packages.
                - anyone in the group when the point of contact is set to
                    said group.

    """
    _validate_poc(pkg_poc)

    try:
        package = model.Package.by_name(session, namespace, pkg_name)
    except NoResultFound:
        raise PkgdbException('No package found by this name')

    try:
        collection = model.Collection.by_name(session, pkg_branch)
    except NoResultFound:
        raise PkgdbException('No collection found by the name of %s'
                             % pkg_branch)

    pkglisting = model.PackageListing.by_pkgid_collectionid(session,
                                                            package.id,
                                                            collection.id)
    if not pkglisting:
        raise PkgdbException(
            'The package %s/%s could not be found in the collection %s.' %
            (namespace, pkg_name, pkg_branch))

    prev_poc = pkglisting.point_of_contact

    if pkglisting.point_of_contact != user.username \
            and pkglisting.point_of_contact != 'orphan' \
            and not pkgdb2.is_pkgdb_admin(user) \
            and not prev_poc.startswith('group::'):
        raise PkgdbException(
            'You are not allowed to change the point of contact.')

    # Is current PoC a group?
    if prev_poc.startswith('group::'):
        group = prev_poc.split('group::')[1]
        if group not in user.groups:
            raise PkgdbException(
                'You are not part of the group "%s", you are not allowed to'
                ' change the point of contact.' % group)

    if former_poc and former_poc != prev_poc:
        raise PkgdbException(
            'Orphaning restricted to the packages of user %s' % prev_poc)

    pkglisting.point_of_contact = pkg_poc
    session.flush()
    if pkg_poc == 'orphan':
        pkglisting.status = 'Orphaned'
        # Remove commit and watchcommits if the user has them
        for acl in ['commit', 'approveacls']:
            if has_acls(
                    session, user.username, namespace, pkg_name,
                    acl=acl, branch=pkg_branch):
                set_acl_package(
                    session,
                    namespace=namespace,
                    pkg_name=pkg_name,
                    pkg_branch=pkg_branch,
                    pkg_user=user.username,
                    acl=acl,
                    status='Obsolete',
                    user=user,
                )
    elif pkglisting.status in ('Orphaned', 'Retired'):
        pkglisting.status = 'Approved'
        for acl in ACLS:
            if not has_acls(
                    session, pkg_poc, namespace, pkg_name,
                    acl=acl, branch=pkg_branch):
                set_acl_package(
                    session,
                    namespace=namespace,
                    pkg_name=pkg_name,
                    pkg_branch=pkg_branch,
                    pkg_user=pkg_poc,
                    acl=acl,
                    status='Approved',
                    user=user,
                    force=True,
                )

    session.add(pkglisting)
    session.flush()
    output = pkgdb2.lib.utils.log(
        session, pkglisting.package, 'owner.update', dict(
            agent=user.username,
            username=pkg_poc,
            previous_owner=prev_poc,
            package_name=pkglisting.package.name,
            package_listing=pkglisting.to_json(),
        )
    )
    if namespace == 'rpms':
        # Update Bugzilla about new owner
        pkgdb2.lib.utils.set_bugzilla_owner(
            pkg_poc, prev_poc, package.name, collection.name,
            collection.version)

    return output


def update_pkg_status(
        session, namespace, pkg_name, pkg_branch, status, user, poc='orphan'):
    """ Update the status of a package.

    :arg session: session with which to connect to the database.
    :arg pkg_name: the name of the package.
    :arg pkg_branch: the name of the collection.
    :arg user: the user making the action.
    :kwarg namespace: the namespace of the package.
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - The provided ``pkg_name`` does not correspond to any package
                in the database.
            - The provided ``pkg_branch`` does not correspond to any collection
                in the database.
            - The provided ``status`` is not allowed for a package.
            - You are not allowed to perform the action:
                - Deprecate:
                    - user can only deprecate on the devel branch.
                    - admin can deprecate on all branches.
                - Approve:
                    - If you approve an orphaned package you need to
                        specify a point_of_contact: ``poc``.
                - Orphan:
                    - anyone can orphan, this should not raise any exception.
                - Remove:
                    - only admin can remove.

    """
    try:
        package = model.Package.by_name(session, namespace, pkg_name)
    except NoResultFound:
        raise PkgdbException('No package found by this name')

    try:
        collection = model.Collection.by_name(session, pkg_branch)
    except NoResultFound:
        raise PkgdbException('No collection found by this name')

    if status not in ['Approved', 'Removed', 'Retired', 'Orphaned']:
        raise PkgdbException('Status not allowed for a package : %s' %
                             status)

    pkglisting = model.PackageListing.by_pkgid_collectionid(session,
                                                            package.id,
                                                            collection.id)

    if not pkglisting:
        raise PkgdbException('No package %s/%s found in collection %s' % (
                             namespace, pkg_name, pkg_branch))

    prev_status = pkglisting.status
    if status == 'Retired':

        if pkglisting.point_of_contact != user.username \
                and not pkgdb2.is_pkg_admin(
                    session, user, namespace, pkg_name, pkg_branch) \
                and pkglisting.point_of_contact != 'orphan' \
                and not pkgdb2.is_pkgdb_admin(user) \
                and not pkglisting.point_of_contact.startswith('group::'):
            raise PkgdbException(
                'You are not allowed to retire this package.')

        # Admins can deprecate everything
        # Users can deprecate Fedora devel and EPEL branches, which
        # are marked as allowing retiring a package.
        if pkgdb2.is_pkgdb_admin(user) or collection.allow_retire:

            prev_poc = pkglisting.point_of_contact
            pkglisting.status = 'Retired'
            pkglisting.point_of_contact = 'orphan'
            session.add(pkglisting)
            # Remove all ACLs
            for acl in pkglisting.acls:
                acl.status = 'Obsolete'
                session.add(acl)
            session.flush()
            # If the package is retired everywhere, stop monitoring it
            pkg = pkglisting.package
            if pkg.retired_everywhere:
                pkg.monitor = False
                session.flush()
            if prev_status != 'Orphaned':
                # Update Bugzilla about new owner
                pkgdb2.lib.utils.set_bugzilla_owner(
                    poc, prev_poc, package.name, collection.name,
                    collection.version)
        else:
            raise PkgdbException(
                'You are not allowed to retire the '
                'package: %s/%s on branch %s.' % (
                    package.namespace, package.name, collection.branchname))
    elif status == 'Orphaned':
        pkglisting.status = 'Orphaned'
        pkglisting.point_of_contact = 'orphan'
        session.add(pkglisting)
        session.flush()
    elif pkgdb2.is_pkgdb_admin(user):
        prev_poc = None
        if status == 'Approved':
            if pkglisting.status == 'Orphaned' and poc == 'orphan':
                raise PkgdbException(
                    'You need to specify the point of contact of this '
                    'package for this branch to un-orphan it')
            # is the new poc valide:
            _validate_poc(poc)
            prev_poc = pkglisting.point_of_contact
            pkglisting.point_of_contact = poc

        pkglisting.status = status
        session.add(pkglisting)
        session.flush()
        # Update Bugzilla about new owner
        pkgdb2.lib.utils.set_bugzilla_owner(
            poc, prev_poc, package.name, collection.name,
            collection.version)

    else:
        raise PkgdbException(
            'You are not allowed to update the status of '
            'the package: %s/%s on branch %s to %s.' % (
                package.namespace, package.name,
                collection.branchname, status)
        )

    return pkgdb2.lib.utils.log(
        session,
        package,
        'package.update.status',
        dict(
            agent=user.username,
            status=status,
            prev_status=prev_status,
            package_name=package.name,
            package_listing=pkglisting.to_json(),
        )
    )


def search_package(
        session, namespace, pkg_name, pkg_branch=None, pkg_poc=None,
        orphaned=None, critpath=None, status=None, eol=False,
        page=None, limit=None, count=False, case_sensitive=True):
    """ Return the list of packages matching the given criteria.

    :arg session: session with which to connect to the database.
    :arg pkg_name: the name of the package.
    :kwarg pkg_branch: branchname of the collection to search.
    :kwarg pkg_poc: point of contact of the packages searched.
    :kwarg orphaned: boolean to restrict search to orphaned packages.
    :kwarg critpath: Boolean to retrict the search to critpath packages.
    :kwarg status: allows filtering the packages by their status:
        Approved, Retired, Removed, Orphaned.
    :kwarg eol: a boolean to specify whether to include results for
        EOL collections or not. Defaults to False.
        If True, it will return results for all collections (including EOL).
        If False, it will return results only for non-EOL collections.
    :kwarg namespace: the namespace of the packages to restrict with.
    :kwarg page: the page number to apply to the results.
    :kwarg limit: the number of results to return.
    :kwarg count: a boolean to return the result of a COUNT query
       if true, returns the data if false (default).
    :kwarg case_sensitive: a boolean to specify doing a case insensitive
        search. Defaults to True.
    :returns: a list of ``Package`` entry corresponding to the given
        criterias.
    :rtype: list(Package)
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - The provided ``limit`` is not an integer.
            - The provided ``page`` is not an integer.

    """
    if '*' in pkg_name:
        pkg_name = pkg_name.replace('*', '%')
    if orphaned:
        pkg_poc = 'orphan'
        status = 'Orphaned'

    if limit is not None:
        try:
            limit = abs(int(limit))
        except ValueError:
            raise PkgdbException('Wrong limit provided')

    if page is not None:
        try:
            page = abs(int(page))
        except ValueError:
            raise PkgdbException('Wrong page provided')

    if page is not None and page > 0 and limit is not None and limit > 0:
        page = (page - 1) * limit

    return model.Package.search(
        session,
        namespace=namespace,
        pkg_name=pkg_name,
        pkg_poc=pkg_poc,
        pkg_status=status,
        pkg_branch=pkg_branch,
        orphaned=orphaned,
        critpath=critpath,
        eol=eol,
        offset=page,
        limit=limit,
        count=count,
        case_sensitive=case_sensitive,
    )


def search_collection(session, pattern, status=None, page=None,
                      limit=None, count=False):
    """ Return the list of Collection matching the given criteria.

    :arg session: session with which to connect to the database.
    :arg pattern: pattern to match the collection.
    :kwarg status: status of the collection to search for.
    :kwarg page: the page number to apply to the results.
    :kwarg limit: the number of results to return.
    :kwarg count: a boolean to return the result of a COUNT query
            if true, returns the data if false (default).
    :returns: a list of ``Collection`` entry corresponding to the given
        criterias.
    :rtype: list(Collection)
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - The provided ``limit`` is not an integer.
            - The provided ``page`` is not an integer.

    """
    if '*' in pattern:
        pattern = pattern.replace('*', '%')

    if limit is not None:
        try:
            limit = abs(int(limit))
        except ValueError:
            raise PkgdbException('Wrong limit provided')

    if page is not None:
        try:
            page = abs(int(page))
        except ValueError:
            raise PkgdbException('Wrong page provided')

    if page is not None and page > 0 and limit is not None and limit > 0:
        page = (page - 1) * limit

    return model.Collection.search(session,
                                   clt_name=pattern,
                                   clt_status=status,
                                   offset=page,
                                   limit=limit,
                                   count=count)


def search_packagers(session, pattern, eol=False, page=None, limit=None,
                     count=False):
    """ Return the list of Packagers maching the given pattern.

    :arg session: session with which to connect to the database.
    :arg pattern: pattern to match on the packagers.
    :kwarg eol: a boolean to specify whether to include results for
        EOL collections or not. Defaults to False.
        If True, it will return results for all collections (including EOL).
        If False, it will return results only for non-EOL collections.
    :kwarg page: the page number to apply to the results.
    :kwarg limit: the number of results to return.
    :kwarg count: a boolean to return the result of a COUNT query
            if true, returns the data if false (default).
    :returns: a list of ``PackageListing`` entry corresponding to the given
        criterias.
    :rtype: list(PackageListing)
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - The provided ``limit`` is not an integer.
            - The provided ``page`` is not an integer.

    """
    if '*' in pattern:
        pattern = pattern.replace('*', '%')

    if limit is not None:
        try:
            limit = abs(int(limit))
        except ValueError:
            raise PkgdbException('Wrong limit provided')

    if page is not None:
        try:
            page = abs(int(page))
        except ValueError:
            raise PkgdbException('Wrong page provided')

    if page is not None and page > 0 and limit is not None and limit > 0:
        page = (page - 1) * limit

    packagers = model.PackageListing.search_packagers(
        session,
        pattern=pattern,
        eol=eol,
        offset=page,
        limit=limit,
        count=count)

    return packagers


def search_actions(
        session, namespace='rpms', package=None, packager=None,
        action=None, status='Awaiting Review', page=None,
        limit=None, count=False):
    """ Return the list of actions requiring an admin and matching the
    given criteria.

    :arg session: session with which to connect to the database.
    :kwarg package: retrict the logs to a certain package.
    :kwarg packager: restrict the logs to a certain user/packager.
    :kwarg action: restrict the actions to this specific category.
    :kwarg status: restrict the actions to this specific status.
        Defaults to ``Awaiting Review``.
    :kwarg page: the page number to apply to the results.
    :kwarg limit: the number of results to return.
    :kwarg count: a boolean to return the result of a COUNT query
            if true, returns the data if false (default).
    :returns: a list of ``Log`` entry corresponding to the given criterias.
    :rtype: list(Log)
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - The provided ``limit`` is not an integer.
            - The provided ``page`` is not an integer.
            - The ``package`` name specified does not correspond to any
                package.

    """
    if limit is not None:
        try:
            limit = abs(int(limit))
        except ValueError:
            raise PkgdbException('Wrong limit provided')

    if page is not None:
        try:
            page = abs(int(page))
        except ValueError:
            raise PkgdbException('Wrong page provided')

    package_id = None
    if package is not None and namespace is not None:
        package = search_package(session, namespace, package, limit=1)
        if not package:
            raise PkgdbException('No package exists')
        else:
            package_id = package[0].id

    if page is not None and page > 0 and limit is not None and limit > 0:
        page = (page - 1) * limit

    if status and status.lower() == 'all':
        status = None

    return model.AdminAction.search(
        session,
        package_id=package_id,
        packager=packager,
        action=action,
        status=status,
        offset=page,
        limit=limit,
        count=count)


def search_logs(session,namespace=None, package=None, packager=None,
                from_date=None, page=None, limit=None, count=False):
    """ Return the list of Collection matching the given criteria.

    :arg session: session with which to connect to the database.
    :kwarg namespace: the namespace of a package.
    :kwarg package: retrict the logs to a certain package.
    :kwarg packager: restrict the logs to a certain user/packager.
    :kwarg from_date: a date from which to retrieve the logs.
    :kwarg page: the page number to apply to the results.
    :kwarg limit: the number of results to return.
    :kwarg count: a boolean to return the result of a COUNT query
            if true, returns the data if false (default).
    :returns: a list of ``Log`` entry corresponding to the given criterias.
    :rtype: list(Log)
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - The provided ``limit`` is not an integer.
            - The provided ``page`` is not an integer.
            - The ``package`` name specified does not correspond to any
                package.

    """
    if limit is not None:
        try:
            limit = abs(int(limit))
        except ValueError:
            raise PkgdbException('Wrong limit provided')

    if page is not None:
        try:
            page = abs(int(page))
        except ValueError:
            raise PkgdbException('Wrong page provided')

    package_id = None
    if package is not None:
        package = search_package(
            session, namespace, package, limit=1)
        if not package:
            raise PkgdbException('No package exists')
        else:
            package_id = package[0].id

    if page is not None and page > 0 and limit is not None and limit > 0:
        page = (page - 1) * limit

    if from_date:
        # Make sure we get all the events of the day asked
        from_date = from_date + timedelta(days=1)

    return model.Log.search(session,
                            package_id=package_id,
                            packager=packager,
                            from_date=from_date,
                            offset=page,
                            limit=limit,
                            count=count)


def get_acl_packager(
        session, packager, acls=None, eol=False, poc=None,
        page=1, limit=100, count=False):
    """ Return the list of ACL associated with a packager.

    :arg session: session with which to connect to the database.
    :arg packager: the name of the packager to retrieve the ACLs for.
    :kwarg acls: one or more ACLs to restrict the query for.
    :kwarg eol: a boolean to specify whether to include results for
        EOL collections or not. Defaults to False.
        If True, it will return results for all collections (including EOL).
        If False, it will return results only for non-EOL collections.
    :kwarg poc: a boolean specifying whether the results should be
        restricted to ACL for which the provided packager is the point
        of contact or not. Defaults to None.
        If ``True`` it will only return ACLs for packages on which the
        provided packager is point of contact.
        If ``False`` it will only return ACLs for packages on which the
        provided packager is not the point of contact.
        If ``None`` it will not filter the ACLs returned based on the point
        of contact of the package (thus every packages is returned).
    :kwarg page: the page number to apply to the results.
    :kwarg limit: the number of results to return.
    :kwarg count: a boolean to return the result of a COUNT query
            if true, returns the data if false (default).
    :returns: a list of ``PackageListingAcl`` associated to the specified
        user.
    :rtype: list(PackageListingAcl)

    """

    if page is not None:
        try:
            page = abs(int(page))
        except ValueError:
            raise PkgdbException('Wrong page provided')

    if page is not None and page > 0 and limit is not None and limit > 0:
        page = (page - 1) * limit

    return model.PackageListingAcl.get_acl_packager(
        session,
        packager=packager,
        acls=acls,
        eol=eol,
        poc=poc,
        offset=page,
        limit=limit,
        count=count)


def get_critpath_packages(session, branch=None):
    """ Return the list of ACL associated with a packager.

    :arg session: session with which to connect to the database.
    :kwarg branch: the name of the branch to retrieve the critpaths of.
    :returns: a list of ``PackageListing`` marked as being part of critpath.
    :rtype: list(PackageListing)

    """
    return model.PackageListing.get_critpath_packages(
        session, branch=branch)


def get_latest_package(session, limit=10):
    """ Return the list of the most recent packages added to the database.

    :arg session: session with which to connect to the database.
    :kwarg limit: the number of packages to return.
    :returns: a list of ``Package`` ordered from the most recently added
        to the oldest.
    :rtype: list(Package)

    """
    return model.Package.get_latest_package(
        session, limit=limit)


def get_package_maintained(
        session, packager, poc=True, branch=None, eol=False):
    """ Return all the packages and branches where given packager has
    commit acl.

    :arg session: session with which to connect to the database.
    :arg packager: the name of the packager to retrieve the ACLs for.
    :kwarg poc: boolean to specify if the results should be restricted
        to packages where ``user`` is the point of contact or packages
        where ``user`` is not the point of contact.
    :kwarg eol: a boolean to specify wether the output should include
        End Of Life releases or not.
    :returns: a list of ``Package`` associated to the specified user.
    :rtype: list(Package, [Collection])

    """
    output = {}
    for pkg, clt in model.Package.get_package_of_user(
            session, user=packager, poc=poc, eol=eol):
        if branch is not None:
            if clt.branchname != branch:
                continue
        if pkg.name in output:
            output[pkg.name][1].append(clt)
        else:
            output[pkg.name] = [pkg, [clt]]
    return [output[key] for key in sorted(output)]


def get_package_watch(
        session, packager, branch=None, pkg_status=None, eol=False):
    """ Return all the packages and branches that the given packager
    watches.

    :arg session: session with which to connect to the database.
    :arg packager: the name of the packager to retrieve the ACLs for.
    :kwarg pkg_status: the status of the packages considered.
    :kwarg eol: a boolean to specify wether the output should include
        End Of Life releases or not.
    :returns: a list of ``Package`` associated to the specified user.
    :rtype: list(Package, [Collection])

    """
    output = {}
    for pkg, clt in model.Package.get_package_watch_by_user(
            session, packager, pkg_status=pkg_status, eol=eol):

        if branch is not None:
            if clt.branchname != branch:
                continue
        if pkg.name in output:
            output[pkg.name][1].append(clt)
        else:
            output[pkg.name] = [pkg, [clt]]
    return [output[key] for key in sorted(output)]


def add_collection(session, clt_name, clt_version, clt_status,
                   clt_branchname, clt_disttag, clt_koji_name,
                   clt_allow_retire, user):
    """ Add a new collection to the database.

    This method only flushes the new object, nothing is committed to the
    database.

    :arg session: the session with which to connect to the database.
    :kwarg clt_name: the name of the collection.
    :kwarg clt_version: the version of the collection.
    :kwarg clt_status: the status of the collection.
    :kwarg clt_branchname: the branchname of the collection.
    :kwarg clt_disttag: the dist tag of the collection.
    :kwarg clt_koji_name: the name of the collection in koji.
    :kwarg clt_allow_retire: boolean specifying if the collection allows
        retiring a package or not.
    :kwarg user: The user performing the update.
    :returns: a message informing that the collection was successfully
        created.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - You are not allowed to edit a collection, only pkgdb admin can.
            - An error occured while updating the collection in the database
                the message returned is then the error message from the
                database.

    """

    if not pkgdb2.is_pkgdb_admin(user):
        raise PkgdbException('You are not allowed to create collections')

    collection = model.Collection(
        name=clt_name,
        version=clt_version,
        status=clt_status,
        owner=user.username,
        branchname=clt_branchname,
        dist_tag=clt_disttag,
        koji_name=clt_koji_name,
        allow_retire=clt_allow_retire,
    )
    try:
        session.add(collection)
        session.flush()
        pkgdb2.lib.utils.log(session, None, 'collection.new', dict(
            agent=user.username,
            collection=collection.to_json(),
        ))
        return 'Collection "%s" created' % collection.branchname
    except SQLAlchemyError, err:  # pragma: no cover
        pkgdb2.LOG.exception(err)
        raise PkgdbException('Could not add Collection to the database.')


def edit_collection(session, collection, clt_name=None, clt_version=None,
                    clt_status=None, clt_branchname=None, clt_disttag=None,
                    clt_koji_name=None, clt_allow_retire=None, user=None):
    """ Edit a specified collection

    This method only flushes the new object, nothing is committed to the
    database.

    :arg session: the session with which to connect to the database.
    :arg collection: the ``Collection`` object to update.
    :kwarg clt_name: the new name of the collection.
    :kwarg clt_version: the new version of the collection.
    :kwarg clt_status: the new status of the collection.
    :kwarg clt_branchname: the new branchname of the collection.
    :kwarg clt_disttag: the new dist tag of the collection.
    :kwarg clt_koji_name: the name of the collection in koji.
    :kwarg clt_allow_retire: a boolean specifying if the collection allows
        retiring a package.
    :kwarg user: The user performing the update.
    :returns: a message informing that the collection was successfully
        updated.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - You are not allowed to edit a collection, only pkgdb admin can.
            - An error occured while updating the package in the database
                the message returned is a dummy information message to
                return to the user, the trace back is in the logs.

    """

    if not pkgdb2.is_pkgdb_admin(user):
        raise PkgdbException('You are not allowed to edit collections')

    edited = []

    if clt_name and clt_name != collection.name:
        collection.name = clt_name
        edited.append('name')
    if clt_version and clt_version != collection.version:
        collection.version = clt_version
        edited.append('version')
    if clt_status and clt_status != collection.status:
        collection.status = clt_status
        edited.append('status')
    if clt_branchname and clt_branchname != collection.branchname:
        collection.branchname = clt_branchname
        edited.append('branchname')
    if clt_disttag and clt_disttag != collection.dist_tag:
        collection.dist_tag = clt_disttag
        edited.append('dist_tag')
    if clt_koji_name and clt_koji_name != collection.koji_name:
        collection.koji_name = clt_koji_name
        edited.append('koji_name')
    if clt_allow_retire is not None and clt_allow_retire != collection.allow_retire:
        collection.allow_retire = clt_allow_retire
        edited.append('allow_retire')

    if edited:
        try:
            session.add(collection)
            session.flush()
            pkgdb2.lib.utils.log(
                session,
                None,
                'collection.update',
                dict(
                    agent=user.username,
                    fields=edited,
                    collection=collection.to_json(),
                )
            )
            return 'Collection "%s" edited' % collection.branchname
        except SQLAlchemyError, err:  # pragma: no cover
            pkgdb2.LOG.exception(err)
            raise PkgdbException('Could not edit Collection.')


def edit_package(
        session, package, pkg_name=None, pkg_summary=None,
        pkg_description=None, pkg_review_url=None, pkg_upstream_url=None,
        pkg_status=None, user=None):
    """ Edit a specified package

    This method only flushes the new object, nothing is committed to the
    database.

    :arg session: the session with which to connect to the database.
    :arg package: the ``Package`` object to update.
    :kwarg pkg_name: the new name of the package.
    :kwarg pkg_summary: the new summary of the package.
    :kwarg pkg_description: the new description of the package.
    :kwarg pkg_review_url: the new URL to the package review on bugzilla.
    :kwarg pkg_upstream_url: the new URL to the project upstream.
    :kwarg pkg_status: the new status to give to this package.
    :kwarg user: The user performing the update.
    :returns: a message informing that the package was successfully
        updated.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - You are not allowed to edit a package, only pkgdb admin can.
            - An error occured while updating the package in the database
                the message returned is a dummy information message to
                return to the user, the trace back is in the logs.

    """

    if not pkgdb2.is_pkgdb_admin(user):
        raise PkgdbException('You are not allowed to edit packages')

    edited = []

    if pkg_name and pkg_name != package.name:
        package.name = pkg_name
        edited.append('name')
    if pkg_summary and pkg_summary != package.summary:
        package.summary = pkg_summary
        edited.append('summary')
    if pkg_description and pkg_description != package.description:
        package.description = pkg_description
        edited.append('description')
    if pkg_review_url and pkg_review_url != package.review_url:
        package.review_url = pkg_review_url
        edited.append('review_url')
    if pkg_upstream_url and pkg_upstream_url != package.upstream_url:
        package.upstream_url = pkg_upstream_url
        edited.append('upstream_url')
    if pkg_status and pkg_status != package.status:
        package.status = pkg_status
        edited.append('status')

    if edited:
        try:
            session.add(package)
            session.flush()
            pkgdb2.lib.utils.log(session, None, 'package.update', dict(
                agent=user.username,
                fields=edited,
                package=package.to_json(acls=False),
            ))
            return 'Package "%s" edited' % package.name
        except SQLAlchemyError, err:  # pragma: no cover
            pkgdb2.LOG.exception(err)
            raise PkgdbException('Could not edit package.')


def update_collection_status(session, clt_branchname, clt_status, user):
    """ Update the status of a collection.

    This method only flushes the new object, nothing is committed to the
    database.

    :arg session: session with which to connect to the database
    :arg clt_branchname: branchname of the collection
    :arg clt_status: status of the collection
    :returns: a message information whether the status of the collection
        has been updated correclty or if it was not necessary.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - You are not allowed to edit a collection, only pkgdb admin can.
            - An error occured while updating the collection in the database
                the message returned is then the error message from the
                database.
            - The specified collection could not be found in the database.

    """
    if not pkgdb2.is_pkgdb_admin(user):
        raise PkgdbException('You are not allowed to edit collections')

    try:
        collection = model.Collection.by_name(session, clt_branchname)

        if collection.status != clt_status:
            prev_status = collection.status
            collection.status = clt_status
            message = 'Collection updated from "%s" to "%s"' % (
                prev_status, clt_status)
            session.add(collection)
            session.flush()
            pkgdb2.lib.utils.log(session, None, 'collection.update', dict(
                agent=user.username,
                fields=['status'],
                collection=collection.to_json(),
            ))
        else:
            message = 'Collection "%s" already had this status' % \
                clt_branchname

        return message
    except NoResultFound:  # pragma: no cover
        raise PkgdbException('Could not find collection "%s"' %
                             clt_branchname)
    except SQLAlchemyError, err:  # pragma: no cover
        pkgdb2.LOG.exception(err)
        raise PkgdbException('Could not update the status of collection'
                             '"%s".' % clt_branchname)


def get_pending_acl_user(session, user=None):
    """ Return the pending ACLs on any of the packages owned by the
    specified user.
    The method returns a list of dictionnary containing the package name
    the collection branchname, the requested ACL and the user that
    requested that ACL.

    :arg session: session with which to connect to the database.
    :arg user: the user owning the packages on which to retrieve the
        list of pending ACLs.
    :returns: a list of dictionnary containing the pending ACL for the
        specified user.
        The dictionnary has for keys: 'package', 'user', 'collection',
        'acl', 'status'.
    :rtype: [{str():str()}]

    """
    output = []
    for package in model.PackageListingAcl.get_pending_acl(
            session, user=user):
        output.append(
            {
                'package': package.packagelist.package.name,
                'namespace': package.packagelist.package.namespace,
                'user': package.fas_name,
                'collection': package.packagelist.collection.branchname,
                'acl': package.acl,
                'status': package.status,
             }
        )
    return output


def get_acl_user_package(session, user, namespace, package, status=None):
    """ Return the ACLs on a specified package for the specified user.

    The method returns a list of dictionnary containing the package name
    the collection branchname, the requested ACL and the user that
    requested that ACL.

    :arg session: session with which to connect to the database.
    :arg user: the user owning the packages on which to retrieve the
        list of pending ACLs.
    :arg package: the package for which to check the acl.
    :kwarg status: the status of the package to retrieve the ACLs of.
    :returns: a list of dictionnary containing the ACL the specified user
        has on a specific package.
        The dictionnary has for keys: 'package', 'user', 'collection',
        'acl', 'status'.
    :rtype: [{str():str()}]

    """
    output = []
    for package in model.PackageListingAcl.get_acl_package(
            session, user, namespace, package, status=status):
        output.append(
            {'package': package.packagelist.package.name,
             'user': package.fas_name,
             'collection': package.packagelist.collection.branchname,
             'collection_status': package.packagelist.collection.status,
             'acl': package.acl,
             'status': package.status,
             }
        )
    return output


def has_acls(session, user, namespace, package, acl, branch=None):
    """ Return wether the specified user has *one of* the specified acl on
    the specified package.

    If several ACLs are specified, having one of them will return True.

    :arg session: session with which to connnect to the database.
    :arg user: the name of the user for which to check the acl.
    :arg package: the name of the package on which the acl should be
        checked.
    :arg acl: one or more ACLs to check for the user on the package.
    :kwarg branch: restrict the check to the specified branch
    :returns: a boolean specifying whether specified user has this ACL on
        this package and branch.
    :rtype: bool()

    """
    if package is None or acl is None:
        return False

    acls = get_acl_user_package(
        session, user=user, namespace=namespace,
        package=package, status='Approved')

    if isinstance(acl, basestring):
        acl = [acl]

    user_has_acls = False
    for user_acl in acls:
        if not branch and user_acl['acl'] in acl:
            user_has_acls = True
            break
        elif branch and user_acl['collection'] == branch \
                and user_acl['acl'] in acl:
            user_has_acls = True
            break
    return user_has_acls


def get_status(session, status='all'):
    """ Return a dictionnary containing all the status and acls.

    :arg session: session with which to connnect to the database.
    :kwarg status: single keyword or multiple keywords used to retrict
        querying only for some of the status rather than all.
        Defaults to 'all' other options are: clt_status, pkg_status,
        pkg_acl, acl_status.
    :returns: a dictionnary with all the status extracted from the database,
        keys are: clt_status, pkg_status, pkg_acl, acl_status.
    :rtype: dict(str():list())

    """
    output = {}

    if status == 'all':
        status = [
            'clt_status', 'pkg_status', 'pkg_acl', 'acl_status',
            'admin_status', 'namespaces',
        ]
    elif isinstance(status, basestring):
        status = [status]

    if 'clt_status' in status:
        output['clt_status'] = model.CollecStatus.all_txt(session)
    if 'pkg_status' in status:
        output['pkg_status'] = model.PkgStatus.all_txt(session)
    if 'pkg_acl' in status:
        output['pkg_acl'] = model.PkgAcls.all_txt(session)
    if 'acl_status' in status:
        output['acl_status'] = model.AclStatus.all_txt(session)
    if 'admin_status' in status:
        output['admin_status'] = model.ActionStatus.all_txt(session)
    if 'namespaces' in status:
        output['namespaces'] = model.Namespace.all_txt(session)

    return output


def get_top_maintainers(session, top=10):
    """ Return the specified top maintainer having the most commit rights

    :arg session: session with which to connect to the database.
    :arg top: the number of results to return, defaults to 10.
    :returns: a list of tuple of type: (username, number_of_packages).
    :rtype: list(tuple())

    """
    return model.PackageListingAcl.get_top_maintainers(session, top)


def get_top_poc(session, top=10):
    """ Return the specified top point of contact.

    :arg session: session with which to connect to the database.
    :arg top: the number of results to return, defaults to 10.
    :returns: a list of tuple of type: (username, number_of_poc).
    :rtype: list(tuple())

    """
    return model.PackageListing.get_top_poc(session, top)


def unorphan_package(
        session, namespace, pkg_name, pkg_branch, pkg_user, user):
    """ Unorphan a specific package in favor of someone and give him the
    appropriate ACLs.

    This method only flushes the changes, nothing is committed to the
    database.

    :arg session: session with which to connect to the database.
    :arg pkg_name: the name of the package.
    :arg pkg_branch: the name of the collection.
    :arg pkg_user: the FAS user requesting the package.
    :arg user: the user making the action.
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - The package name provided does not correspond to any package
                in the database.
            - The package could not be found in the specified branch
            - The package is not orphaned in the specified branch
            - You are are trying to unorphan the package for someone else
                while you are not a pkgdb admin
            - You are trying to unorphan the package while you are not a
                packager.

    """
    _validate_poc(pkg_user)

    try:
        package = model.Package.by_name(session, namespace, pkg_name)
    except NoResultFound:
        raise PkgdbException('No package found by this name')

    try:
        collection = model.Collection.by_name(session, pkg_branch)
    except NoResultFound:
        raise PkgdbException('No collection found by this name')

    pkg_listing = get_acl_package(
        session, namespace, pkg_name, pkg_clt=pkg_branch)
    if not pkg_listing:
        raise PkgdbException(
            'Package "%s/%s" is not in the collection %s'
            % (namespace, pkg_name, pkg_branch))
    pkg_listing = pkg_listing[0]

    if pkg_listing.status not in ('Orphaned', 'Retired'):
        raise PkgdbException(
            'Package "%s/%s" is not orphaned on %s' % (
                namespace, pkg_name, pkg_branch))

    if not pkgdb2.is_pkgdb_admin(user):
        if user.username != pkg_user and not pkg_user.startswith('group::'):
            raise PkgdbException('You are not allowed to update ACLs of '
                                 'someone else.')
        elif user.username == pkg_user and 'packager' not in user.groups:
            raise PkgdbException('You must be a packager to take a package.')

    status = 'Approved'
    pkg_listing.point_of_contact = pkg_user
    pkg_listing.status = status
    session.add(pkg_listing)
    session.flush()

    pkgdb2.lib.utils.log(session, pkg_listing.package, 'owner.update', dict(
        agent=user.username,
        username=pkg_user,
        previous_owner="orphan",
        status=status,
        package_name=pkg_listing.package.name,
        package_listing=pkg_listing.to_json(),
    ))
    if namespace == 'rpms':
        pkgdb2.lib.utils.set_bugzilla_owner(
            pkg_user, None, package.name, collection.name,
            collection.version)

    acls = ['commit', 'watchbugzilla', 'watchcommits', 'approveacls']

    for acl in acls:
        personpkg = model.PackageListingAcl.get(
            session, pkg_user, pkg_listing.id, acl=acl)
        if not personpkg:
            personpkg = model.PackageListingAcl.create(
                session, pkg_user, pkg_listing.id, acl=acl, status=status)

        prev_status = personpkg.status
        personpkg.status = status
        session.add(personpkg)

        pkgdb2.lib.utils.log(session, pkg_listing.package, 'acl.update', dict(
            agent=user.username,
            username=pkg_user,
            acl=acl,
            previous_status=prev_status,
            status=status,
            package_name=pkg_listing.package.name,
            package_listing=pkg_listing.to_json(),
        ))

    session.flush()
    return 'Package %s/%s has been unorphaned on %s by %s' % (
        namespace, pkg_name, pkg_branch, pkg_user
    )


def add_branch(session, clt_from, clt_to, user):
    """ Clone a the permission from a branch to another.

    This method only flushes the new objects, the only thing committed is
    the log message when the branching starts.

    :arg session: session with which to connect to the database.
    :arg clt_from: the ``branchname`` of the collection to branch from.
    :arg clt_to: the ``branchname`` of the collection to branch to.
    :arg user: the user making the action.
    :returns: a list of errors generated while branching, these errors
        might be the results of trying to create a PackageListing object
        already existing.
    :rtype: list(str)
    :raises pkgdb2.lib.PkgdbException: There are three conditions leading to
        this exception beeing raised:
            - You are not allowed to branch (only pkgdb admin can do it)
            - The specified branch from is invalid (does not exist)
            - The specified branch to is invalid (does not exist).

    """
    if not pkgdb2.is_pkgdb_admin(user):
        raise PkgdbException('You are not allowed to branch: %s to %s' % (
            clt_from, clt_to))

    try:
        clt_from = model.Collection.by_name(session, clt_from)
    except NoResultFound:
        raise PkgdbException('Branch %s not found' % clt_from)

    try:
        clt_to = model.Collection.by_name(session, clt_to)
    except NoResultFound:
        raise PkgdbException('Branch %s not found' % clt_to)

    pkgdb2.lib.utils.log(session, None, 'branch.start', dict(
        agent=user.username,
        collection_from=clt_from.to_json(),
        collection_to=clt_to.to_json(),
    ))
    session.commit()

    messages = []
    for pkglist in model.PackageListing.by_collectionid(
            session, clt_from.id):
        if pkglist.status in ('Approved','Orphaned'):
            try:
                pkglist.branch(session, clt_to)
                # Should not fail since the flush() passed
                session.commit()
                messages.append(
                    '%s/%s branched successfully from %s to %s %s' % (
                        pkglist.package.namespace, pkglist.package.name,
                        clt_from.name, clt_to.name, clt_to.version))
            except SQLAlchemyError, err:  # pragma: no cover
                session.rollback()
                pkgdb2.LOG.debug(err)
                messages.append(
                    'FAILED: %s/%s failed to branch from %s to %s %s' % (
                        pkglist.package.namespace, pkglist.package.name,
                        clt_from.name, clt_to.name, clt_to.version))
                messages.append(str(err))

    pkgdb2.lib.utils.log(session, None, 'branch.complete', dict(
        agent=user.username,
        collection_from=clt_from.to_json(),
        collection_to=clt_to.to_json(),
    ))

    return messages


def add_new_branch_request(session, namespace, pkg_name, clt_to, user):
    """ Register a new branch request.

    :arg session: session with which to connect to the database.
    :arg pkg_name: the name of the package for which to create the branch.
    :arg clt_to: the ``branchname`` of the collection to branch to.
    :arg user: the user making the action.
    :raises pkgdb2.lib.PkgdbException: There are three conditions leading to
        this exception beeing raised:
            - The specified package does not exists.
            - The specified branch from is invalid (does not exist)
            - The specified branch to is invalid (does not exist)
            - The user requesting is not a packager

    """
    try:
        package = model.Package.by_name(session, namespace, pkg_name)
    except NoResultFound:
        raise PkgdbException(
            'Package %s/%s not found' % (namespace, pkg_name))

    try:
        clt_to = model.Collection.by_name(session, clt_to)
    except NoResultFound:
        raise PkgdbException('Branch %s not found' % clt_to)

    _validate_poc(user.username)
    pkg_admin = has_acls(
        session, user.username, namespace, pkg_name, 'approveacls')

    status = 'Pending'
    if pkg_admin:
        status = 'Awaiting Review'

    if clt_to.name == 'Fedora EPEL':
        _validate_pkg(session, clt_to.version, package.name)

    actions = model.AdminAction.search(
        session,
        package_id=package.id,
        collection_id=clt_to.id,
        action='request.branch',
        user=user.username,
    )
    if actions:
        action = actions.pop()
        action._status = status
        action.message = None
    else:
        action = model.AdminAction(
            package_id=package.id,
            collection_id=clt_to.id,
            user=user.username,
            _status=status,
            action='request.branch',
        )

    session.add(action)

    pkgdb2.lib.utils.log(
        session,
        package=package,
        topic='package.branch.request',
        message=dict(
            agent=user.username,
            package=package.to_json(acls=False),
            collection_to=clt_to.to_json(),
        )
    )

    msg = 'Branch %s requested for user %s' % (
        clt_to.branchname, user.username)

    # If user is packager -> checked with _validate_poc()
    # If clt_to is Fedora
    # If user has approveacls on pkg_name
    # Then automatically grant the branch request
    if clt_to.name == 'Fedora' and pkg_admin:
        for acl in ['commit', 'watchbugzilla',
                    'watchcommits', 'approveacls']:
            set_acl_package(
                session,
                namespace=namespace,
                pkg_name=package.name,
                pkg_branch=clt_to.branchname,
                pkg_user=user.username,
                acl=acl,
                status='Approved',
                user=user,
                force=True,
            )
        msg = 'Branch %s created for user %s' % (
            clt_to.branchname, user.username)

        # The branch is created, so the action has been approved
        action._status = 'Approved'
        session.add(action)

    return msg


def add_new_package_request(
        session, pkg_name, pkg_summary, pkg_description, pkg_status,
        pkg_collection, pkg_poc, user, pkg_review_url, pkg_namespace='rpms',
        pkg_upstream_url=None, pkg_critpath=False):
    """ Create a new Package request in the database.

    :arg session: session with which to connect to the database.
    :arg pkg_name: the name of the package.
    :arg pkg_summary: a summary description of the package.
    :arg pkg_description: the description of the package.
    :arg pkg_status: the status of the package.
    :arg pkg_collection: the collection in which had the package.
    :arg pkg_poc: the point of contact for this package in this collection
    :arg user: the user performing the action
    :kwarg pkg_namespace: the namespace of the package, defaults to 'rpms'
    :kwarg pkg_review_url: the url of the review-request on the bugzilla
    :kwarg pkg_upstream_url: the url of the upstream project.
    :kwarg pkg_critpath: a boolean specifying if the package is marked as
        being in critpath.
    :returns: a message informing that the request has been successfully
        created.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - Invallid pkg_poc provided
            - Something went wrong when adding the request to the database
    :raises sqlalchemy.orm.exc.NoResultFound: when there is no collection
        found in the database with the name ``pkg_collection``.

    """
    _validate_poc(pkg_poc)

    try:
        clt = model.Collection.by_name(session, pkg_collection)
    except NoResultFound:
        raise PkgdbException('Branch %s not found' % pkg_collection)

    # Prevent asking for an existing package
    package = None
    try:
        package = model.Package.by_name(session, pkg_namespace, pkg_name)
    except NoResultFound:
        pass
    if package:
        raise PkgdbException(
            'There is already a package named: %s/%s' % (pkg_namespace,
                                                         pkg_name))

    if pkg_collection.startswith(('el', 'epel')):
        _validate_pkg(session, pkg_collection[-1:], pkg_name)

    info = {
        'pkg_name': pkg_name.strip(),
        'pkg_summary': pkg_summary.strip(),
        'pkg_description': pkg_description.strip() if pkg_description else None,
        'pkg_status': pkg_status.strip(),
        'pkg_collection': pkg_collection.strip(),
        'pkg_poc': pkg_poc.strip(),
        'pkg_review_url': pkg_review_url.strip() if pkg_review_url else None,
        'pkg_upstream_url': pkg_upstream_url.strip() if pkg_upstream_url else None,
        'pkg_critpath': pkg_critpath,
        'pkg_namespace': pkg_namespace,
    }

    action = model.AdminAction(
        package_id=None,
        collection_id=clt.id,
        user=user.username,
        _status='Awaiting Review',
        action='request.package',
        info=json.dumps(info),
    )

    session.add(action)

    return pkgdb2.lib.utils.log(session, None, 'package.new.request', dict(
        agent=user.username,
        package=None,
        collection=clt.to_json(),
        info=info,
    ))


def add_unretire_request(
        session, namespace, pkg_name, pkg_branch, review_url, user):
    """ Register a new request to un-retire a package.

    This method only flushes the new objects.

    :arg session: session with which to connect to the database.
    :arg namespace: the namespace of the package to unretire.
    :arg pkg_name: the name of the package to unretire.
    :arg clt_to: the ``branchname`` of the collection to unretire.
    :arg review_url: the url of the new review.
    :arg user: the user making the action.
    :raises pkgdb2.lib.PkgdbException: There are three conditions leading to
        this exception beeing raised:
            - The specified package does not exists.
            - The specified branch is invalid (does not exist)
            - The user requesting is not a packager

    """
    try:
        package = model.Package.by_name(session, namespace, pkg_name)
    except NoResultFound:
        raise PkgdbException(
            'Package %s/%s not found' % (namespace, pkg_name))

    try:
        pkg_branch = model.Collection.by_name(session, pkg_branch)
    except NoResultFound:
        raise PkgdbException('Branch %s not found' % pkg_branch)

    _validate_poc(user.username)

    action = model.AdminAction(
        package_id=package.id,
        collection_id=pkg_branch.id,
        user=user.username,
        _status='Awaiting Review',
        action='request.unretire',
        info=json.dumps({'pkg_review_url': review_url}),
    )

    session.add(action)

    return pkgdb2.lib.utils.log(
        session, None, 'package.unretire.request', dict(
            agent=user.username,
            package=package.to_json(),
            collection=pkg_branch.to_json(),
        )
    )


def count_collection(session):
    """ Return the number of package 'Approved' for each collection.

    :arg session: the session to connect to the database with.

    """
    return model.Package.count_collection(session)


def count_fedora_collection(session):
    """ Return the number of package 'Approved' for each Fedora collection.

    :arg session: the session to connect to the database with.

    """
    collections_fedora = model.Package.count_fedora_collection(session)

    if collections_fedora:
        # We need to get devel out to sort the releases correctly
        devel = collections_fedora.pop()
        collections_fedora = [[int(item[0]), item[1]]
                              for item in collections_fedora]

        collections_fedora.sort(key=operator.itemgetter(1))
        collections_fedora.append(devel)

    return collections_fedora


def get_groups(session):
    """ Return the list of FAS groups involved in maintaining packages in
    the database

    :arg session: the session to connect to the database with.

    """
    return model.get_groups(session)


def notify(session, eol=False, name=None, version=None, acls=None):
    """ Return the user that should be notify for each package.

    :arg session: the session to connect to the database with.
    :kwarg eol: a boolean to specify wether the output should include End
        Of Life releases or not.
    :kwarg name: restricts the output to a specific collection name.
    :kwarg version: restricts the output to a specific collection version.
    :kwarg acls: a list of ACLs to filter the package/user to retrieve.
        If no acls is specified it defaults to
        ``['watchcommits', 'watchbugzilla', 'commit']`` which means that it
        will return any person having one of these three acls for each
        package in the database.
        If the acls specified is ``all`` then all ACLs are used.

    """
    output = {}
    pkgs = model.notify(session=session, eol=eol, name=name,
                        version=version, acls=acls)
    for pkg in pkgs:
        if pkg[0] in output:  # pragma: no cover
            output[pkg[0]] += ',' + pkg[1]
        else:
            output[pkg[0]] = pkg[1]
    return output


def bugzilla(session, name=None):
    """ Return the information to sync ACLs with bugzilla.

    :arg session: the session to connect to the database with.
    :kwarg name: restricts the output to a specific collection name.

    """
    output = {}
    pkgs = model.bugzilla(session=session, name=name)

    # 0  Collection.name
    # 1  Collection.version
    # 2  Package.name
    # 3  Package.summary
    # 4  PackageListing.point_of_contact
    # 5  PackageListingAcl.fas_name
    # 6  Collection.branchname

    for pkg in pkgs:
        version = pkg[1]
        if pkg[1] == 'devel':
            if pkg[4] != 'orphan':
                version = 10000
            else:
                version = 0

        if pkg[0] in output:
            if pkg[2] in output[pkg[0]]:
                # Check poc
                if pkg[4] == 'orphan':
                    pass
                elif output[pkg[0]][pkg[2]]['poc'] == 'orphan':
                    output[pkg[0]][pkg[2]]['poc'] = pkg[4]
                    output[pkg[0]][pkg[2]]['version'] = version
                elif int(version) > int(output[pkg[0]][pkg[2]]['version']):
                    output[pkg[0]][pkg[2]]['poc'] = pkg[4]
                    output[pkg[0]][pkg[2]]['version'] = version
                # If #5 is not poc, add it to cc
                if pkg[5] != 'orphan' \
                        and pkg[5] != output[pkg[0]][pkg[2]]['poc'] \
                        and pkg[5] not in output[pkg[0]][pkg[2]]['cc']:
                    if output[pkg[0]][pkg[2]]['cc']:
                        output[pkg[0]][pkg[2]]['cc'] += ','
                    output[pkg[0]][pkg[2]]['cc'] += pkg[5]
            else:
                cc = ''
                if pkg[5] != pkg[4]:  # pragma: no cover
                    cc = pkg[5]
                output[pkg[0]][pkg[2]] = {
                    'collection': pkg[0],
                    'name': pkg[2],
                    'summary': pkg[3],
                    'poc': pkg[4],
                    'qa': '',
                    'cc': cc,
                    'version': version,
                }
        else:
            cc = ''
            if pkg[5] != pkg[4]:
                cc = pkg[5]
            output[pkg[0]] = {
                pkg[2]: {
                    'collection': pkg[0],
                    'name': pkg[2],
                    'summary': pkg[3],
                    'poc': pkg[4],
                    'qa': '',
                    'cc': cc,
                    'version': version,
                }
            }

    return output


def _vcs_acls_json(packages, skip_pp=None):
    """ For a given list of package/user/branch build a dict of dict
    representating of who has commit access to which package.

    The output dict is something like:

    {
      pkg1: {
        branch1: {
          name: pkg1,
          branch: branch1,
          people: [user1, user2],
          groups: [group1, group2]
        },
        branch2: {
          name: pkg1,
          branch: branch2,
          people: [user1],
          groups: [group1, group3]
        },
      },
      pkg2:
      ...
    }
    """
    output = {}
    for pkgname, username, branchname, namespace in packages:
        user = None
        group = None

        if username and username.startswith('group::'):
                group = username.replace('group::', '')
        else:
            user = username

        if namespace not in output:
            output[namespace] = {}

        if pkgname not in output[namespace]:
            output[namespace][pkgname] = {}

        if branchname not in output[namespace][pkgname]:
            groups = []
            if skip_pp and pkgname not in skip_pp:
                groups.append('provenpackager')

            output[namespace][pkgname][branchname] = {
                'commit': {'groups': groups, 'people': []},
            }

        if group:
            output[namespace][pkgname][branchname
                ]['commit']['groups'].append(group)
        if user:
            output[namespace][pkgname][branchname
                ]['commit']['people'].append(user)
    return output


def _vcs_acls_text(packages, skip_pp=None):
    """ For a given list of package/user/branch return a dict of dict of dict
    listing for each package, for each branch who has access to what.

    The output dict is something like:

    {
      pkg1: {
        branch1: {
          name: "pkg1",
          branch: "branch1",
          user: "user1, user2",
          group: "@group1, @group2",
        },
        branch2: {
          name: "pkg1",
          branch: "branch2",
          user: "user1",
          group: "@group1, @group3"
        },
      },
      pkg2:
      ...
      }
    }

    """
    output = {}
    for pkgname, username, branchname, namespace in packages:
        user = None
        group = None
        if username and username.startswith('group::'):
                group = username.replace('group::', '@')
        else:
            user = username

        groups = ''
        if pkgname not in skip_pp:
            groups = '@provenpackager'

        if pkgname in output:
            if branchname in output[pkgname]:
                if user:
                    if output[pkgname][branchname]['user']:
                        output[pkgname][branchname]['user'] += ','
                    output[pkgname][branchname]['user'] += user
                elif group:  # pragma: no cover
                    if output[pkgname][branchname]['group'].strip():
                        output[pkgname][branchname]['group'] += ','
                    output[pkgname][branchname]['group'] += group
            else:
                if group and groups:  # pragma: no cover
                    group = ',' + group


                output[pkgname][branchname] = {
                    'name': pkgname,
                    'user': user or '',
                    'group': groups + (group or ''),
                    'branch': branchname,
                    'namespace': namespace,
                }
        else:
            if group and groups:
                group = ',' + group
            output[pkgname] = {
                branchname: {
                    'name': pkgname,
                    'user': user or '',
                    'group': groups + (group or ''),
                    'branch': branchname,
                    'namespace': namespace,
                }
            }
    return output


def vcs_acls(
        session, eol=False, collection=None, oformat='text', skip_pp=None,
        namespace=None):
    """ Return the information to sync ACLs with gitolite.

    :arg session: the session to connect to the database with.
    :kwarg eol: A boolean specifying whether to include information about
        End Of Life collections or not. Defaults to ``False``.
    :kwarg collection: Restrict the VCS info to a specific collection.
    :kwarg oformat: Output format to returned the data as, defaults to `text`
        can be `JSON`.
    :kwarg skip_pp: A boolean to specify if we want to skip provenpackager
        for some packages
    :kwarg namespace: Restrict the ACLs returned to a given namespace

    """
    output = {}
    pkgs = model.vcs_acls(
        session=session, eol=eol, collection=collection, namespace=namespace)
    if oformat == 'json':
        output = _vcs_acls_json(pkgs, skip_pp)
    else:
        output = _vcs_acls_text(pkgs, skip_pp)
    return output


def set_critpath_packages(
        session, namespace, pkg_name, pkg_branch, critpath=True, user=None):
    """ Set the provided critpath status on a specified package.

    This method can be used to set or unset the critpath flag of a package
    on the specified branches.

    :arg session: the session with which to connect to the database.
    :arg namespace: the namespce to search the package in.
    :arg pkg_name: The name of the package to update.
    :arg pkg_branch: The branchname of the collection to update
    :kwarg user: The user performing the update.
    :returns: a message informing that the package was successfully
        updated.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - You are not allowed to edit a package, only pkgdb admin can.
            - The package cannot be found in the database.
            - The branch cannot be found in the database.
            - The package does not have the branch specified.
            - An error occured while updating the package in the database
                the message returned is a dummy information message to
                return to the user, the trace back is in the logs.

    """

    if not pkgdb2.is_pkgdb_admin(user):
        raise PkgdbException('You are not allowed to edit packages')

    try:
        package = model.Package.by_name(session, namespace, pkg_name)
    except NoResultFound:
        raise PkgdbException(
            'No package found by this name: %s/%s' % (namespace, pkg_name))

    try:
        collection = model.Collection.by_name(session, pkg_branch)
    except NoResultFound:
        raise PkgdbException('No collection found by the name of %s'
                             % pkg_branch)

    pkglisting = model.PackageListing.by_pkgid_collectionid(session,
                                                            package.id,
                                                            collection.id)

    if not pkglisting:
        raise PkgdbException(
            '%s/%s was not found in the collection %s' % (
                namespace, pkg_name, pkg_branch))

    msg = None
    branches = []
    if critpath != pkglisting.critpath:
        pkglisting.critpath = critpath
        branches.append(pkglisting.collection.branchname)
        msg = '%s/%s: critpath updated on %s to %s' % (
            package.namespace, package.name,
            pkglisting.collection.branchname, critpath)
        session.add(pkglisting)

    try:
        session.add(package)
        session.flush()
        pkgdb2.lib.utils.log(session, None, 'package.critpath.update', dict(
            agent=user.username,
            critpath=critpath,
            branches=branches,
            package=package.to_json(),
        ))
    except SQLAlchemyError, err:  # pragma: no cover
        pkgdb2.LOG.exception(err)
        raise PkgdbException('Could not edit package.')

    return msg


def get_monitored_package(session):
    """ Return the list of packaged flag as `to monitor`.

    :arg session: the session with which to connect to the database.
    :returns: a list of Package.
    :rtype: list()

    """

    return model.Package.get_monitored(session)


def get_koschei_monitored_package(session):
    """ Return the list of packaged marked to be monitored by koschei.

    :arg session: the session with which to connect to the database.
    :returns: a list of Package.
    :rtype: list()

    """

    return model.Package.get_koschei_monitored(session)


def set_monitor_package(session, namespace, pkg_name, status, user):
    """ Set the provided status on the monitoring flag of the specified
    package.

    :arg session: the session with which to connect to the database.
    :arg namespace: The namespace of the package to update.
    :arg pkg_name: The name of the package to update.
    :arg status: boolean specifying the monitor status to set
    :arg user: The user performing the update.
    :returns: a message informing that the package was successfully
        updated.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception being raised:
            - You are not allowed to edit a package, only pkgdb admin can.
            - The package cannot be found in the database.
            - An error occured while updating the package in the database
                the message returned is a dummy information message to
                return to the user, the trace back is in the logs.

    """

    package = None
    try:
        package = model.Package.by_name(session, namespace, pkg_name)
    except NoResultFound:
        raise PkgdbException('No package found by this name')

    pkger = has_acls(
        session, user.username, namespace, pkg_name, ['commit', 'approveacls'])
    if not (pkger or pkgdb2.is_pkgdb_admin(user)):
        raise PkgdbException(
            'You are not allowed to update the monitor flag on this package'
        )

    msg = 'Monitoring status un-changed'
    if package.monitoring_status != status:
        package.monitor = status
        session.add(package)

        msg = 'Monitoring status of %s/%s set to %s' % (
            package.namespace, pkg_name, package.monitoring_status)

        try:
            session.flush()
            pkgdb2.lib.utils.log(
                session, package, 'package.monitor.update', dict(
                    agent=user.username,
                    status=status,
                    package=package.to_json(acls=False),
                )
            )
        except SQLAlchemyError, err:  # pragma: no cover
            pkgdb2.LOG.exception(err)
            raise PkgdbException('Could not update monitoring status.')

    return msg


def set_koschei_monitor_package(session, namespace, pkg_name, status, user):
    """ Set the provided status on the koscehi monitoring flag of the
    specified package.

    :arg session: the session with which to connect to the database.
    :arg namespace: the namespace of the package to update.
    :arg pkg_name: The name of the package to update.
    :arg status: boolean specifying the monitor status to set
    :arg user: The user performing the update.
    :returns: a message informing that the package was successfully
        updated.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception being raised:
            - You are not allowed to edit a package, only pkgdb admin can.
            - The package cannot be found in the database.
            - An error occured while updating the package in the database
                the message returned is a dummy information message to
                return to the user, the trace back is in the logs.

    """

    package = None
    try:
        package = model.Package.by_name(session, namespace, pkg_name)
    except NoResultFound:
        raise PkgdbException('No package found by this name')

    if not 'packager' in user.groups:
        raise PkgdbException(
            'You are not allowed to update the koschei monitoring flag on '
            'this package'
        )

    msg = 'Koschei monitoring status un-changed'
    if package.koschei != status:
        package.koschei = status
        session.add(package)

        msg = 'Koschei monitoring status of %s/%s set to %s' % (
            package.namespace, pkg_name, package.koschei)

        try:
            session.flush()
            pkgdb2.lib.utils.log(
                session, package, 'package.koschei.update', dict(
                    agent=user.username,
                    status=status,
                    package=package.to_json(acls=False),
                )
            )
        except SQLAlchemyError, err:  # pragma: no cover
            pkgdb2.LOG.exception(err)
            raise PkgdbException(
                'Could not update Koschei monitoring status.')

    return msg


def get_admin_action(session, action_id):
    """ For a given Admin Action identifier, return the Admin Action object
    having this identifier.

    :arg session: the session with which to connect to the database.
    :arg action_id: The identifier of the admin action to retrieve.
    :returns: an Admin Action object having the specified identifier.
    :rtype: AdminAction()

    """
    return model.AdminAction.get(session, action_id)


def edit_action_status(
        session, admin_action, action_status, user, message=None):
    """ Update the status of the given Admin Action if the user is allowed
    to.

    :arg session: the session with which to connect to the database.
    :arg admin_action: a AdminAction object whose status is to update.
    :arg action_status: the status to update the provided AdminAdction to.
    :arg user: the user doing the action.
    :kwarg message: the message required when an action is denied explaining
        why it was denied.
    :returns: a string informing if the action was successfull
    :rtype: str
    :raises pkgdb2.lib.PkgdbException: This exception is raised when the
        user performing the action is not a pkgdb admin.

    """
    pkgdb_admin = pkgdb2.is_pkgdb_admin(user)
    if admin_action.package:
        pkg_admin = has_acls(
            session, user.username, admin_action.package.namespace,
            admin_action.package.name, 'approveacls')
    else:
        pkg_admin = False
    requester = admin_action.user == user.username

    if action_status == 'Pending':
        if not pkg_admin and not pkgdb_admin and not requester:
            raise PkgdbException(
                'You are not allowed to edit this request')
    elif action_status in ['Awaiting Review', 'Blocked']:
        # Requester can re-set 'request.unretire' to 'Awaiting Review'
        if (pkg_admin or pkgdb_admin or
                (requester and admin_action.action == 'request.unretire')):
            pass
        else:
            raise PkgdbException(
                'You are not allowed to review this request')
    elif action_status in ['Obsolete']:
        if not requester:
            raise PkgdbException(
                'Only the person having made the request can change its '
                'status to obsolete')
    elif not pkgdb_admin:
        raise PkgdbException('You are not allowed to edit admin action')

    if action_status in ['Blocked', 'Denied'] and not message:
        raise PkgdbException(
            'You must provide a message explaining why when you block or '
            'deny a request')

    edit = []
    old_status = admin_action.status
    if admin_action.status != action_status:
        admin_action._status = action_status
        edit.append('status')

    if admin_action.message != message:
        admin_action.message = message

    if edit:
        try:
            session.add(admin_action)
            session.flush()
            msg = pkgdb2.lib.utils.log(
                session,
                package=admin_action.package,
                topic='admin.action.status.update',
                message=dict(
                    agent=user.username,
                    old_status=old_status,
                    new_status=action_status,
                    action=admin_action.to_json(),
                ))
        except SQLAlchemyError, err:
            session.rollback()
            pkgdb2.LOG.exception(err)
            raise PkgdbException('Could not edit action.')

        # Approve the request.branch awaiting review on this package now
        # that it was approved
        if action_status == 'Approved' \
                and admin_action.action == 'request.package':
            pkg = admin_action.info_data.get('pkg_name')
            if pkg:
                requests = search_actions(
                    session, package=pkg, action='request.package',
                    status='Awaiting Review')
                requests.extend(search_actions(
                    session, package=pkg, action='request.branch',
                    status='Awaiting Review'))
                for req in requests:
                    if req.collection.name.lower() != 'fedora':
                        continue
                    for acl in ['commit', 'watchbugzilla',
                                'watchcommits', 'approveacls']:
                        set_acl_package(
                            session,
                            pkg_name=pkg,
                            pkg_branch=req.collection.branchname,
                            pkg_user=user.username,
                            acl=acl,
                            status='Approved',
                            user=user,
                            force=True,
                        )
                    edit_action_status(session, req, 'Approved', user=user)

    else:
        msg = 'Nothing to change.'

    return msg


def get_retired_packages(session, collection):
    """ Return the list of packaged retired on all active collections
    belonging to the collectin specified.

    :arg session: the session with which to connect to the database.
    :arg collection: the collection name to filter the package retired.
    :returns: a list of Package.
    :rtype: list()

    """

    return model.Package.get_retired(session, collection)


def add_namespace(session, namespace, user):
    """ Add a new namespace to the database.

    This method only flushes the new object, nothing is committed to the
    database.

    :arg session: the session with which to connect to the database.
    :arg namespace: the namespace to add.
    :arg user: The user performing the action.
    :returns: a message informing that the namespace was successfully
        created.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - You are not allowed to add a namespace, only pkgdb admin can.
            - An error occured while adding the namespace in the database
                the message returned is then the error message from the
                database.

    """

    if not pkgdb2.is_pkgdb_admin(user):
        raise PkgdbException('You are not allowed to add namespaces')

    ns = model.Namespace(namespace=namespace)
    try:
        session.add(ns)
        session.flush()
        pkgdb2.lib.utils.log(session, None, 'namespace.new', dict(
            agent=user.username,
            namespace=namespace,
        ))
        return 'Namespace "%s" created' % namespace
    except SQLAlchemyError, err:  # pragma: no cover
        pkgdb2.LOG.exception(err)
        session.rollback()
        raise PkgdbException(
            'Could not add Namespace "%s" to the database.' % namespace)


def drop_namespace(session, namespace, user):
    """ Remove a namespace from the database.

    This method only flushes the new object, nothing is committed to the
    database.

    :arg session: the session with which to connect to the database.
    :arg namespace: the namespace to remove.
    :arg user: The user performing the action.
    :returns: a message informing that the namespace was successfully
        removed.
    :rtype: str()
    :raises pkgdb2.lib.PkgdbException: There are few conditions leading to
        this exception beeing raised:
            - You are not allowed to remove a namespace, only pkgdb admin can.
            - The specified namespace could not be found in the DB.
            - An error occured while removing the namespace in the database
                the message returned is then the error message from the
                database.

    """

    if not pkgdb2.is_pkgdb_admin(user):
        raise PkgdbException('You are not allowed to remove namespaces')

    ns = model.Namespace.get(session, namespace)
    if not ns:
        raise PkgdbException(
            'Could not find namespace "%s" in the DB' % namespace)

    try:
        session.delete(ns)
        session.flush()
        pkgdb2.lib.utils.log(session, None, 'namespace.drop', dict(
            agent=user.username,
            namespace=namespace,
        ))
        return 'Namespace "%s" removed' % namespace
    except SQLAlchemyError, err:  # pragma: no cover
        pkgdb2.LOG.exception(err)
        session.rollback()
        raise PkgdbException(
            'Could not remove Namespace "%s" to the database.' % namespace)
