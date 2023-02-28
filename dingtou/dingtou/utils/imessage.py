import json
import logging
import requests
import smtplib
from email.header import Header
from email.mime.text import MIMEText


logger = logging.getLogger(__name__)

"""
用法：
    MessageSender().send(title,msg,topic)
"""


class MessageSender():
    SIGNAL = 'signal'
    ERROR = 'error'

    def __init__(self, conf):
        self.conf = conf
        self.senders = {
            'weixin': WeixinMessager(conf),
            # 'plusplus': PlusMessager(conf),
            # 'mail': MailMessager(conf),
        }

    def send(self, title, msg, type):
        for name, messager in self.senders.items():
            messager.send(title, msg, type)


class Messager():
    def __init__(self, conf):
        self.conf = conf

    def send(self, title, msg, type):
        pass


class PlusMessager(Messager):
    def send(self, title, msg, type='signal'):
        try:
            # http://www.pushplus.plus/doc/guide/api.htm
            url = 'http://www.pushplus.plus/send'
            data = {
                "token": self.conf['plusplus']['token'],
                "title": title,
                "content": msg,
                "topic": type
            }
            body = json.dumps(data).encode(encoding='utf-8')
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, data=body, headers=headers)
            data = response.json()
            if data and data.get("code", None) and data["code"] == 200:
                return
            if data and data.get("code", None):
                logger.warning("发往PlusPlus消息错误: code=%r, msg=%s, token=%s, topic=%s",
                               data['code'], data['msg'], self.conf['plusplus']['token'][:10] + "...", type)
            else:
                logger.warning("发往PlusPlus消息错误: 返回为空")
        except Exception:
            logger.exception("发往PlusPlus消息发生异常", msg)
            return False


class MailMessager(Messager):
    def send(self, title, msg, type):
        try:
            uid = self.conf['email']['uid']
            pwd = self.conf['email']['pwd']
            host = self.conf['email']['host']
            email = self.conf['email']['email']

            receivers = [email]  # 接收邮件，可设置为你的QQ邮箱或者其他邮箱

            # 三个参数：第一个为文本内容，第二个 plain 设置文本格式，第三个 utf-8 设置编码
            message = MIMEText(msg, 'plain', 'utf-8')
            message['From'] = Header("量化机器人", 'utf-8')  # 发送者
            message['To'] = Header("量化机器人", 'utf-8')  # 接收者
            message['Subject'] = Header(f'{title} - {type}', 'utf-8')

            # logger.info("发送邮件[%s]:[%s:%s]", host,uid,pwd)
            smtp = smtplib.SMTP_SSL(host)
            smtp.login(uid, pwd)
            smtp.sendmail(uid, receivers, message.as_string())
            logger.info("发往[%s]的邮件通知完成，标题：%s", email, title)
            return True
        except smtplib.SMTPException:
            logger.exception("发往[%s]的邮件出现异常，标题：%s", email, email)
            return False


class WeixinMessager(Messager):
    def send(self, title, msg, type):
        """
        接口文档：https://developer.work.weixin.qq.com/document/path/91770?version=4.0.6.90540
        """
        try:
            logger.info("开始推送微信[类别:%s]消息", type)
            url = self.conf['weixin'][type]

            post_data = {
                "msgtype": "text",
                "text": {
                    "content": f"标题:{title}:\n内容:\n{msg[:2040]}"  # content    是    文本内容，最长不超过2048个字节，必须是utf8编码
                }
            }
            headers = {'Content-Type': 'application/json'}
            requests.post(url, json=post_data, headers=headers)
            logger.info("发往企业微信机器人[%s]的通知完成", type)
            return True
        except Exception:
            logger.exception("发往企业微信机器人[%s]的消息[%s...]，发生异常", type, msg[:200])
            return False


# python -m dingtou.utils.imessage
if __name__ == '__main__':
    from dingtou.utils.utils import load_conf, init_logger

    init_logger()
    conf = load_conf("conf/config.yml")
    s = MessageSender(conf)
    s.send("信号标题", "信号内容", s.SIGNAL)
    s.send("错误标题", "错误内容", s.ERROR)
