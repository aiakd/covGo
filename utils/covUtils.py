import os
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from django.conf import settings
import time, re
# 获取被测机器列表
from utils.execCmd import execCmd


def getClientServerList():
    # res = requests.get("http://127.0.0.1:7777/v1/cover/list")
    res = requests.get("http://192.168.56.101:7777/v1/cover/list")
    print(res.json())
    clientServerList = res.json()['simple-go-server']
    print(clientServerList)
    return clientServerList

# 定义覆盖率文件存储位置
def covReportsPath(gitProjectName,covTaskId):
    covReportsPath = os.path.join(settings.BASE_DIR, '..', 'covFilesDir', 'covReports',str(gitProjectName).strip(), str(covTaskId).strip())
    execCmd(f'''chmod 777 {covReportsPath}''')
    return covReportsPath

# 生成runId
def generateRunId(t, covTaskId,originalHostPort):
    patternHostPort = re.compile(r'''\/\/(.*)''')
    if originalHostPort:
        hostPort = re.findall(patternHostPort,str(originalHostPort))[0]
        hostPort = hostPort.replace(':','_')
        res = f'''{t}-{covTaskId}-{hostPort}'''
    else:
        res = f'''{t}-{covTaskId}'''
    return res
# hostPort = 'http://192.168.56.101:46599'
# generateRunId(1,hostPort)

def crawlCovFromHtml(htmlPath):
    htmlfile = open(htmlPath, 'r', encoding='utf-8')
    htmlhandle = htmlfile.read()
    s = BeautifulSoup(htmlhandle, 'lxml')

    htmlStr = str(s)  # 正则必须是string

    patternDiffLineTotal = re.compile(r'''<li><b>Total</b>: (.*) lines</li>''')
    diffLineTotal = re.findall(patternDiffLineTotal, htmlStr)[0]

    patternMissLineTotal = re.compile(r'''<li><b>Missing</b>: (.*) lines</li>''')
    missLineTotal = re.findall(patternMissLineTotal, htmlStr)[0]

    patternCoverage = re.compile(r'''<li><b>Coverage</b>: (.*)</li>''')
    coverage = re.findall(patternCoverage, htmlStr)[0]

    return {"diffLineTotal":diffLineTotal, "missLineTotal":missLineTotal, "coverage":coverage}

# path = '''D://work_space//covFilesDir//covReports//simple-go-server//1//merge20220622193826355853-1.html'''
# res = crawlCovFromHtml(path)
# print(res['diffLineTotal'])
# print(type(res))
