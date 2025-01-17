import time
from django.conf import settings
from utils.execCmd import execCmd,runCommand
from utils.fileHandle import getXmlFileName
from utils.gitHandle import cloneCode, pullCode, checkOutBranch, downloadPath
from cov.models import project as projectModel
from cov.models import covTask as covTaskModel
from cov.models import covTaskHistory as covTaskHistoryModel
from cov.models import reports as reportsModel
from utils.logs import MyLog
from django.db import connection
from utils.covUtils import *

# 初次创建覆盖率任务后，任务状态=0，需要对0状态的进行clone代码到指定的任务目录
# todo 这个任务期望每1分钟检查一次
def cloneToTaskDir():
    MyLog.info(f"-----cloneToTaskDir任务开始执行-----")
    # 查出库里有哪些是0状态的数据待clone
    cursor = connection.cursor()
    cursor.execute('''SELECT c.id AS cid,
                                p.id AS pid, 
                                gitName,
                                gitUrl,
                                gitPwd,
                                covTaskName,
                                p.projectName 
                                FROM cov_covtask c
                                    LEFT JOIN cov_project p ON  c.projectId = p.id
                                    WHERE c.deleted = 0 AND c.status=0 AND p.deleted = 0 
                                        ''')
    resObj = cursor.fetchall()
    i = 0
    # 依次下载
    for res in resObj:
        res = resObj[i]
        username = res[2]
        pwd = res[4]
        gitUrl = res[3]
        gitProjectName = res[6]
        covTaskId = res[0]
        covTaskName = res[5]
        gitCodePath = downloadPath(gitProjectName, covTaskId)

        MyLog.info(f"首次下载--start git clone--覆盖率任务名称:{covTaskName}--仓库地址:{gitUrl}")
        try:
            cloneCode(username, pwd, gitUrl, gitProjectName, covTaskId)
            checkout_remote_branch_cmd = f'''cd {gitCodePath} && git checkout -b master origin/master'''
            execCmd(checkout_remote_branch_cmd)
            MyLog.info(f"首次下载完毕--end git clone--覆盖率任务名称:{covTaskName}--仓库地址:{gitUrl}")
            covTaskModel.objects.filter(id=covTaskId).update(status=1,
                                                             updateTime=time.strftime("%Y-%m-%d %H:%M:%S")
                                                             )
        except Exception as e:
            MyLog.error(f"首次下载异常--end git clone--覆盖率任务名称:{covTaskName}--仓库地址:{gitUrl}，报错如下: {str(e)}")
            covTaskModel.objects.filter(id=covTaskId).update(status=2,
                                                             updateTime=time.strftime("%Y-%m-%d %H:%M:%S")
                                                             )
        i = i + 1


# 获取覆盖率
def getCov():
    MyLog.info(f"-----getCov任务开始执行-----")
    # 1、获取被测试分支
    # 查出库里有哪些是1和3状态的数据待pull、获取覆盖率
    cursor = connection.cursor()
    cursor.execute('''SELECT c.id AS cid,
                                    p.id AS pid, 
                                    gitName,
                                    gitUrl,
                                    gitPwd,
                                    covTaskName,
                                    p.projectName ,
                                    c.branch,
                                    c.clientServerHostPort
                                    FROM cov_covtask c
                                        LEFT JOIN cov_project p ON  c.projectId = p.id
                                        WHERE c.deleted = 0 AND c.status IN(1,3,31) AND p.deleted = 0 AND c.startTime <= NOW() AND NOW() <= c.endTime 
                                            ''')
    resObj = cursor.fetchall()
    i = 0
    # 依次下载
    for res in resObj:
        res = resObj[i]
        username = res[2]
        pwd = res[4]
        gitUrl = res[3]
        gitProjectName = res[6]
        covTaskId = res[0]
        covTaskName = res[5]
        branch = res[7]
        clientServerHostPort = res[8]
        MyLog.info(f"开始搜集覆盖率--覆盖率任务名称:{covTaskName}--clientServerList:{clientServerHostPort}")
        try:
            # 拉取代码
            checkOutBranch(gitProjectName, covTaskId, branch="master")

            pullCode(gitProjectName, covTaskId)
            # 切换分支
            checkOutBranch(gitProjectName, covTaskId, branch)
            pullCode(gitProjectName, covTaskId)

            # 获取被测机器列表 todo 与填写的进行对比
            gocServer = eval(clientServerHostPort)[0]
            # 拉取覆盖率
            t = datetime.now().strftime('%Y%m%d%H%M%S%f')
            cmd_goc =['goc', 'service', 'get', '--host={0}'.format(gocServer), '--wide']
            server_id_str = runCommand(cmd_goc)
            MyLog.info(f'server_id_str:{server_id_str}')

            server_id_list = getGocServieslist(server_id_str)
            MyLog.info(f'server_id_list:{server_id_list}')

            connect_server_list = [server['ID'] for server in server_id_list if server['STATUS'] == 'CONNECT' and gitProjectName in server['HOSTNAME']]
            MyLog.info(f'connect_server_list:{connect_server_list}')

            for id in connect_server_list:
                covPath = covReportsPath(gitProjectName, covTaskId)
                runId = generateRunId(t, covTaskId, None)
                covFileName = generateRunId(t, covTaskId, originalHostPort=id)
                # 拉取正常的入库status=1
                try:
                    # getCovcmd = f'''{settings.BASE_DIR}/cmdTools/goc profile --center={clientServer} -o {covPath}/{covFileName}.cov'''
                    # V2 getCovcmd = f'''{settings.BASE_DIR}/cmdTools/goc profile get --host={hostServer} -o {covPath}/{covFileName}.cov'''
                    getCovcmd = f'''goc profile get --host={gocServer} --id={id} --skip='.pb.' -o {covPath}/{covFileName}.cov'''
                    MyLog.info(f'getCovcmd:{getCovcmd}')
                    execCmd(getCovcmd)
                    p = covTaskHistoryModel(runId=runId,
                                            covTaskId=covTaskId,
                                            clientServerHostPort=id,
                                            covFileName=covFileName + ".cov",
                                            status=3,
                                            )
                    p.save()
                    covTaskModel.objects.filter(id=covTaskId).update(
                        status=31,
                        lastCollectTime=time.strftime("%Y-%m-%d %H:%M:%S"),
                        updateTime=time.strftime("%Y-%m-%d %H:%M:%S")
                    )
                    MyLog.info(f"收集覆盖率完毕--覆盖率任务名称:{covTaskName}--服务器:{id}")
                # 拉取非正常的入库status=2
                except Exception as e:
                    p = covTaskHistoryModel(runId=runId,
                                            covTaskId=covTaskId,
                                            clientServerHostPort=id,
                                            covFileName=runId + ".cov",
                                            status=2,
                                            )
                    p.save()
                    MyLog.info(f"收集覆盖率异常--覆盖率任务名称:{covTaskName}--服务器:{id}，报错如下: {str(e)}")

        except Exception as e:
            MyLog.error(f"获取覆盖率cov文件异常--覆盖率任务名称:{covTaskName}--仓库地址:{gitUrl}，报错如下: {str(e)}")
            covTaskModel.objects.filter(id=covTaskId).update(
                updateTime=time.strftime("%Y-%m-%d %H:%M:%S")
            )
        i = i + 1


# 生成覆盖率报告
def generateHtmlReport():
    MyLog.info(f"-----generateHtmlReport任务开始执行-----")
    # 查出库里状态是1的covTaskId
    cursor = connection.cursor()
    cursor.execute('''SELECT c.id AS cid,
                                p.id AS pid, 
                                gitName,
                                gitUrl,
                                gitPwd,
                                compareBranch,
                                covTaskName,
                                p.projectName,
                                branch 
                                FROM cov_covtask c
                                    LEFT JOIN cov_project p ON  c.projectId = p.id
                                    WHERE c.deleted = 0 AND c.status IN (31) AND p.deleted = 0  AND c.startTime <= NOW() AND NOW() <= c.endTime
                                        ''')
    resObj = cursor.fetchall()
    i = 0
    # 依次
    for res in resObj:
        res = resObj[i]
        compareBranch = res[5]
        covTaskName = res[6]
        gitProjectName = res[7]
        covTaskId = res[0]
        branch = res[8]
        covPath = covReportsPath(gitProjectName, covTaskId)
        t = datetime.now().strftime('%Y%m%d%H%M%S%f')
        runId = generateRunId(t, covTaskId, None)
        mergeCovName = "merge" + str(runId)
        try:
            MyLog.info(f"开始生成html--覆盖率任务名称:{covTaskName}")
            xmlNameList = getXmlFileName(covPath)
            # 把0kb的xml视为有问题的文件
            for xml in xmlNameList:
                if os.stat(f'{covPath}/{xml}').st_size == 0:
                    mvToErrorCmd = f'''mv {covPath}/{xml}  {covPath}/{xml}.error'''
                    MyLog.info(f'''mvToErrorCmd: {mvToErrorCmd}''')
                    execCmd(mvToErrorCmd)
            # 合并全部覆盖率文件
            # mergeCmd = f'''{settings.BASE_DIR}/cmdTools/goc merge {covPath}/*.cov -o {covPath}/{mergeCovName}.cov'''
            mergeCmd = f'''goc merge {covPath}/*.cov -o {covPath}/{mergeCovName}.cov'''
            MyLog.info(f'mergeCmd:{mergeCmd}')
            execCmd(mergeCmd)
            # 把历史cov文件移到bak文件夹
            mvTobakCmd = f'''mkdir -p {covPath}/bak && mv {covPath}/*.cov {covPath}/bak'''
            MyLog.info(f'mvTobakCmd:{mvTobakCmd}')
            execCmd(mvTobakCmd)
            # 把最新的cov文件移出来，下次merge使用
            mvNewMergeOutCmd = f'''mv {covPath}/bak/{mergeCovName}.cov {covPath}'''
            MyLog.info(f'mvNewMergeOutCmd:{mvNewMergeOutCmd}')
            execCmd(mvNewMergeOutCmd)
            # 代码路径
            gitCodePath = downloadPath(gitProjectName, covTaskId)
            # 全量覆盖率生成 todo
            covToHtmlCmd = f'''cd {gitCodePath} && export GOPATH=$GOPATH:{gitCodePath} && {settings.BASE_DIR}/cmdTools/gocov convert {covPath}/{mergeCovName}.cov | {settings.BASE_DIR}/cmdTools/gocov-html > {covPath}/full_{mergeCovName}.html'''
            MyLog.info(f'covToHtmlCmd:{covToHtmlCmd}')
            execCmd(covToHtmlCmd)
            m = reportsModel(runId=runId,
                             type=1,
                             covTaskId=covTaskId,
                             htmlFileName='full_' + mergeCovName + '.html',
                             status=1,
                             )
            m.save()

            # 把cov转换成xml
            # covToXmlCmd = f'''cd {covPath} && gocov convert {covPath}/{mergeCovName}.cov | gocov-xml > {covPath}/{mergeCovName}.xml'''

            covToXmlCmd = f'''cd {gitCodePath} && export GOPATH=$GOPATH:{gitCodePath} && {settings.BASE_DIR}/cmdTools/gocov convert {covPath}/{mergeCovName}.cov | {settings.BASE_DIR}/cmdTools/gocov-xml > {covPath}/{mergeCovName}.xml'''
            MyLog.info(f'covToXmlCmd:{covToXmlCmd}')
            execCmd(covToXmlCmd)

            # 判断生成的xml大小是否为0,为0则不进行下一步转换
            if os.stat(f'{covPath}/{mergeCovName}.xml').st_size != 0:
                # xml转换成后html文件
                xmlToHtmlCmd = f'''cd {gitCodePath} && diff-cover {covPath}/{mergeCovName}.xml --compare-branch={compareBranch}..{branch} --html-report {covPath}/{mergeCovName}.html'''
                MyLog.info(f'xmlToHtmlCmd:{xmlToHtmlCmd}')
                execCmd(xmlToHtmlCmd)
                MyLog.info(f"生成html完毕--覆盖率任务名称:{covTaskName}--生成文件：{mergeCovName}.html")
            elif os.stat(f'{covPath}/{mergeCovName}.xml').st_size == 0:
                mvToErrorCmd2 = f'''mv {covPath}/{xml}  {covPath}/{xml}.error'''
                MyLog.info(f'''mvToErrorCmd2:: {mvToErrorCmd2}''')
                execCmd(mvToErrorCmd2)

            p = reportsModel(runId=runId,
                             covTaskId=covTaskId,
                             htmlFileName=mergeCovName + '.html',
                             status=1,
                             )
            p.save()
        except Exception as e:
            p = reportsModel(runId=runId,
                             covTaskId=covTaskId,
                             htmlFileName=mergeCovName + '.html',
                             status=2,
                             )
            p.save()
            # 把错误xml文件重命名，以免下次会再次merge报错
            execCmd(f'''mv {covPath}/{mergeCovName}.xml  {covPath}/{mergeCovName}.xml.error''')
            MyLog.error(f"生成html失败--覆盖率任务名称:{covTaskName}--生成文件：{mergeCovName}.html，报错如下: {str(e)}")
        i = i + 1


# 从html报告中爬取覆盖率
def getCovFromHtml():
    MyLog.info(f"-----开始爬取覆盖率-----")
    # 查出库里状态是1的covTaskId
    cursor = connection.cursor()
    cursor.execute('''SELECT r.id,
                        r.runId,
                        c.projectName,
                        c.id,
                        c.covTaskName,
                        c.branch,
                        c.compareBranch,
                        r.createTime,
                        r.diffLineTotal,
                        r.missLineTotal,
                        r.coverage,
                        r.isCrawled,
                        r.htmlFileName
                         FROM `cov_reports` r
                        LEFT JOIN cov_covtask c ON r.covTaskId = c.id
                        WHERE  r.status = 1 AND r.isCrawled = 0 ORDER BY createTime ASC 
                                            ''')
    resObj = cursor.fetchall()
    i = 0
    # 依次
    for res in resObj:
        res = resObj[i]
        id = res[0]
        gitProjectName = res[2]
        covTaskId = res[3]
        htmlFileName = res[12]
        htmlPath = os.path.join(covReportsPath(gitProjectName, covTaskId), htmlFileName)
        try:
            covRes = crawlCovFromHtml(htmlPath)
            reportsModel.objects.filter(id=id).update(
                isCrawled=1,
                diffLineTotal=covRes['diffLineTotal'],
                missLineTotal=covRes['missLineTotal'],
                coverage=covRes['coverage'],
                updateTime=time.strftime("%Y-%m-%d %H:%M:%S")
            )
            MyLog.info(f"-----爬取covTask:{covTaskId}成功-----")
        except Exception as e:
            reportsModel.objects.filter(id=id).update(
                isCrawled=2,
                diffLineTotal="-1",
                missLineTotal="-1",
                coverage="-1",
                updateTime=time.strftime("%Y-%m-%d %H:%M:%S")
            )
            MyLog.error(f"-----爬取covTask:{covTaskId}失败-----，报错如下: {str(e)}")

        i = i + 1
