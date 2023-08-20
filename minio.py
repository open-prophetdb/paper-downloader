import os
import sys
import requests
import json
import yaml
import subprocess
from watchdog.observers import Observer
from watchdog.events import *
import time
import tempfile
import hashlib
from datetime import datetime
import logging

# log config
# create logger
logger = logging.getLogger('Notifier')
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
fh = logging.FileHandler('/var/log/notifier.log')
fh.setLevel(logging.DEBUG)
# create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# add formatter to console handler
fh.setFormatter(formatter)
# add console handler to logger
logger.addHandler(fh)

root_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications"
config_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/config"
metadata_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/metadata"
html_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/html"
pdf_dir = "/data/prophetdb/prophetdb-studio/data/paper-downloader/publications/pdf"
python_bin = "/data/prophetdb/prophetdb-studio/paper-downloader/.venv/bin/python"
script = "/data/prophetdb/prophetdb-studio/paper-downloader/main.py"


def md5(string):
    m = hashlib.md5()
    m.update(string.encode("utf-8"))
    return m.hexdigest()


def send_notification(msg):
    # Replace with your own DingTalk Bot webhook URL
    url = 'https://oapi.dingtalk.com/robot/send?access_token=cae67b70f6cf807554ba99c12a1131037bbb7ae748fe7bfcedff1becebed388f'

    headers = {'Content-Type': 'application/json;charset=utf-8'}

    data = {
        "msgtype": "text",
        "text": {
            "content": msg
        },
    }

    r = requests.post(url, headers=headers, data=json.dumps(data))
    logger.info(r.text)


def read_bib(bib_path):
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        temp_file = f.name
        cmd = f"{python_bin} {script} bib2pd -o {temp_file} -b {bib_path}"

        subprocess.call(cmd, shell=True)

        if os.path.exists(temp_file):
            with open(temp_file, 'r') as f:
                data = json.load(f)
                return data
        else:
            return None


def handle_configfile_event(filepath, uniq_str):
    # If you change the directory structure, you need to change the parent_dir
    logger.info("Find a new config file: %s" % filepath)

    if os.path.isfile(filepath) and filepath.startswith(config_dir):
        dirname = os.path.dirname(filepath)
        filename = os.path.basename(filepath)
        project = os.path.basename(dirname)
        dest_dir = os.path.join(metadata_dir, project)
        author = os.path.basename(os.path.dirname(filepath))

        try:
            msg = f"{uniq_str}: 收到新的检索式，但是文件格式不正确。请检查文件格式是否为bib, json或yaml。"
            data = None
            with open(os.path.abspath(filepath), 'r') as f:
                if filepath.endswith(".json"):
                    data = json.load(f)
                    dest_file = os.path.join(
                        dest_dir, filename.replace(".json", ".json"))
                    msg = f"{uniq_str}: 收到新的检索式，正在处理。"
                elif filepath.endswith("yaml"):
                    data = yaml.load(f, Loader=yaml.FullLoader)
                    dest_file = os.path.join(
                        dest_dir, filename.replace(".yaml", ".json"))
                    msg = f"{uniq_str}: 收到新的检索式，正在处理。"
                elif filepath.endswith("bib"):
                    data = read_bib(filepath)
                    dest_file = os.path.join(
                        dest_dir, filename.replace(".bib", ".json"))
                    msg = f"{uniq_str}: 收到新的检索式，正在处理。"

            send_notification(msg)
            if filepath.endswith(".log"):
                return None

            if data is None:
                return None
        except Exception as e:
            logger.error(e)
            send_notification(f"{uniq_str}: 收到新的检索式，但是文件格式不正确。请检查文件格式是否为bib, json或yaml。")
            return None

        # Check & Update the metadata file
        data.update({"author": author})
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            temp_file = f.name
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=4)
                filepath = temp_file

        download_pdf = data.get("download_pdf")

        cmd = f"{python_bin} {script} fetch-metadata -d 3 -o {dest_file} -c {filepath}"

        if os.path.exists(dest_file):
            relative_dir = os.path.relpath(dest_dir, metadata_dir)
            minio_dir = os.path.join("metadata", relative_dir)
            filename = os.path.basename(dest_file)
            msg = f"{uniq_str}: {author}上传了新的检索式，但系统检测到在{minio_dir}目录已有相同的Metadata文件{filename}, 请重命名配置文件后重试。"
            send_notification(msg)
            return None

        try:
            subprocess.call(cmd, shell=True)
            if download_pdf:
                msg = f"{uniq_str}: {author}上传了新的检索式，系统已获取到新的文献元数据。正在下载文献PDF，请稍后。"
                send_notification(msg)
                download_pdfs(dest_file, uniq_str)

            msg = f"{uniq_str}: 系统已处理完毕{author}上传的新的检索式。请前往publications.3steps.cn下载Metadata，并导入至Prophet Studio。"

            send_notification(msg)
        except Exception as e:
            msg = f"{author}上传了新的检索式，但系统处理时出现了错误。请管理员前往Prophet Server查看错误信息。以下是错误信息：\n{e}"
            send_notification(msg)

    else:
        logger.error("The file is not an expected config json file")


def download_pdfs(metadata_json_file, uniq_str):
    if not os.path.isfile(metadata_json_file):
        logger.error("The metadata file is not an expected json file")
        return None

    cmd = f"{python_bin} {script} fetch-pdf -o {pdf_dir} -m {metadata_json_file}"
    try:
        subprocess.call(cmd, shell=True)
        msg = f"{uniq_str}: 系统已下载完所有文献PDF。请前往Prophet Studio查看。"
        send_notification(msg)
    except Exception as e:
        msg = f"{uniq_str}: 系统处理时出现了错误。请管理员前往Prophet Server查看错误信息。以下是错误信息：\n{e}"
        logger.error(msg)
        send_notification(msg)

# Define a function to handle events


def handle_pdf_event(filepath, uniq_str):
    # If you change the directory structure, you need to change the parent_dir
    logger.info("Find a new file: %s" % filepath)
    if os.path.isfile(filepath) and filepath.endswith(".pdf") and filepath.startswith(pdf_dir):
        msg = f"{uniq_str}: 系统已获取到新的文献PDF。正在转换为HTML，请稍后。"
        send_notification(msg)

        cmd = f"{python_bin} {script} pdf2html -p {pdf_dir} -h {html_dir}"
        subprocess.call(cmd, shell=True)
        if os.path.exists(os.path.join(html_dir, os.path.basename(filepath).replace(".pdf", ".html"))):
            msg = f"{uniq_str}: 系统已将所有文献PDF转换为HTML。请前往Prophet Studio查看。"
            send_notification(msg)
    else:
        logger.info("The file is not a expected pdf file")


class FileEventHandler(FileSystemEventHandler):
    def __init__(self):
        FileSystemEventHandler.__init__(self)

    def on_moved(self, event):
        if event.is_directory:
            logger.info("directory moved from {0} to {1}".format(
                event.src_path, event.dest_path))
        else:
            logger.info("file moved from {0} to {1}".format(
                event.src_path, event.dest_path))

    def on_created(self, event):
        try:
            if event.is_directory:
                logger.info("directory created:{0}".format(event.src_path))
            else:
                uniq_str = md5(event.src_path)
                logger.info("file created:{0}".format(event.src_path))
                if event.src_path.startswith(pdf_dir):
                    handle_pdf_event(event.src_path, uniq_str)

                if event.src_path.startswith(config_dir):
                    handle_configfile_event(event.src_path, uniq_str)
        except Exception as e:
            logger.error(e)

    def on_deleted(self, event):
        if event.is_directory:
            logger.info("directory deleted:{0}".format(event.src_path))
        else:
            logger.info("file deleted:{0}".format(event.src_path))

    def on_modified(self, event):
        if event.is_directory:
            logger.info("directory modified:{0}".format(event.src_path))
        else:
            logger.info("file modified:{0}".format(event.src_path))


def main():
    observer = Observer()
    event_handler = FileEventHandler()
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
    main()
