"""This file includes easy APIs to handle GitLab merge requests."""

import sys
from typing import Optional
import time

import requests
import git

from gerritlab import global_vars, utils


class MergeRequest:
    _remote: git.Remote
    _source_branch: str
    _target_branch: Optional[str]
    _title: Optional[str]
    _description: Optional[str]
    _iid: Optional[str]
    _web_url: Optional[str]
    _mergeable: bool
    _local_branch: str
    _needs_save: bool

    def __init__(
        self,
        remote,
        source_branch=None,
        target_branch=None,
        title=None,
        description=None,
        json_data=None,
    ):
        self._remote = remote
        self._source_branch = source_branch
        self._target_branch = target_branch
        self._title = title
        self._description = description
        self._iid = None
        self._web_url = None
        self._mergeable = False
        self._needs_save = False

        self._set_data(json_data)

    def _set_data(self, json_data):
        if json_data is not None:
            for attr in json_data:
                setattr(self, "_{}".format(attr), json_data[attr])

        self._local_branch = self._source_branch.rsplit("-", 1)[0]

    @property
    def mergeable(self):
        return self._mergeable

    @property
    def source_branch(self):
        return self._source_branch

    @property
    def target_branch(self):
        return self._target_branch

    def print_info(self, verbose=False):
        print("* {} {}".format(self._web_url, self._title))
        if verbose:
            print(
                "    {} -> {}".format(self._source_branch, self._target_branch)
            )

    def create(self):
        data = {
            "source_branch": self._source_branch,
            "target_branch": self._target_branch,
            "title": self._title,
            "description": self._description,
            "remove_source_branch": global_vars.remove_source_branch,
        }
        try:
            r = global_vars.session.post(global_vars.mr_url, data=data)
            data = r.json()
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise SystemExit(
                "Error creating merge request for "
                "{} → {}\n{}\n{}".format(
                    self._source_branch, self._target_branch, e, data
                )
            )
        self._iid = data["iid"]
        self._web_url = data["web_url"]

    def update(
        self,
        source_branch=None,
        target_branch=None,
        title=None,
        description=None,
    ):
        if source_branch is not None:
            self._source_branch = source_branch
        if target_branch is not None:
            self._target_branch = target_branch
        if title is not None:
            self._title = title
        if description is not None:
            self._description = description
        data = {
            "source_branch": self._source_branch,
            "target_branch": self._target_branch,
            "title": self._title,
            "description": self._description,
        }
        r = global_vars.session.put(
            "{}/{}".format(global_vars.mr_url, self._iid), data=data
        )
        r.raise_for_status()
        data = r.json()
        self._iid = data["iid"]
        self._web_url = data["web_url"]

    def rebase(self):
        """Rebases source_branch of the MR against its target_branch."""
        r = global_vars.session.put(
            "{}/{}/rebase".format(global_vars.mr_url, self._iid)
        )
        r.raise_for_status()

    def merge(self):
        if self._iid is None:
            raise ValueError("Must set iid before merging an MR!")
        url = "{}/{}/merge".format(global_vars.mr_url, self._iid)
        while True:
            r = global_vars.session.put(url)
            if r.status_code == requests.codes.ok:
                break
            else:
                time.sleep(2)

    def delete(self, delete_source_branch=False):
        if self._iid is None:
            raise ValueError("Must set iid before deleting an MR!")
        r = global_vars.session.delete(
            "{}/{}".format(global_vars.mr_url, self._iid)
        )
        r.raise_for_status()
        if delete_source_branch:
            self._remote.push(refspec=(":{}".format(self._source_branch)))

    def get_commits(self):
        """Returns a list of commits in this merge request."""
        r = global_vars.session.get(
            "{}/{}/commits".format(global_vars.mr_url, self._iid)
        )
        r.raise_for_status()
        return r.json()

    def needs_update(self, commit) -> bool:
        title, desc = utils.get_msg_title_description(commit.commit.message)
        return (
            self._source_branch != commit.source_branch
            or self._target_branch != commit.target_branch
            or self._title != title
            or self._description != desc.strip()
        )

    def refresh(self):
        """
        Update's this object's data using the latest info available from the
        server.
        """
        r = global_vars.session.get(
            "{}/{}".format(global_vars.mr_url, self._iid)
        )
        r.raise_for_status()
        self._set_data(r.json())

    def wait_until_stable(self, commit):
        """
        Poll the MR until the "sha" field matches that of `commit`.
        """
        while True:
            self.refresh()
            if self._sha == commit.commit.hexsha:
                return
            time.sleep(0.500)

    def set_target_branch(self, target_branch):
        if self._target_branch != target_branch:
            self._target_branch = target_branch
            self._needs_save = True

    def set_title(self, title):
        if self._title != title:
            self._title = title
            self._needs_save = True

    def set_desc(self, desc):
        if self._description.strip() != desc.strip():
            self._description = desc
            self._needs_save = True

    def save(self) -> bool:
        saved = False

        if self._needs_save:
            self.update()
            saved = True

        self._needs_save = False
        return saved


def _get_open_merge_requests():
    """Gets all open merge requests in the GitLab repo."""
    page = 1
    per_page = 50
    results = []
    while True:
        try:
            next_page = global_vars.session.get(
                "{}?state=opened&page={}&per_page={}&"
                "scope=created_by_me".format(global_vars.mr_url, page, per_page)
            )
            next_page.raise_for_status()
        except (
            requests.exceptions.HTTPError,
            requests.exceptions.InvalidHeader,
        ) as e:
            print("Error gathering merge requests, message: {}".format(e))
            sys.exit(1)

        if not next_page.json():
            break

        results.append(next_page)
        page += 1
    return results


def get_merge_request(remote, branch):
    """Return a `MergeRequest` given branch name."""
    for r in _get_open_merge_requests():
        for mr in r.json():
            if mr["source_branch"] == branch:
                return MergeRequest(remote=remote, json_data=mr)
    return None


def get_all_merge_requests(remote, branch):
    """Return all `MergeRequest`s created off of `branch`."""
    mrs = []
    for r in _get_open_merge_requests():
        for json_data in r.json():
            if json_data["source_branch"].startswith(branch):
                mrs.append(MergeRequest(remote=remote, json_data=json_data))
    return mrs


def get_merge_request_chain(mrs):
    """Returns the MR dependency chain."""
    if len(mrs) == 0:
        return []
    source_branches = set([mr.source_branch for mr in mrs])
    roots = []
    for mr in mrs:
        if mr.target_branch not in source_branches:
            roots.append(mr)
    mrs_dict = {mr.target_branch: mr for mr in mrs}

    def get_merge_request_chain_inner(mrs, root):
        mr_chain = [root]
        if root.source_branch not in mrs:
            return mr_chain
        else:
            next_mr = mrs[root.source_branch]
            mr_chain.extend(get_merge_request_chain_inner(mrs, next_mr))
            return mr_chain

    mr_chain = []
    for root in roots:
        mr_chain.extend(get_merge_request_chain_inner(mrs_dict, root))
    return mr_chain
