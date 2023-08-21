import os
import click
import requests
import json
import yaml
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from paper_downloader import send_notification
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
# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# add formatter to console handler
fh.setFormatter(formatter)
# add console handler to logger
logger.addHandler(fh)

# root_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications"
# config_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/config"
# metadata_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/metadata"
# log_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/log"
# html_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/html"
# pdf_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/pdf"
# python_bin = "/data/prophetdb/prophetdb-studio/paper-downloader/.venv/bin/python"
# script = "/data/prophetdb/prophetdb-studio/paper-downloader/main.py"


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
            msg = f"{uniq_str}: 系统检测到在{metadata_dir}目录已有相同的Metadata文件{filename}, 请重命名配置文件后重试。"
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


class FileEventHandler(FileSystemEventHandler):
    def __init__(self, root_dir, token):
        self.root_dir = root_dir
        self.token = token
        FileSystemEventHandler.__init__(self)

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
        try:
            if event.is_directory:
                basename = os.path.basename(event.src_path)
                if os.path.join(self.root_dir, basename) == event.src_path:
                    logger.info("directory created:{0}".format(event.src_path))
                    send_notification("系统已创建新的项目: %s" % basename, self.token)
                    make_dirs(event.src_path)
            else:
                filename = os.path.basename(event.src_path)
                project_name = get_project_name(self.root_dir, event.src_path)

                pdf_dir = get_pdf_dir(self.root_dir, event.src_path)
                if (
                    not project_name.startswith(".")
                    and event.src_path.startswith(pdf_dir)
                    and not filename.startswith(".")
                ):
                    logger.info("file created:{0}".format(event.src_path))
                    make_dirs(os.path.join(self.root_dir, project_name))
                    handle_pdf_event(self.root_dir, event.src_path, self.token)

                config_dir = get_config_dir(self.root_dir, event.src_path)
                if (
                    not project_name.startswith(".")
                    and event.src_path.startswith(config_dir)
                    and not filename.startswith(".")
                ):
                    logger.info("file created:{0}".format(event.src_path))
                    make_dirs(os.path.join(self.root_dir, project_name))
                    handle_configfile_event(self.root_dir, event.src_path, self.token)
        except Exception as e:
            logger.error(e)

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


@click.command(help="Monitor the directory and handle the events")
@click.option("-d", "--root-dir", default=".", help="The directory to be monitored")
@click.option(
    "-t", "--token", default=".", help="The token to be used to send notification"
)
def cli(root_dir, token):
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


if __name__ == "__main__":
    logger.info("Prophet Server is starting...")
    cli()
