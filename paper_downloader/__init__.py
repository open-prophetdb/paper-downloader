import json
import logging
import requests

logger = logging.getLogger("paper_downloader")

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
