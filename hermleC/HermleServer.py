# -*- coding: utf-8 -*-
"""
Created on Tue Dec  4 14:48:51 2018

@author: TQ_006
"""
import socket
import sys
import os
import json
import time
import csv
import zmq
import getopt
import threading
import snap7
import struct
import copy

serverHelpDoc = """

本服务用于展示PIC服务模型功能。PIC服务模型在PIC内部运行，通过服务总线连接到PIC主系统。
PIC服务一般在系统启动时加载运行，可以带有命令行参数，参数包括：

1. 采用-port=xxxx指定服务端口。
2. 采用-help显示本帮助

服务模型与PIC模型之间采用JSON形式通讯。本服务模型提供以下接口：
“{Register: ?}” PIC模型发给服务模型，服务模型返回注册信息，主要包括程序名称和相关服务内容。
“{serverName: xxx, serverPort: xxxx, serverFunction1: sfName1}”

"""
# ----------------------------------------------------------------------------------------------
# 系统变量
serverName = sys.argv[0]
serverIP = '172.16.45.199'
dnccmdIP = 'localhost'
# rootserverIP = '172.16.31.30'
rootserverIP = '10.3.1.201'

# Local
serverPort1 = '5020'
serverPort2 = '5021'
serverPort3 = '5030'

# Remote root server
port_dispatchServer = '5051'
port_statusUpdate = '5071'
port_rabbit = '5001'
rootErrorLoggerPort = '5618'

DNCServicePort = '5556'
serverFunctions = {}
otherFunctions = {}
# tqdir = 'D:\\tq\\DNC\\DNCCommand\\DNCCommand\\bin\Debug\\' # DNCcommand文件目录
# tqdir = 'D:\\tq\\DNC\\new\\DNCCommand\\DNCCommand\\DNCCommand\\bin\Debug\\' # DNCcommand文件目录
tncProgramDir = 'D:\\ProgramData\\TQ\\Hermle\\TNCProgram\\'  # 加工文件的共享目录
hermleTNCProgramDir = 'TNC:\\HERMLE TEST\\'
setPoint = '8031'
trayStatus = '{"data": "None"}'
rfidBindindDict = {
    '1': '',
    '2': '',
    '3': ''
}
orderlist = {}
workingstep = '0'
loggingstep = True  # True时本进程记录， False时taskflow中记录
onlineSignal = False
serveractive = '0'  # 0 服务器断线，1 服务器空闲 2 服务器忙碌 3 服务器正在运行
hermleConnectedSignal = '0'
hermleConnectedSignalCounter = 0
# ----------------------------------------------------------------------------------------------
tqdata1 = bytearray(b'\x01')  # 置"1"
tqdata0 = bytearray(b'\x00')  # 置"0"
plcIP = '192.168.0.31'
reck = 0
slot = 1
# ----------------------------------------------------------------------------------------------
# Check hermleConnectedSignal


def sendInfo(port, data, ip=dnccmdIP):
	context = zmq.Context()
	zmqSocket = context.socket(zmq.REQ)
	zmqSocket.connect(f"tcp://{ip}:{port}")  # 172.16.14.102:5618 10.3.1.201:5618
	zmqSocket.send_string(json.dumps(data), flags=0, encoding='utf-8')
	zmqResponse = zmqSocket.recv_json()
	return zmqResponse


def updateConnectionError():
    global hermleConnectedSignal
    global hermleConnectedSignalCounter
    while True:
        if hermleConnectedSignalCounter > 5:
            alarmModel_MachineTools = {
                'logType': 'errorLog',
                'errorType': 'systemConnectionError',
                'isDisposed': 'False',
                'disposedBy': 'Anonymous'
            }
            tempDict = copy.deepcopy(alarmModel_MachineTools)
            tempDict['errorLocation'] = 'hermleC'
            tempDict['errorKey'] = 'Hermle01001'
            tempDict['errorMsg'] = 'connection failed between pic and hermleC'
            tempDict['Text'] = tempDict['errorKey'] + ': ' + tempDict['errorMsg']
            tempDict['Arrived'] = time.time()
            try:
                res = sendInfo(ip=rootserverIP, port=rootErrorLoggerPort,
                                data={'addErrorObj': {'modelsDict': tempDict}})
                print(f'from hermleC:\nafter send HermleC ConnectionError')
            except Exception as e:
                raise e
        elif hermleConnectedSignalCounter > 3:
            print('connection delay')
        else:
            ...
        if hermleConnectedSignal == '1':
            hermleConnectedSignalCounter = 0
            hermleConnectedSignal = '0'
            continue
        hermleConnectedSignalCounter += 1
        time.sleep(1)


# ----------------------------------------------------------------------------------------------

# trayStatusAdd = {'1': 'null', '2': 'null', '3': 'null'}

def sendCMD(ip, port, functionname='', msg=''):
    context = zmq.Context()
    zmqSocket = context.socket(zmq.REQ)
    # zmqSocket.connect("tcp://172.16.45.236:5000")
    zmqSocket.connect("tcp://" + ip + ":" + port)
    zmqData = {functionname: msg}
    zmqSocket.send_string(json.dumps(zmqData), flags=0, encoding='utf-8')
    zmqResponse = zmqSocket.recv_json()
    return zmqResponse

def send2DNCCommand(cmddict):
    context = zmq.Context()
    zmqSocket = context.socket(zmq.REQ)
    zmqSocket.connect("tcp://" + dnccmdIP + ":" + DNCServicePort)
    zmqData = cmddict
    zmqSocket.send_string(json.dumps(zmqData), flags=0, encoding='utf-8')
    zmqResponse = zmqSocket.recv_json()
    return zmqResponse


def bindRFID(a):
    """
    a = {
        'trayNum': '1',
        'RFID': '<uuid>'
    }
    """
    global rfidBindindDict
    trayNum = a.get('trayNum')
    rfid = a.get('RFID')
    rfidBindindDict[trayNum] = rfid
    return {
        'meta': {
            'status': 'success',
            'msg': 'bindingSuccess'
            },
        'data': f'{rfid}'
        }


def statusPut():
    global loggingstep
    global onlineSignal
    while True:
        if loggingstep:
            try:
                data = readStatus('default')
                print('>>>> in statusPut(), data:', data)
                data['机床状态']['online'] = onlineSignal
                print('>>>> in statusPut(), data2:', data)
            except Exception as e:
                print(f'>>>>    in statusPut() ERROR:\n{e}')
            try:
                print('>>>>    in statusPut():\n', data)
                sendCMD(rootserverIP, port_statusUpdate, functionname='uploadStatus', msg={'deviceName': 'hermle01', 'data': data})
        
                print('>>>> hermleStatusUpdated')
            except Exception as e:
                print('>>>>    \n>>>>    wrong\n>>>> \n>>>>    ', e)
            time.sleep(3)

def setLoggingStep(a):
    global loggingstep
    if a == 'False':
        loggingstep = False
        return {'res': 'already set loggingstep False'}
    elif a == 'True':
        loggingstep = True
        return {'res': 'already set loggingstep True'}
    else:
        return {'res': 'sth went wrong'}

def register(v):
    b = {}
    b['serverName'] = serverName
    b['serverPort1'] = serverPort1
    b['Register'] = v

    c = {}
    for k in serverFunctions.keys():
        c[k] = serverFunctions[k][1]
    b['serverFunction'] = c
    return b

def Configure():
    pass


def changeToManual(a):
    res = send2DNCCommand({'action': 'SetExecutionMode', 'arg1': 'DNC_EXEC_MANUAL'})
    if 'Status' in res:
        msg = '切换手动模式成功'
    elif 'Exception' in res:
        msg = '切换手动模式失败, 错误信息:\n' + str(res['Exception'])
    return {'msg':msg}


def changeToAutomatic(a):
    res = send2DNCCommand({'action': 'SetExecutionMode', 'arg1': 'DNC_EXEC_AUTOMATIC'})
    if 'Status' in res:
        msg = '切换自动模式成功'
    elif 'Exeption' in res:
        msg = '切换自动模式失败，错误代码： ' + str(res['Exception'])
    return {'msg':msg}


def downloadFiles(filename):
    res = send2DNCCommand({"action":"FileSystem_Transmit","arg1":f"{tncProgramDir + filename}","arg2":hermleTNCProgramDir})
    if 'Status' in res:
        msg = '切换自动模式成功'
    elif 'Exeption' in res:
        msg = '切换自动模式失败，错误代码： ' + str(res['Exception'])
    else:
        raise Exception(str(res))
    return {'msg':msg}


def deleteFiles(a):
    if a.get('arg1') and a.get('arg2'):
        filePath = a.get('arg1')
        is_file = str(a.get('arg2'))
    res = send2DNCCommand({"action":"FileSystem_Delete","arg1":filePath,"arg2":is_file})
    if 'Status' in res:
        msg = '切换自动模式成功'
    elif 'Exeption' in res:
        msg = '切换自动模式失败，错误代码： ' + str(res['Exception'])
    return {'msg':msg}


def receiveFiles(a): # {targetPath, localName} default localName=targetPath.split('\\')[-1]
    if a.get('tartgetPath'):
        filename = a.get('tartgetPath').split('\\')[-1]
        if a.get('localName'):
            localName = a.get('localName')
        else:
            localName = filename
        res = send2DNCCommand({
            "action":"FileSystem_Receive",
            "arg1":f"{hermleTNCProgramDir + filename}",
            "arg2": f"{tncProgramDir + localName}"
            })
        if 'Status' in res:
            msg = '下载加工文件成功'
        elif 'Exeption' in res:
            msg = '下载加工文件成功失败, 详细信息:\n' + str(res['Exception'])
        else:
            msg = '下载加工文件成功失败, 未知错误...'
    else:
        msg = msg = '下载加工文件成功失败, 未发现targetPath...'
    return {'msg':msg}


def selectFile(filename):
    res = send2DNCCommand({"action":"SelectProgram","arg1":hermleTNCProgramDir + filename})
    if 'Exeption' in res:
        msg = '下载加工文件成功失败, 详细信息:\n' + str(res['Exception'])
    elif 'Warning' in res:
        msg = '下载加工文件成功失败, 详细信息:\n' + str(res['Warning'])
    else:
        msg = '下载加工文件成功'
    return {'msg':msg}


def startCMD(filename):
    res = send2DNCCommand({"action":"StartProgram","arg1":f"{hermleTNCProgramDir + filename}"})
    if 'Status' in res:
        msg = '加工程序已启动'
    elif 'Exeption' in res:
        msg = '启动加工程序失败, 详细信息:\n' + str(res['Exception'])
    return {'msg':msg}


def stopCMD(a):
    res = send2DNCCommand({"action":"StopProgram"})
    if 'Status' in res:
        msg = '加工程序停止'
    elif 'Exeption' in res:
        msg = '停止加工程序失败, 详细信息:\n' + str(res['Exception'])
    return {'msg':msg}


def cancelCMD(a):
    res = send2DNCCommand({"action":"CancelProgram"})
    if 'Status' in res:
        msg = '取消选中的程序成功'
    elif 'Exeption' in res:
        msg = '取消选中的程序失败, 详细信息:\n' + str(res['Exception'])
    return {'msg':msg}

# def maininfo(m):
#     res = os.popen('%sDNCCommand.exe  "GetOverride"  "1"'%(tqdir))
#     info = res.read()
#     s = info.split('\n')
#     s = s[:-1]
#     return {'MainInfo':s}

def axisinfo(m):
    res = send2DNCCommand({"action":"GetOverride"})
    dataList = list()
    if 'Status' in res:
        data = json.loads(res['Status'])
        dataList.append('GetOverride: ')
        for i in data:
            dataList.append(i + ': ' + data[i])
    elif 'Exeption' in res:
        dataList = ['GetOverride: ', 'feed: 0', 'speed: 0', 'rapid: 0']
    return {'AxisInfo': dataList}


def maininfo(m):
    res = send2DNCCommand({"action":"GetCutterLocation"})
    dataDict = dict()
    if 'Status' in res:
        data = json.loads(res['Status'])
        for axisInfo in data: # fieldNameList = ['bstrCoordinateName', 'dPosition', 'bIsInch']
            dataDict[axisInfo.get('bstrCoordinateName')] = axisInfo['dPosition']
    elif 'Exeption' in res:
        dataDict = {'X': '0','Y': '0','Z': '0','C': '0','a': '0','A': '0','B': '0','b': '0','x': '0'}
    return {'MainInfo': dataDict}


def readStatus(a):
    global trayStatus
    sts = trayStatus
    b_old = {' ': '=1', ':': '=2', '[': '=3', ']': '=4', '{': '=5', '}': '=6', ',': '=7', '"': '=8', "'": '=9'}
    b_new = dict([k, v] for [v, k] in b_old.items())
    for i in b_new.keys():
        sts = sts.replace(i, b_new[i])
    std = eval(sts)
    res_axisinfo = axisinfo('default')
    res_maininfo = maininfo('default')
    std['主轴坐标'] = res_axisinfo['AxisInfo']
    std['主轴其他信息'] = res_maininfo['MainInfo']
    std['data'] = None

    # extend status with rfidBindindMessage
    for trayNum in rfidBindindDict:
        try:
            if rfidBindindDict[trayNum]:
                std[trayNum][3] = rfidBindindDict[i]
            else:
                std[trayNum][3] = 'noDataAvailable'
        except Exception:
            raise
    return {'机床状态': std}

def writeStatus(a):
    global setPoint
    setPoint = a
    print(setPoint)
    return {'本次写入 ': setPoint}

def setonline(a):
    if a == 'online':
        try:
            writeStatus('activated')
            return {'status writen': 'activated'}
        except Exception:
            return {'status writen': 'something went wrong'}    
    if a == 'offline':
        try:
            writeStatus('deactivated')
            return {'status writen': 'deactivated'}
        except Exception:
            return {'status writen': 'something went wrong'}
    else:
        return {'result': 'wrong command'}   
    

def getStatus(a):
    global trayStatus
    trayStatus = a
    # print('>>>  更新了状态： ', trayStatus)
    return {'trayStatus': trayStatus}

def setStatus(a):
    global setPoint
    global onlineSignal
    global hermleConnectedSignal
    temp = setPoint
    setPoint = 'stop'
    hermleConnectedSignal = '1'
    if temp == 'activated':
        onlineSignal = 'True'
    if temp == 'deactivated':
        onlineSignal = 'False'
    
    print('>>>>>>   in setStatus')
    return {'setPoint': temp}

def enableTaskflow(a):
    global workingstep
    global orderlist
    global loggingstep
    global serveractive
    orderlist = a
    print('>>>>>    in task flowenable', a)
    serveractive = '3'
    workingstep = '1'
    loggingstep = False
    return {'workingstep': workingstep}


def readworkingstep(a):
    global workingstep
    return {'workingstep':workingstep}

def clearworking(a):
    global workingstep
    workingstep = '0'
    return {'workingstep': '0'}

def orderList(a):
    return {'orderlist':orderlist}


def rabbitmsg(a):
    try:
        sendCMD(rootserverIP, port_rabbit, functionname='timetomodel', msg= a)
    except Exception:
        print('time消息传输失败')
    return {'timemsg':'receivemsg'}


def taskover(a):
    global serveractive
    a['resouce'] = 'hermle01'
    try:
        sendCMD(rootserverIP,port_dispatchServer,functionname='changstatustodone', msg= a )
    except Exception:
        print('rootserver传输失败')
    else:
        serveractive = '1'
        clearworking('')
    return {'taskover':'sendmsg'}


def serveronline(a):
    global serveractive
    serveractive = '1'
    return {'serveronline':'success'}


def serveroffline(a):
    global serveractive
    serveractive = '0'
    return {'serveroffline':'success'}


def serverstatus(a):
    global serveractive
    return {'serverstatus':serveractive}


def getorder(ip, port):
    global orderlist
    global serveractive
    print(serveractive)
    while True:
        if serveractive == '1':
            try:
                ordmsg = sendCMD(rootserverIP, port_dispatchServer, functionname='hermledispatch', msg= 'hermle01')
                print(ordmsg)
            except Exception:
                print('获取工单失败')
            else:
                if ordmsg['getorder']:
                    orderlist = ordmsg['getorder']
                    serveractive = '2'
                    print('serveractive')
        elif serveractive == '2':
            try:
                ordstat = sendCMD(rootserverIP, port_dispatchServer, functionname='doingorderstatus', msg= 'hermle01')
            except Exception:
                print('与根服务通讯失败')
            else:
                if ordstat['orderstatus']['status'] == '已就位':
                    print(ordstat['orderstatus']['status'])
                    enableTaskflow(orderlist)
                    serveractive = '3'
        time.sleep(1)




def startzmqServer(ip, port): 
# ip = '172.16.45.199'
# port = '5000'
    if __name__ == "__main__":
        # 处理程序参数
        if len(sys.argv) > 1:
            opts, args = getopt.getopt(sys.argv[1:], "hp:", ["help", "port="])
            for op, value in opts:
                if op in ("-p", "--port"):
                    serverPort = value
                elif op in ("-h", "--help"):
                    print(serverHelpDoc)
                    exit(0)
                else:
                    print("服务模型参数错误：", op, ' = ', value)
                    exit(0)

        # 注册函数
        serverFunctions['Register'] = (register, '显示服务注册信息')
        serverFunctions['changeToManual'] = (changeToManual, '切换为手动模式')
        serverFunctions['changeToAutomatic'] = (changeToAutomatic, '切换为自动模式')
        serverFunctions['downloadFiles'] = (downloadFiles, '下载指定文件')
        serverFunctions['receiveFiles'] = (receiveFiles, '接收指定文件')
        serverFunctions['deleteFiles'] = (deleteFiles, '删除指定文件')
        serverFunctions['selectFile'] = (selectFile, '选中指定加工程序')
        serverFunctions['startCMD'] = (startCMD, '开始执行选中的加工程序')
        serverFunctions['stopCMD'] = (stopCMD, '停止执行当前加工程序') # 但正在加工的动作不停止，直到加工完成后才停止。该命令只负责让加工程序不再被调用。
        serverFunctions['cancelCMD'] = (cancelCMD, '取消选中的加工程序') # 需要先Stop，再Cancel，否则报错。
        serverFunctions['writeStatus'] = (writeStatus, '向机床发出动作指令')
        serverFunctions['readStatus'] = (readStatus, '读取机床当前状态')
        serverFunctions['startTaskflow']= (enableTaskflow, '启动Taskflow')
        serverFunctions['orderlist'] = (orderList, '派工单')
        serverFunctions['axisinfo'] = (axisinfo, '读取主轴信息')
        serverFunctions['readworkingstep'] =(readworkingstep,'读使能信号')
        serverFunctions['clearworking'] = (clearworking,'初始化使能信号')
        serverFunctions['setonline'] = (setonline, '智能产线上线')
        serverFunctions['setLoggingStep'] = (setLoggingStep, 'set False')
        serverFunctions['rabbitmsg'] = (rabbitmsg, '向MES发送rabbitmq消息')
        serverFunctions['taskover'] = (taskover, '向rootserver发送完工消息')
        serverFunctions['serveronline'] = (serveronline, '服务器上线')
        serverFunctions['serveroffline'] = (serveroffline, '服务器下线')
        serverFunctions['serverstatus'] = (serverstatus, '读取服务器情况')
        serverFunctions['bindRFID'] = (bindRFID, '绑定RFID到托盘信息')

        otherFunctions['getStatus'] = (getStatus, '机床发来状态')
        otherFunctions['setStatus'] = (setStatus, '机床更新自身状态')

        context = zmq.Context()
        zmqSocket = context.socket(zmq.REP)
        serverURL = 'tcp://' + ip + ':' + port
        print("serverURL= ", serverURL)
        zmqSocket.bind(serverURL)
        serverRun = True

        serveronline('')

        while serverRun:
        #        message = json.loads(zmqSocket.recv())
            message = zmqSocket.recv_json()
            print('received request: ', message)
            if 'serverQuit' in message.keys():
                if message['serverQuit'] == 'qqq':
                    serverRun = False
            a = {'answer': '来自哈默机床', 'replyType': 'Normal'}
            for k in message.keys():
                if k in serverFunctions.keys():
                    a.update(serverFunctions[k][0](message[k]))
                elif k in otherFunctions.keys():
                    a.update(otherFunctions[k][0](message[k]))
                else:
                    a[k] = message[k]

            time.sleep(0.1)
            zmqSocket.send_string(json.dumps(a), flags=0, encoding='utf-8')

t1 = threading.Thread(target=startzmqServer, args=(serverIP, serverPort1)) # 被web2py call
t2 = threading.Thread(target=startzmqServer, args=(serverIP, serverPort2)) # 运行taskflow
t3 = threading.Thread(target=statusPut) # 发送状态到root
t4 = threading.Thread(target=getorder, args=(serverIP, serverPort3)) # 运行taskflow
t5 = threading.Thread(target=updateConnectionError) # connection error between hermle and pic

t1.start()
print('-------------------------------------------------------------------------')
# t2.start()
print('------------------------ t3 start now -----------------------------------')
t3.start()
# print('after 3')
print('-------------------------------------------------------------------------')
t4.start()
# t5.start()

