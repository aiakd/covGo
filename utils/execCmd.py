import os
import sys
from utils.logs import MyLog
import subprocess

def execCmd(cmd):
    MyLog.info(f"ExecCmd start: {cmd}")
    pingaling = os.popen(cmd,"r")
    while 1:
        line = pingaling.readline()
        if not line: break
        MyLog.info(line)
        sys.stdout.flush()
        # pingaling.close()
    MyLog.info(f"ExecCmd end: {cmd}")

# os.chdir("D:\work_space\simple-go-server")
# execCmd("diff-cover merge.xml --compare-branch=ae4b318d245d7fe463f3e69f9a866c47cab0db44 --html-report report33.html")
def runCommand(command, timeout=30):
    try:
        # 执行命令并获取输出
        MyLog.info(f"ExecCmd end: {command}")

        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=True
        )
        # 如果命令执行成功，返回标准输出
        MyLog.info(f"ExecCmd end: {result.stdout}")

        return result.stdout
    except subprocess.CalledProcessError as e:
        # 捕获命令执行错误并输出错误信息
        MyLog.info(f"命令执行失败, 错误码: {e.returncode}")
        MyLog.info(f"错误信息: {e.stderr}")
        return None
    except subprocess.TimeoutExpired as e:
        # 捕获超时异常
        MyLog.info(f"命令执行超时: {e}")
        return None
    except FileNotFoundError as e:
        # 捕获找不到命令的错误
        MyLog.info(f"找不到命令: {e}")
        return None
    except Exception as e:
        # 捕获其他异常
        MyLog.info(f"发生未知错误: {e}")
        return None

