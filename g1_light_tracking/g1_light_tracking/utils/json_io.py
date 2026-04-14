import json
from std_msgs.msg import String

def dumps_msg(data: dict) -> String:
    msg = String()
    msg.data = json.dumps(data, ensure_ascii=False)
    return msg

def loads_msg(msg: String) -> dict:
    return json.loads(msg.data) if msg.data else {}
