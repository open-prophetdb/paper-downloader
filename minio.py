import os
import sys
import requests
import json
import yaml
import subprocess
from watchdog.observers import Observer
from watchdog.events import *
import time
import logging

# log config
# create logger
logger = logging.getLogger('Notifier')
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
fh = logging.FileHandler('/var/log/notifier.log')
fh.setLevel(logging.DEBUG)
# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# add formatter to console handler
fh.setFormatter(formatter)
# add console handler to logger
logger.addHandler(fh)

config_dir = "/data/prophetdb/prophetdb-studio/data/publications/2023/config/"
metadata_dir = "/data/prophetdb/prophetdb-studio/data/publications/2023/metadata"
html_dir = "/data/prophetdb/prophetdb-studio/data/publications/2023/html"
pdf_dir = "/data/prophetdb/prophetdb-studio/data/publications/2023/pdf"
python_bin = "/data/prophetdb/prophetdb-studio/paper-downloader/.venv/bin/python"
script = "/data/prophetdb/prophetdb-studio/paper-downloader/main.py"


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


def handle_configfile_event(filepath):
    # If you change the directory structure, you need to change the parent_dir
    logger.info("Find a new config file: %s" % filepath)

    if os.path.isfile(filepath) and filepath.startswith(config_dir):
        with open(os.path.abspath(filepath), 'r') as f:
            if filepath.endswith(".json"):
                data = json.load(f)
            elif filepath.endswith("yaml"):
                data = yaml.load(f, Loader=yaml.FullLoader)
            else:
                return None

        author = data.get("author")
        download_pdf = data.get("download_pdf")
        send_notification("收到新的检索式，正在处理中，请稍后。")
        dirname = os.path.dirname(filepath)
        filename = os.path.basename(filepath)
        project = os.path.basename(dirname)
        dest_dir = os.path.join(metadata_dir, project)
        dest_file = os.path.join(dest_dir, filename.replace(".yaml", ".json"))
        cmd = f"{python_bin} {script} fetch-metadata -d 3 -o {dest_file} -c {filepath}"

        if not author:
            author = "匿名用户"

        try:
            output = subprocess.check_output(cmd, shell=True)
            if download_pdf:
                msg = f"{author}上传了新的检索式，系统已获取到新的文献元数据。正在下载文献PDF，请稍后。"
                send_notification(msg)
                download_pdfs_output = download_pdfs(dest_file)
                output = output + "\n\n" + download_pdfs_output

                msg = f"系统已处理完毕{author}上传的新的检索式。请前往publications.3steps.cn下载Metadata，并导入至Prophet Studio。"
            else:
                msg = f"{author}上传了新的检索式，系统已处理完毕。请前往publications.3steps.cn下载Metadata，并导入至Prophet Studio。"
            
            send_notification(msg)
            logger.info(output)

            log_filepath = filepath.replace(".yaml", ".log").replace(".json", ".log")
            with open(log_filepath, 'w') as f:
                f.write(output)
        except Exception as e:
            msg = f"{author}上传了新的检索式，但系统处理时出现了错误。请管理员前往Prophet Server查看错误信息。以下是错误信息：\n{e}"
            send_notification(msg)
    else:
        logger.error("The file is not an expected config json file")

def download_pdfs(metadata_json_file):
    if not os.path.isfile(metadata_json_file):
        logger.error("The metadata file is not an expected json file")
        return None

    cmd = f"{python_bin} {script} fetch-pdf -o {pdf_dir} -m {metadata_json_file}"
    try:
        output = subprocess.check_output(cmd, shell=True)
        msg = f"系统已下载完所有文献PDF。请前往Prophet Studio查看。"
        send_notification(msg)
        return output
    except Exception as e:
        msg = f"系统处理时出现了错误。请管理员前往Prophet Server查看错误信息。以下是错误信息：\n{e}"
        send_notification(msg)
        return str(e)

# Define a function to handle events
def handle_pdf_event(filepath):
    # If you change the directory structure, you need to change the parent_dir
    logger.info("Find a new file: %s" % filepath)
    if os.path.isfile(filepath) and filepath.endswith(".pdf") and filepath.startswith(pdf_dir):
        cmd = f"{python_bin} {script} pdf2html -p {pdf_dir} -h {html_dir}"
        output = subprocess.check_output(cmd, shell=True)
        logger.info(output)
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
                logger.info("file created:{0}".format(event.src_path))
                if event.src_path.startswith("/data/prophetdb/prophetdb-studio/data/publications/2023/pdf"):
                    handle_pdf_event(event.src_path)

                if event.src_path.startswith("/data/prophetdb/prophetdb-studio/data/publications/2023/config"):
                    handle_configfile_event(event.src_path)
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
    observer.schedule(
        event_handler, "/data/prophetdb/prophetdb-studio/data/publications/2023", True)
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
