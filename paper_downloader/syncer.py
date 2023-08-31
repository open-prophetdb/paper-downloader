import os
import hashlib
import requests
import click
import tempfile
import logging
import subprocess
import json
import threading, time, signal
from datetime import timedelta

logger = logging.getLogger("paper_downloader.syncer")
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


MINIO_ALIAS = "publications"


class ProgramKilled(Exception):
    pass


def make_config_file(minio_server, access_key, secret_key):
    # Construct the command to make the config file
    command = [
        "mc",
        "config",
        "host",
        "add",
        MINIO_ALIAS,
        minio_server,
        access_key,
        secret_key,
    ]

    try:
        # Run the command and parse JSON output
        subprocess.check_output(command, universal_newlines=True)
        return True
    except subprocess.CalledProcessError:
        return False


def get_registered_users():
    """Get registered users from Minio

    [
        {
            "status": "success",
            "accessKey": "YuchenYe",
            "policyName": "mecfs_longcovid",
            "userStatus": "enabled"
        }
    ]
    """
    # Construct the command to list users
    command = [
        "mc",
        "admin",
        "user",
        "list",
        MINIO_ALIAS,
        "--json",
    ]

    try:
        # Run the command and parse JSON output
        output = subprocess.check_output(command, universal_newlines=True)
        if output == "":
            return []

        outputs = filter(lambda x: x != "", output.split("\n"))
        users = [json.loads(output) for output in outputs]
        return users
    except subprocess.CalledProcessError as e:
        logger.error("Something wrong with the group: %s" % e)
        return []


def register_user(email, minio_token):
    """Register a user in Minio

    Args:
        email (str): Email of the user
        minio_token (str): Token to use for syncing
    """
    # Construct the command to register a user
    command = ["mc", "admin", "user", "add", MINIO_ALIAS, email, minio_token]

    try:
        # Run the command and parse JSON output
        subprocess.check_output(command, universal_newlines=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Something wrong with the group: %s" % e)
        return False
    

def update_user(email, minio_token):
    """Update a user in Minio

    Args:
        email (str): Email of the user
        minio_token (str): Token to use for syncing
    """
    # Construct the command to update a user
    command = ["mc", "admin", "user", "update", MINIO_ALIAS, email, minio_token]

    try:
        # Run the command and parse JSON output
        subprocess.check_output(command, universal_newlines=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Something wrong with the group: %s" % e)
        return False


def register_policy(bucket_name):
    """Register a policy in Minio

    Args:
        bucket_name (str): Name of the bucket
    """
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:*"],
                "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
            }
        ],
    }

    # Save policy to a temp file
    with tempfile.NamedTemporaryFile(mode="w") as f:
        json.dump(policy, f)
        f.flush()

        # Construct the command to register a policy
        command = [
            "mc",
            "admin",
            "policy",
            "attach",
            MINIO_ALIAS,
            bucket_name,
            f"{f.name}",
        ]

        try:
            # Run the command and parse JSON output
            subprocess.check_output(command, universal_newlines=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Something wrong with the group: %s" % e)
            return False
        

def bind_policy_with_group(bucket_name):
    """Bind a policy with a group in Minio

    Args:
        bucket_name (str): Name of the bucket
    """
    # Construct the command to bind a policy with a group
    command = [
        "mc",
        "admin",
        "policy",
        "set",
        MINIO_ALIAS,
        bucket_name,
        f"group={bucket_name}",
    ]

    try:
        # Run the command and parse JSON output
        subprocess.check_output(command, universal_newlines=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Something wrong with the group: %s" % e)
        return False
        

def make_bucket(bucket_name):
    """Make a bucket in Minio

    Args:
        bucket_name (str): Name of the bucket
    """
    # Construct the command to make a bucket
    command = [
        "mc",
        "mb",
        "-p",
        f"{MINIO_ALIAS}/{bucket_name}",
    ]

    try:
        # Run the command and parse JSON output
        subprocess.check_output(command, universal_newlines=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Something wrong with the group: %s" % e)
        return False
        

def add_users_into_group(bucket_name, users):
    """Register a group in Minio

    Args:
        bucket_name (str): Name of the bucket
    """
    # Construct the command to register a group
    command = [
        "mc",
        "admin",
        "group",
        "add",
        MINIO_ALIAS,
        bucket_name,
        *users,
    ]

    try:
        # Run the command and parse JSON output
        subprocess.check_output(command, universal_newlines=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Something wrong with the group: %s" % e)
        return False


def exists_user(email, registered_users):
    """Check if a user exists in Minio

    Args:
        email (str): Email of the user
        registered_users (list): List of registered users

    Returns:
        bool: True if user exists, False otherwise
    """
    for user in registered_users:
        if user["accessKey"] == email:
            return True
    return False


def get_organizations(ls_server, token):
    """Get organizations from Label Studio

    Args:
        ls_server (str): Label Studio server URL
        token (str): Token to use for syncing

    Returns:
        list: List of organizations

    Examples:
        [
            {
                "id": 1,
                "title": "Label Studio",
                "created_by": 1
            }
        ]
    """
    url = f"{ls_server}/api/organizations"
    try:
        response = requests.get(url, headers={"Authorization": f"Token {token}"})
        response.raise_for_status()
        organizations = response.json()
        return organizations
    except Exception as e:
        logger.error(f"Error getting organizations: {e}")
        return []


def get_users_by_organization(ls_server, token, organization_id):
    """Get users from Label Studio

    Args:
        ls_server (str): Label Studio server URL
        token (str): Token to use for syncing

    Returns:
        list: List of users

    Examples:
        {
            "count": 13,
            "next": null,
            "previous": null,
            "results": [
                {
                    "id": 1,
                    "organization": 1,
                    "user": {
                        "id": 1,
                        "first_name": "",
                        "last_name": "",
                        "username": "",
                        "email": "clinico-omics@prophetdb.org",
                        "last_activity": "2023-08-30T02:03:37.302039Z",
                        "avatar": null,
                        "initials": "cl",
                        "phone": "",
                        "active_organization": 1,
                        "allow_newsletters": null,
                        "is_superuser": true,
                        "created_projects": null,
                        "contributed_to_projects": null
                    }
                },
            ]
        }
    """
    url = f"{ls_server}/api/organizations/{organization_id}/memberships"
    try:
        response = requests.get(url, headers={"Authorization": f"Token {token}"})
        response.raise_for_status()
        results = response.json().get("results", [])
        return [result["user"] for result in results]
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        return []
    

def remove_policy(bucket_name):
    """Remove a policy in Minio

    Args:
        bucket_name (str): Name of the bucket
    """
    # Construct the command to remove a policy
    command = [
        "mc",
        "admin",
        "policy",
        "remove",
        MINIO_ALIAS,
        bucket_name,
    ]

    try:
        # Run the command and parse JSON output
        subprocess.check_output(command, universal_newlines=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Something wrong with the group: %s" % e)
        return False
    

def get_users_in_group(bucket_name):
    """Get users in a group in Minio

    Args:
        bucket_name (str): Name of the bucket

    Returns:
        list: List of users
    """
    # Construct the command to get users in a group
    # mc admin group info publications label-studio --json
    command = [
        "mc",
        "admin",
        "group",
        "info",
        MINIO_ALIAS,
        bucket_name,
        "--json",
    ]

    # {
    #     "status": "success",
    #     "groupName": "label-studio",
    #     "members": [
    #         "1321459126@qq.com",
    #         "1456259568@qq.com",
    #         "1635231996@qq.com",
    #         "1814284435@qq.com",
    #         "1826840740@qq.com",
    #         "1826840749@qq.com",
    #         "chengtianyuan0606@outlook.com",
    #         "laf19990321@126.com",
    #         "qingqingzish@163.com",
    #         "ranzh@sumhs.edu.cn",
    #         "yjcyxky@163.com",
    #         "zhuzhixing@shchildren.com.cn"
    #     ],
    #     "groupStatus": "enabled"
    # }

    try:
        # Run the command and parse JSON output
        output = subprocess.check_output(command, universal_newlines=True)
        if output == "":
            return []

        users = json.loads(output).get("members", [])
        return users
    except subprocess.CalledProcessError as e:
        logger.error("Something wrong with the group: %s" % e)
        return []

def remove_group(bucket_name):
    """Remove a group in Minio

    Args:
        bucket_name (str): Name of the bucket
    """
    all_users_in_group = get_users_in_group(bucket_name)

    # Construct the command to remove a group
    command = [
        "mc",
        "admin",
        "group",
        "remove",
        MINIO_ALIAS,
        bucket_name,
        *all_users_in_group,
    ]

    try:
        # Run the command and parse JSON output
        subprocess.check_output(command, universal_newlines=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Something wrong with the group: %s" % e)
        return False
    

def remove_special_characters(string):
    """Remove special characters from a string

    Args:
        string (str): String to remove special characters from

    Returns:
        str: String without special characters
    """
    return "".join([e if e.isalnum() else "_" for e in string])



def sync_account(ls_server, token):
    print(time.ctime())
    logger.info("Syncing account")

    logger.info("Get all registered users from Minio")
    registered_users = get_registered_users()
    logger.info(f"Found {len(registered_users)} registered users")

    logger.info("Get all organizations from Label Studio")
    organizations = get_organizations(ls_server, token)
    logger.info(f"Found {len(organizations)} organizations")

    if len(organizations) == 0:
        logger.error("No organizations found")
        return

    # Let all users in an organization be in the same group and bucket
    for organization in organizations:
        logger.info(f"Get all users from organization {organization['title']}")
        users = get_users_by_organization(ls_server, token, organization["id"])
        bucket_name = organization["title"].lower().replace(" ", "-")

        logger.info(f"Syncing organization {bucket_name}")

        logger.info(f"Creating bucket {bucket_name}")
        make_bucket(bucket_name)

        logger.info(f"Removing group {bucket_name}")
        remove_group(bucket_name)

        logger.info(f"Removing policy for bucket {bucket_name}")
        remove_policy(bucket_name)

        successed_users = []
        for user in users:
            if user["is_superuser"]:
                continue

            userid = user["id"]
            email = user["email"]
            minio_token = hashlib.md5(f"{email}:{userid}".encode()).hexdigest()

            # Check if user is already registered
            if exists_user(email, registered_users):
                logger.info(f"User {email} already registered, if the user cannot login with the secret key, please remove the user from Minio and let the syncer re-register the user")
                successed_users.append(email)
                continue
            else:
                logger.info(f"Registering user {email}")
                if register_user(email, minio_token):
                    successed_users.append(email)

        if len(successed_users) == 0:
            logger.info("No users registered")
            continue

        logger.info(f"Adding users into group {bucket_name}")
        add_users_into_group(bucket_name, successed_users)

        logger.info(f"Registering policy for bucket {bucket_name}")
        register_policy(bucket_name)

        logger.info(f"Binding policy with group {bucket_name}")
        bind_policy_with_group(bucket_name)


def signal_handler(signum, frame):
    raise ProgramKilled


class Job(threading.Thread):
    def __init__(self, interval, execute, *args, **kwargs):
        threading.Thread.__init__(self)
        self.daemon = False
        self.stopped = threading.Event()
        self.interval = interval
        self.execute = execute
        self.args = args
        self.kwargs = kwargs

    def stop(self):
        self.stopped.set()
        self.join()

    def run(self):
        while not self.stopped.wait(self.interval.total_seconds()):
            self.execute(*self.args, **self.kwargs)


@click.command(help="Syncs the account every N minutes")
@click.option("--minutes", default=5, help="Minutes between each sync", type=float)
@click.option(
    "--ls-server", default="http://localhost:8080", help="Label Studio server URL"
)
@click.option("--token", default=None, help="Token to use for syncing")
@click.option(
    "--minio-server", default="http://localhost:9000", help="Minio server URL"
)
@click.option("--access-key", default=None, help="Minio access key")
@click.option("--secret-key", default=None, help="Minio secret key")
def cli(minutes, token, ls_server, minio_server, access_key, secret_key):
    if token is None:
        #  Get token from the environment variable
        token = os.environ.get("LABEL_STUDIO_ADMIN_TOKEN")

    if minio_server is None:
        #  Get minio server from the environment variable
        minio_server = os.environ.get("MINIO_SERVER")

    if access_key is None:
        #  Get access key from the environment variable
        access_key = os.environ.get("MINIO_ACCESS_KEY")

    if secret_key is None:
        #  Get secret key from the environment variable
        secret_key = os.environ.get("MINIO_SECRET_KEY")

    logger.info("Starting syncer")
    logger.info("Set up Minio config file")
    make_config_file(minio_server, access_key, secret_key)

    WAIT_TIME_SECONDS = minutes * 60
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    job = Job(
        interval=timedelta(seconds=WAIT_TIME_SECONDS),
        execute=sync_account,
        token=token,
        ls_server=ls_server,
    )
    job.start()

    while True:
        try:
            time.sleep(1)
        except ProgramKilled:
            logger.info("Program killed: running cleanup code")
            job.stop()
            break

if __name__ == "__main__":
    cli()