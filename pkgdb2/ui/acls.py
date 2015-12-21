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
ACLs management for the Flask application.
'''

import flask
import itertools
from sqlalchemy.orm.exc import NoResultFound

import pkgdb2.forms
import pkgdb2.lib as pkgdblib
from pkgdb2 import (SESSION, APP, fas_login_required,
                    packager_login_required)
from pkgdb2.ui import UI


## Some of the object we use here have inherited methods which apparently
## pylint does not detect.
# pylint: disable=E1101


@UI.route('/acl/<namespace>/<package>/request/', methods=('GET', 'POST'))
@fas_login_required
def request_acl(namespace, package):
    ''' Request acls for a specific package. '''

    try:
        package_acl = pkgdblib.get_acl_package(
            SESSION, namespace, package)
        package = pkgdblib.search_package(
            SESSION, namespace, package, limit=1)[0]
    except (NoResultFound, IndexError):
        SESSION.rollback()
        flask.flash('No package of this name found.', 'errors')
        return flask.render_template('msg.html')

    collections = [
        acl.collection
        for acl in package_acl
        if acl.collection.status in ['Active', 'Under Development']
    ]

    pkg_acl = pkgdblib.get_status(SESSION, 'pkg_acl')['pkg_acl']

    form = pkgdb2.forms.RequestAclPackageForm(
        collections=collections,
        pkg_acl_list=pkg_acl
    )
    if form.validate_on_submit():
        pkg_branchs = form.branches.data
        pkg_acls = form.acl.data

        try:
            for (collec, acl) in itertools.product(pkg_branchs, pkg_acls):
                acl_status = 'Awaiting Review'
                if acl in APP.config['AUTO_APPROVE']:
                    acl_status = 'Approved'
                elif 'packager' not in flask.g.fas_user.groups:
                    flask.flash(
                        'You must be a packager to apply to the'
                        ' ACL: %s on %s' % (acl, collec), 'errors')
                    continue

                pkgdblib.set_acl_package(
                    SESSION,
                    namespace=namespace,
                    pkg_name=package.name,
                    pkg_branch=collec,
                    pkg_user=flask.g.fas_user.username,
                    acl=acl,
                    status=acl_status,
                    user=flask.g.fas_user,
                )
            SESSION.commit()
            flask.flash('ACLs updated')
            return flask.redirect(flask.url_for(
                '.package_info',
                namespace=package.namespace,
                package=package.name)
            )

        except pkgdblib.PkgdbException, err:
            SESSION.rollback()
            flask.flash(str(err), 'error')

    return flask.render_template(
        'acl_request.html',
        form=form,
        package=package.name,
        namespace=namespace,
    )


@UI.route('/acl/<namespace>/<package>/request/<acl>/', methods=['POST'])
@fas_login_required
def request_acl_all_branch(namespace, package, acl):
    ''' Request the specified ACL on all branches of the specified package.
    '''
    form = pkgdb2.forms.ConfirmationForm()

    if form.validate_on_submit():
        pkg_acl = pkgdblib.get_status(SESSION, 'pkg_acl')['pkg_acl']
        if acl not in pkg_acl:
            flask.flash('Invalid ACL provided %s.' % acl, 'errors')
            return flask.render_template('msg.html')

        try:
            pkg = pkgdblib.search_package(
                SESSION, namespace=namespace, pkg_name=package, limit=1)[0]
        except IndexError:
            flask.flash('No package found by this name', 'error')
            return flask.render_template('msg.html')

        pkg_branchs = set([
            pkglist.collection.branchname
            for pkglist in pkg.listings
            if pkglist.collection.status in ['Active', 'Under Development']
                and pkglist.status == 'Approved'
        ])

        for branch in pkg_branchs:
            acl_status = 'Awaiting Review'
            if acl in APP.config['AUTO_APPROVE']:
                acl_status = 'Approved'
            elif 'packager' not in flask.g.fas_user.groups:
                flask.flash(
                    'You must be a packager to apply to the ACL: %s on %s' % (
                        acl, package), 'error')

            try:
                pkgdblib.set_acl_package(
                    SESSION,
                    namespace=namespace,
                    pkg_name=package,
                    pkg_branch=branch,
                    pkg_user=flask.g.fas_user.username,
                    acl=acl,
                    status=acl_status,
                    user=flask.g.fas_user,
                )
                flask.flash(
                    'ACL %s requested on branch %s' % (acl, branch))
                SESSION.commit()
            except pkgdblib.PkgdbException, err:
                SESSION.rollback()
                flask.flash(str(err), 'error')

    return flask.redirect(flask.url_for(
        '.package_info', namespace=namespace, package=package))


@UI.route('/acl/<namespace>/<package>/giveup/<acl>/', methods=['POST'])
@fas_login_required
def giveup_acl(namespace, package, acl):
    ''' Request acls for a specific package. '''
    form = pkgdb2.forms.ConfirmationForm()

    if form.validate_on_submit():
        pkg_acl = pkgdblib.get_status(SESSION, 'pkg_acl')['pkg_acl']
        if acl not in pkg_acl:
            flask.flash('Invalid ACL provided %s.' % acl, 'errors')
            return flask.render_template('msg.html')

        try:
            pkg = pkgdblib.search_package(
                SESSION, namespace=namespace, pkg_name=package, limit=1)[0]
        except IndexError:
            flask.flash('No package found by this name', 'error')
            return flask.redirect(flask.url_for(
                '.package_info', namespace=namespace, package=package))

        pkg_branchs = set([
            pkglist.collection.branchname
            for pkglist in pkg.listings
            if pkglist.collection.status in
            ['Active', 'Under Development'] and flask.g.fas_user.username in
            [tmpacl.fas_name for tmpacl in pkglist.acls]
        ])

        if not pkg_branchs:
            flask.flash(
                'No active branches found for you for the ACL: %s' % acl,
                'error')
            return flask.redirect(flask.url_for(
                '.package_info', namespace=namespace, package=package))

        for branch in pkg_branchs:
            print package, namespace, branch, acl, flask.g.fas_user.username
            try:
                pkgdblib.set_acl_package(
                    SESSION,
                    namespace=namespace,
                    pkg_name=package,
                    pkg_branch=branch,
                    pkg_user=flask.g.fas_user.username,
                    acl=acl,
                    status='Obsolete',
                    user=flask.g.fas_user,
                )
                flask.flash(
                    'Your ACL %s is obsoleted on branch %s of package %s'
                    % (acl, branch, package))
            except pkgdblib.PkgdbException, err:  # pragma: no cover
                flask.flash(str(err), 'error')
                SESSION.rollback()

        try:
            SESSION.commit()
        # Keep it in, but normally we shouldn't hit this
        except pkgdblib.PkgdbException, err:  # pragma: no cover
            SESSION.rollback()
            flask.flash(str(err), 'error')

    return flask.redirect(flask.url_for(
        '.package_info', namespace=namespace, package=package))


@UI.route('/acl/<namespace>/<package>/give/', methods=('GET', 'POST'))
@fas_login_required
def package_give_acls(namespace, package):
    ''' Give acls to a specified user for a specific package. '''

    try:
        pkg = pkgdblib.search_package(
            SESSION, namespace=namespace, pkg_name=package, limit=1)[0]
    except IndexError:
        flask.flash('No package found by this name', 'error')
        return flask.redirect(
            flask.url_for('.list_packages'))

    collections = [
        pkglist.collection
        for pkglist in pkg.listings
        if pkglist.collection.status != 'EOL']

    acls = pkgdblib.get_status(SESSION)

    form = pkgdb2.forms.SetAclPackageForm(
        collections_obj=collections,
        pkg_acl=acls['pkg_acl'],
        acl_status=acls['acl_status'],
        namespaces=acls['namespaces'],
    )
    form.pkgname.data = package
    if str(form.namespace.data) in ['None', '']:
        form.namespace.data = 'rpms'

    if form.validate_on_submit():
        pkg_branchs = form.branches.data
        pkg_acls = form.acl.data
        pkg_user = form.user.data
        acl_status = form.acl_status.data

        try:
            for (collec, acl) in itertools.product(pkg_branchs, pkg_acls):
                if acl in APP.config['AUTO_APPROVE']:
                    acl_status = 'Approved'

                pkgdblib.set_acl_package(
                    SESSION,
                    namespace=namespace,
                    pkg_name=package,
                    pkg_branch=collec,
                    pkg_user=pkg_user,
                    acl=acl,
                    status=acl_status,
                    user=flask.g.fas_user,
                )
            SESSION.commit()
            flask.flash('ACLs updated')
            return flask.redirect(flask.url_for(
                '.package_info', namespace=namespace, package=package))
        except pkgdblib.PkgdbException, err:
            SESSION.rollback()
            flask.flash(str(err), 'error')

    return flask.render_template(
        'acl_give.html',
        form=form,
        package=package,
        namespace=namespace,
    )


@UI.route('/acl/<namespace>/<package>/watch/', methods=['POST'])
@fas_login_required
def watch_package(namespace, package):
    ''' Request watch* ACLs on a package.
    Anyone can request these ACLs, no need to be a packager.
    '''
    form = pkgdb2.forms.ConfirmationForm()

    if form.validate_on_submit():
        try:
            pkg = pkgdblib.search_package(
                SESSION, namespace=namespace, pkg_name=package, limit=1)[0]
        except IndexError:
            flask.flash('No package found by this name', 'error')
            return flask.redirect(flask.url_for(
                '.package_info', namespace=namespace, package=package))

        pkg_acls = ['watchcommits', 'watchbugzilla']
        pkg_branchs = set([
            pkglist.collection.branchname
            for pkglist in pkg.listings
            if pkglist.collection.status in ['Active', 'Under Development']
                and pkglist.status == 'Approved'
        ])
        try:
            for (collec, acl) in itertools.product(pkg_branchs, pkg_acls):
                pkgdblib.set_acl_package(
                    SESSION,
                    namespace=namespace,
                    pkg_name=package,
                    pkg_branch=collec,
                    pkg_user=flask.g.fas_user.username,
                    acl=acl,
                    status='Approved',
                    user=flask.g.fas_user,
                )
            SESSION.commit()
            flask.flash('ACLs updated')
        # Let's keep this in although we should never see it
        except pkgdblib.PkgdbException, err:  # pragma: no cover
            SESSION.rollback()
            flask.flash(str(err), 'error')
    return flask.redirect(flask.url_for(
        '.package_info', namespace=namespace, package=package))


@UI.route('/acl/<namespace>/<package>/unwatch/', methods=['POST'])
@fas_login_required
def unwatch_package(namespace, package):
    ''' Obsolete watch* ACLs on a package.
    This method can only be used for the user itself.
    '''
    form = pkgdb2.forms.ConfirmationForm()

    if form.validate_on_submit():
        try:
            pkg = pkgdblib.search_package(
                SESSION, namespace=namespace, pkg_name=package, limit=1)[0]
        except IndexError:
            flask.flash('No package found by this name', 'error')
            return flask.redirect(flask.url_for(
                '.package_info', namespace=namespace, package=package))

        pkg_acls = ['watchcommits', 'watchbugzilla']
        pkg_branchs = set([
            pkglist.collection.branchname
            for pkglist in pkg.listings
            if pkglist.collection.status in ['Active', 'Under Development']])
        try:
            for (collec, acl) in itertools.product(pkg_branchs, pkg_acls):
                pkgdblib.set_acl_package(
                    SESSION,
                    namespace=namespace,
                    pkg_name=package,
                    pkg_branch=collec,
                    pkg_user=flask.g.fas_user.username,
                    acl=acl,
                    status='Obsolete',
                    user=flask.g.fas_user,
                )
            SESSION.commit()
            flask.flash('ACLs updated')
        # Let's keep this in although we should never see it
        except pkgdblib.PkgdbException, err:  # pragma: no cover
            SESSION.rollback()
            flask.flash(str(err), 'error')
    return flask.redirect(flask.url_for(
        '.package_info', namespace=namespace, package=package))


@UI.route('/acl/<namespace>/<package>/comaintain/', methods=['POST'])
@packager_login_required
def comaintain_package(namespace, package):
    ''' Asks for ACLs to co-maintain a package.
    You need to be a packager to request co-maintainership.
    '''
    form = pkgdb2.forms.ConfirmationForm()

    if form.validate_on_submit():
        # This is really wearing belt and suspenders, the decorator above
        # should take care of this
        if 'packager' not in flask.g.fas_user.groups:  # pragma: no cover
            flask.flash(
                'You must be a packager to apply to be a comaintainer',
                'errors')
            return flask.redirect(flask.url_for(
                '.package_info', package=package))

        try:
            pkg = pkgdblib.search_package(
                SESSION, namespace=namespace, pkg_name=package, limit=1)[0]
        except IndexError:
            flask.flash('No package found by this name', 'error')
            return flask.redirect(flask.url_for(
                '.package_info', namespace=namespace, package=package))

        pkg_acls = ['commit', 'watchcommits', 'watchbugzilla']
        pkg_branchs = set([
            pkglist.collection.branchname
            for pkglist in pkg.listings
            if pkglist.collection.status in ['Active', 'Under Development']
                and pkglist.status == 'Approved'
        ])

        # Make sure the requester does not already have commit
        pkg_branchs2 = []
        for pkg_branch in pkg_branchs:
            if pkgdblib.has_acls(
                    SESSION, flask.g.fas_user.username, pkg.namespace,
                    pkg.name, acl='commit', branch=pkg_branch):
                flask.flash(
                    'You are already a co-maintainer on %s' % pkg_branch,
                    'error')
            else:
                pkg_branchs2.append(pkg_branch)
        pkg_branchs = pkg_branchs2

        if not pkg_branchs:
            return flask.redirect(flask.url_for(
                '.package_info', namespace=namespace, package=package))

        try:
            msgs = []
            for (collec, acl) in itertools.product(pkg_branchs, pkg_acls):
                acl_status = 'Awaiting Review'
                if acl in APP.config['AUTO_APPROVE']:
                    acl_status = 'Approved'
                msg = pkgdblib.set_acl_package(
                    SESSION,
                    namespace=namespace,
                    pkg_name=package,
                    pkg_branch=collec,
                    pkg_user=flask.g.fas_user.username,
                    acl=acl,
                    status=acl_status,
                    user=flask.g.fas_user,
                )
                if msg:
                    msgs.append(msg)

            SESSION.commit()
            if msgs:
                flask.flash('ACLs updated')
            else:
                flask.flash('Nothing to update')
        # Let's keep this in although we should never see it
        except pkgdblib.PkgdbException, err:  # pragma: no cover
            SESSION.rollback()
            flask.flash(str(err), 'error')
    return flask.redirect(flask.url_for(
        '.package_info', namespace=namespace, package=package))


@UI.route('/acl/<namespace>/<package>/dropcommit/', methods=['POST'])
@fas_login_required
def dropcommit_package(namespace, package):
    ''' Obsolete commit ACLs on a package.
    This method can only be used for the user itself.
    '''
    form = pkgdb2.forms.ConfirmationForm()

    if form.validate_on_submit():
        try:
            pkg = pkgdblib.search_package(
                SESSION, namespace=namespace, pkg_name=package, limit=1)[0]
        except IndexError:
            flask.flash('No package found by this name', 'error')
            return flask.redirect(flask.url_for(
                '.package_info', namespace=namespace, package=package))

        pkg_acls = ['commit']
        pkg_branchs = set()
        for pkglist in pkg.listings:
            if pkglist.collection.status in [
                    'Active', 'Under Development']:
                for acl in pkglist.acls:
                    if acl.fas_name == flask.g.fas_user.username and \
                            acl.acl == 'commit' and acl.status == 'Approved':
                        pkg_branchs.add(pkglist.collection.branchname)

        try:
            for (collec, acl) in itertools.product(pkg_branchs, pkg_acls):
                pkgdblib.set_acl_package(
                    SESSION,
                    namespace=namespace,
                    pkg_name=package,
                    pkg_branch=collec,
                    pkg_user=flask.g.fas_user.username,
                    acl=acl,
                    status='Obsolete',
                    user=flask.g.fas_user,
                )
            SESSION.commit()
            flask.flash('ACLs updated')
        # Let's keep this in although we should never see it
        except pkgdblib.PkgdbException, err:  # pragma: no cover
            SESSION.rollback()
            flask.flash(str(err), 'error')
    return flask.redirect(flask.url_for(
        '.package_info', namespace=namespace, package=package))


@UI.route('/acl/pending/')
@packager_login_required
def pending_acl():
    ''' List the pending acls for the user logged in. '''
    pending_acls = pkgdblib.get_pending_acl_user(
        SESSION, flask.g.fas_user.username)
    form = pkgdb2.forms.ConfirmationForm()
    return flask.render_template(
        'acl_pending.html',
        pending_acls=pending_acls,
        form=form,
    )


@UI.route('/acl/pending/approve', methods=['POST'])
@packager_login_required
def pending_acl_approve():
    ''' Approve all the pending acls for the user logged in. '''
    form = pkgdb2.forms.ConfirmationForm()

    if form.validate_on_submit():
        pending_acls = pkgdblib.get_pending_acl_user(
            SESSION, flask.g.fas_user.username)
        try:
            for acl in pending_acls:
                pkgdblib.set_acl_package(
                    SESSION,
                    namespace=acl['namespace'],
                    pkg_name=acl['package'],
                    pkg_branch=acl['collection'],
                    pkg_user=acl['user'],
                    acl=acl['acl'],
                    status='Approved',
                    user=flask.g.fas_user
                )

            SESSION.commit()
            flask.flash('All ACLs approved')
            # Let's keep this in although we should never see it
        except pkgdblib.PkgdbException, err:  # pragma: no cover
            SESSION.rollback()
            flask.flash(str(err), 'error')

    return flask.redirect(flask.url_for('.pending_acl'))


@UI.route('/acl/pending/deny', methods=['POST'])
@packager_login_required
def pending_acl_deny():
    ''' Deny all the pending acls for the user logged in. '''
    form = pkgdb2.forms.ConfirmationForm()

    if form.validate_on_submit():
        pending_acls = pkgdblib.get_pending_acl_user(
            SESSION, flask.g.fas_user.username)
        try:
            for acl in pending_acls:
                pkgdblib.set_acl_package(
                    SESSION,
                    namespace=acl['namespace'],
                    pkg_name=acl['package'],
                    pkg_branch=acl['collection'],
                    pkg_user=acl['user'],
                    acl=acl['acl'],
                    status='Denied',
                    user=flask.g.fas_user
                )

            SESSION.commit()
            flask.flash('All ACLs denied')
            # Let's keep this in although we should never see it
        except pkgdblib.PkgdbException, err:  # pragma: no cover
            SESSION.rollback()
            flask.flash(str(err), 'error')

    return flask.redirect(flask.url_for('.pending_acl'))
