import os
import click
import requests
import json
import yaml
import signal
import subprocess
from watchdog.observers import Observer
from watchdog.events import *
import time
import tempfile
import hashlib
import logging


# log config
# create logger
logger = logging.getLogger("Notifier")
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
fh = logging.FileHandler("/var/log/notifier.log")
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
logger.addHandler(ch)

# root_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications"
# config_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/config"
# metadata_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/metadata"
# log_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/log"
# html_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/html"
# pdf_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/pdf"
# python_bin = "/data/prophetdb/prophetdb-studio/paper-downloader/.venv/bin/python"
# script = "/data/prophetdb/prophetdb-studio/paper-downloader/main.py"


def send_notification(msg, access_token=None):
    # Replace with your own DingTalk Bot webhook URL
    url = f"https://oapi.dingtalk.com/robot/send?access_token={access_token}"

    headers = {"Content-Type": "application/json;charset=utf-8"}

    data = {
        "msgtype": "text",
        "text": {"content": msg},
    }

    r = requests.post(url, headers=headers, data=json.dumps(data))
    logger.info(r.text)


def md5(string):
    m = hashlib.md5()
    m.update(string.encode("utf-8"))
    return m.hexdigest()


def get_bin(bin_name):
    cmd = f"which {bin_name}"
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    out, err = p.communicate()
    bin = out.decode("utf-8").strip()
    if bin:
        return bin
    else:
        raise Exception(
            f"Can't find {bin_name} in your system. Please install it first."
        )


def read_bib(bib_path):
    logpath = bib_path.replace(".bib", ".log")
    logpath = logpath.replace("config", "log")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_file = f.name
        bin = get_bin("pfetcher")
        cmd = f"{bin} bib2pd -o {temp_file} -b {bib_path} -l {logpath}"

        subprocess.call(cmd, shell=True)

        if os.path.exists(temp_file):
            with open(temp_file, "r") as f:
                data = json.load(f)
                return data
        else:
            return None


def get_project_name(root_dir, filepath):
    dir = filepath.replace(root_dir, "")
    project_name = list(filter(lambda x: x, dir.split("/")))[0]
    return project_name


def get_config_dir(root_dir, filepath):
    return os.path.join(root_dir, get_project_name(root_dir, filepath), "config")


def get_metadata_dir(root_dir, filepath):
    return os.path.join(root_dir, get_project_name(root_dir, filepath), "metadata")


def get_html_dir(root_dir, filepath):
    return os.path.join(root_dir, get_project_name(root_dir, filepath), "html")


def get_pdf_dir(root_dir, filepath):
    return os.path.join(root_dir, get_project_name(root_dir, filepath), "pdf")


def handle_configfile_event(root_dir, filepath, access_token):
    uniq_str = get_project_name(root_dir, filepath)
    # If you change the directory structure, you need to change the parent_dir
    logger.info("Find a new config file: %s" % filepath)

    config_dir = get_config_dir(root_dir, filepath)
    if os.path.isfile(filepath) and filepath.startswith(config_dir):
        filename = os.path.basename(filepath)
        metadata_dir = get_metadata_dir(root_dir, filepath)
        dest_file = ""
        logpath = (
            filepath.replace(".json", ".log")
            .replace(".yaml", ".log")
            .replace(".bib", ".log")
            .replace("config", "log")
        )

        if not os.path.exists(os.path.join(config_dir, filename)):
            msg = f"{uniq_str}: 收到新的检索式，但文件不存在或未直接将文件放置在config目录下。"
            send_notification(msg, access_token)
            return

        try:
            msg = f"{uniq_str}: 收到新的检索式，但是文件格式不正确。请检查文件格式是否为bib, json或yaml。"
            data = None
            with open(os.path.abspath(filepath), "r") as f:
                if filepath.endswith(".json"):
                    data = json.load(f)
                    dest_file = os.path.join(
                        metadata_dir, filename.replace(".json", ".json")
                    )
                    msg = f"{uniq_str}: 收到新的检索式，正在处理。"
                elif filepath.endswith("yaml"):
                    data = yaml.load(f, Loader=yaml.FullLoader)
                    dest_file = os.path.join(
                        metadata_dir, filename.replace(".yaml", ".json")
                    )
                    msg = f"{uniq_str}: 收到新的检索式，正在处理。"
                elif filepath.endswith("bib"):
                    data = read_bib(filepath)
                    dest_file = os.path.join(
                        metadata_dir, filename.replace(".bib", ".json")
                    )
                    msg = f"{uniq_str}: 收到新的检索式，正在处理。"

            send_notification(msg, access_token)
            if filepath.endswith(".log"):
                return None

            if data is None:
                send_notification(
                    f"{uniq_str}: 文件格式不正确。请检查文件格式是否为bib, json或yaml。", access_token
                )
                return None
        except Exception as e:
            logger.error(e)
            send_notification(
                f"{uniq_str}: 收到新的检索式，但是文件格式不正确。请检查文件格式是否为bib, json或yaml。", access_token
            )
            return None

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_file = f.name
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=4)
                filepath = temp_file

        download_pdf = data.get("download_pdf")

        bin = get_bin("pfetcher")
        cmd = f"{bin} fetch-metadata -d 3 -o {dest_file} -c {filepath} -l {logpath} -t {access_token}"

        if os.path.exists(dest_file):
            msg = f"{uniq_str}: 系统检测到在metadata目录已有同名的Metadata文件, 请重命名配置文件后重试。"
            send_notification(msg, access_token)
            return None

        try:
            send_notification(f"{uniq_str}: 解析配置文件成功", access_token)
            subprocess.call(cmd, shell=True)
            if download_pdf:
                msg = f"{uniq_str}: 系统已获取到新的文献元数据。正在下载文献PDF，请稍后。"
                send_notification(msg, access_token)
                download_pdfs(root_dir, dest_file, access_token)

            msg = f"{uniq_str}: 系统已处理完毕新的检索式。请前往publications.3steps.cn下载Metadata，并导入至Prophet Studio。"

            send_notification(msg, access_token)
        except Exception as e:
            msg = f"{uniq_str}: 系统处理时出现了错误。请管理员前往Prophet Server查看错误信息。以下是错误信息：\n{e}"
            send_notification(msg, access_token)

    else:
        logger.error("The file is not an expected config json file")


def download_pdfs(root_dir, metadata_json_file, access_token):
    if not os.path.isfile(metadata_json_file):
        logger.error("The metadata file is not an expected json file")
        return None

    project_name = get_project_name(root_dir, metadata_json_file)
    filename = os.path.basename(metadata_json_file)
    logpath = os.path.join(
        root_dir, project_name, "log", filename.replace(".json", ".log")
    )
    pdf_dir = get_pdf_dir(root_dir, metadata_json_file)
    bin = get_bin("pfetcher")
    cmd = f"{bin} fetch-pdf -o {pdf_dir} -m {metadata_json_file} -l {logpath}"
    try:
        subprocess.call(cmd, shell=True)
        msg = f"{project_name}: 系统已下载完所有文献PDF。请前往Prophet Studio查看。"
        send_notification(msg, access_token)
    except Exception as e:
        msg = f"{project_name}: 系统处理时出现了错误。请管理员前往Prophet Server查看错误信息。以下是错误信息：\n{e}"
        logger.error(msg)
        send_notification(msg, access_token)


# Define a function to handle events
def handle_pdf_event(root_dir, filepath, access_token):
    uniq_str = get_project_name(root_dir, filepath)
    # If you change the directory structure, you need to change the parent_dir
    logger.info("Find a new file: %s" % filepath)
    logpath = os.path.join(
        root_dir, uniq_str, "log", os.path.basename(filepath).replace(".pdf", ".log")
    )
    pdf_dir = get_pdf_dir(root_dir, filepath)
    if (
        os.path.isfile(filepath)
        and filepath.endswith(".pdf")
        and filepath.startswith(pdf_dir)
    ):
        msg = f"{uniq_str}: 系统已获取到新的文献PDF。正在转换为HTML，请稍后。"
        send_notification(msg, access_token)

        bin = get_bin("pfetcher")
        html_dir = get_html_dir(root_dir, filepath)
        cmd = f"{bin} pdf2html -p {pdf_dir} -h {html_dir} -l {logpath}"
        subprocess.call(cmd, shell=True)
        if os.path.exists(
            os.path.join(html_dir, os.path.basename(filepath).replace(".pdf", ".html"))
        ):
            msg = f"{uniq_str}: 系统已将所有文献PDF转换为HTML。请前往Prophet Studio查看。"
            send_notification(msg, access_token)
    else:
        logger.info("The file is not a expected pdf file")


def make_dirs(dir):
    if not os.path.exists(dir):
        raise Exception(f"Directory {dir} does not exist")

    for subdir in ["pdf", "html", "metadata", "config", "log"]:
        subdir = os.path.join(dir, subdir)
        if not os.path.exists(subdir):
            os.makedirs(subdir)
            if not os.path.exists(os.path.join(subdir, ".gitkeep")):
                with open(os.path.join(subdir, ".gitkeep"), "w") as f:
                    f.write("")


def handle_create_event(root_dir, src_path, access_token):
    try:
        if os.path.isdir(src_path):
            basename = os.path.basename(src_path)
            if os.path.join(root_dir, basename) == src_path:
                logger.info("directory created:{0}".format(src_path))
                send_notification("系统已创建新的项目: %s" % basename, access_token)
                make_dirs(src_path)
        else:
            filename = os.path.basename(src_path)
            project_name = get_project_name(root_dir, src_path)
            pdf_dir = get_pdf_dir(root_dir, src_path)
            config_dir = get_config_dir(root_dir, src_path)

            logger.info(
                "file created: {0}, {1}, {2}, {3}".format(
                    src_path, project_name, pdf_dir, config_dir
                )
            )
            if (
                not project_name.startswith(".")
                and src_path.startswith(pdf_dir)
                and not filename.startswith(".")
            ):
                make_dirs(os.path.join(root_dir, project_name))
                handle_pdf_event(root_dir, src_path, access_token)

            if (
                not project_name.startswith(".")
                and src_path.startswith(config_dir)
                and not filename.startswith(".")
            ):
                make_dirs(os.path.join(root_dir, project_name))
                handle_configfile_event(root_dir, src_path, access_token)
    except Exception as e:
        logger.error(e)


class FileEventHandler(RegexMatchingEventHandler):
    def __init__(self, root_dir, token):
        self.root_dir = root_dir
        self.token = token
        super(FileEventHandler, self).__init__(
            regexes=[r".*\.json", r".*\.pdf", r".*\.bib", r".*\.yaml", r".*\.yml"],
            ignore_directories=True,
            ignore_regexes=[r".*\.gitkeep", r".*\.minio.sys.*"],
        )

    # def on_moved(self, event):
    #     if event.is_directory:
    #         logger.info(
    #             "directory moved from {0} to {1}".format(
    #                 event.src_path, event.dest_path
    #             )
    #         )
    #     else:
    #         logger.info(
    #             "file moved from {0} to {1}".format(event.src_path, event.dest_path)
    #         )

    def on_created(self, event):
        print("on_created: {0}, {1}".format(event.src_path, event.is_directory))
        if ".minio.sys" in event.src_path:
            return

        handle_create_event(self.root_dir, event.src_path, self.token)

    # def on_deleted(self, event):
    #     if event.is_directory:
    #         logger.info("directory deleted:{0}".format(event.src_path))
    #     else:
    #         logger.info("file deleted:{0}".format(event.src_path))

    # def on_modified(self, event):
    #     if event.is_directory:
    #         logger.info("directory modified:{0}".format(event.src_path))
    #     else:
    #         logger.info("file modified:{0}".format(event.src_path))


cli = click.Group()


@cli.command(help="Monitor the directory and handle the events")
@click.option("-d", "--root-dir", default=".", help="The directory to be monitored")
@click.option(
    "-t", "--token", default=".", help="The token to be used to send notification"
)
def watchdog(root_dir, token):
    observer = Observer()
    root_dir = root_dir.rstrip("/")
    event_handler = FileEventHandler(root_dir, token)
    observer.schedule(event_handler, root_dir, True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def get_event_handler(root_dir, access_token):
    def process_minio_event(event):
        """Process minio event

        Args:
            event (dict): minio event

        Returns:
            None

        event = {
            "Records": [
                {
                    "eventName": "s3:ObjectCreated:Put",
                    ...
                    "s3": {
                        "bucket": {
                            "name": "test",
                            ...
                        },
                        "object": {
                            "key": "test/test.pdf",
                            ...
                        }
                    }
                }
            ]
        }
        """
        filtered_events = []
        for record in event.get("Records", []):
            event_name = record.get("eventName", '')

            if event_name.startswith("s3:ObjectCreated"):
                bucket_name = record.get("s3", {}).get("bucket", {}).get("name", "")
                object_key = record.get("s3", {}).get("object", {}).get("key", "")
                filtered_events.append({
                    "bucket_name": bucket_name,
                    "object_key": object_key,
                    "event_type": event_name,
                })

        logger.info("Find {0} events".format(len(filtered_events)))
        for event in filtered_events:
            bucket_name, object_name, event_type = (
                event["bucket_name"],
                event["object_key"],
                event["event_type"],
            )

            logger.info("file created: {0}, {1}, {2}".format(bucket_name, object_name, event_type))
            src_path = os.path.join(root_dir, bucket_name, object_name)
            handle_create_event(root_dir, src_path, access_token)

    return process_minio_event


@cli.command(help="Monitor the directory and handle the events from minio.")
@click.option("-u", "--access-key", help="The access key of minio", required=True)
@click.option("-p", "--secret-key", help="The secret key of minio", required=True)
@click.option(
    "-s",
    "--server",
    help="The server of minio",
    required=False,
    default="127.0.0.1:9000",
)
@click.option(
    "-S", "--secure", help="Whether to use https", required=False, default=False
)
@click.option(
    "-t",
    "--access-token",
    help="The access token to be used to send notification",
    required=True,
)
@click.option(
    "-d",
    "--root-dir",
    help="The root directory to be monitored",
    required=False,
    default=".",
)
def minio(access_key, secret_key, server, secure, access_token, root_dir="."):
    from minio import Minio
    import threading

    minio_client = Minio(
        server, access_key=access_key, secret_key=secret_key, secure=secure
    )

    # Get all buckets.
    buckets = minio_client.list_buckets()
    logger.info("buckets: {0}".format(buckets))

    def listen_to_bucket(minio_client, bucket_name, root_dir, access_token):
        logger.info("listen to bucket: {0}".format(bucket_name))
        try:
            events = minio_client.listen_bucket_notification(bucket_name)
            for event in events:
                logger.debug("Get event: {0}".format(event))
                get_event_handler(root_dir, access_token)(event)
        except Exception as err:
            logger.error("Error: %s" % err)

    # Listen multiple buckets.
    threads = []
    for bucket in buckets:
        thread = threading.Thread(
            target=listen_to_bucket,
            args=(minio_client, bucket.name, root_dir, access_token),
        )
        threads.append(thread)
        thread.start()

    # Response to a killing signal.
    def signal_handler(sig, frame):
        for thread in threads:
            thread.stop()

    signal.signal(signal.SIGINT, signal_handler)

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    logger.info("Prophet Server is starting...")
    cli()
