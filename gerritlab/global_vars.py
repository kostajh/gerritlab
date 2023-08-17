"""This file includes global variables."""

import os
import configparser
import requests

mr_url = None
pipeline_url = None
pipelines_url = None
headers = None
global_target_branch = "master"
remove_source_branch = False
username = None
email = None
ci_mode = False
session = None


def load_config(remote, repo):
    global username
    global email
    global mr_url
    global pipeline_url
    global pipelines_url
    global headers
    global global_target_branch
    global remove_source_branch
    global session

    username = repo.config_reader().get_value("user", "name")
    email = repo.config_reader().get_value("user", "email")

    config = configparser.ConfigParser()
    root_dir = repo.git.rev_parse("--show-toplevel")
    config.read(os.path.join(root_dir, ".gitreview"))
    configs = config[remote]
    host = configs["host"]
    project_id = configs["project_id"]
    if "GITLAB_PRIVATE_TOKEN" in os.environ:
        private_token = os.environ["GITLAB_PRIVATE_TOKEN"]
    elif "private_token" in configs:
        private_token = configs["private_token"]
    else:
        private_token = repo.config_reader().get_value("gerritlab", "private-token")
    # Optional configs.
    if "target_branch" in configs:
        global_target_branch = configs["target_branch"]
    if "remove_source_branch" in configs:
        remove_source_branch = configs.getboolean("remove_source_branch")
    mr_url = "{}/api/v4/projects/{}/merge_requests".format(host, project_id)
    pipeline_url = "{}/api/v4/projects/{}/pipeline".format(host, project_id)
    pipelines_url = "{}/api/v4/projects/{}/pipelines".format(host, project_id)
    session = requests.session()
    session.headers.update({"PRIVATE-TOKEN": private_token})
