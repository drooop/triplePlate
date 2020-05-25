# -*- coding: utf-8 -*-
import os
import sys
import time
import datetime
import platform
import traceback

import zmq
import sys
import json

import taskflow.engines
from taskflow.patterns import linear_flow as linearflow
from taskflow import task

import snap7
import struct

#-----------------------------------------------------------------------------------------------
from tqlib.configs.tq_logging_settings_kafka import *
# 
#-----------------------------------------------------------------------------------------------
orderlist = {}
# ip = '172.16.45.197'
localZMQIp = '172.16.45.199'
# rootServerIP = '172.16.31.30'
rootServerIP = '10.3.1.201'
port1 = '5020'
port2 = '5021'
port_update2server = '5071'
# ----------------------------------------------------------------------------------------------
tqdata1 = bytearray(b'\x01') # 置"1"
tqdata0 = bytearray(b'\x00') # 置"0"
plcIP = '172.16.45.218'
reck = 0
slot = 1

#--------------------------------------------------------------------------------
def getTime():
    return  time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
#--------------------------------------------------------------------------------
#
def tqlogger(mid, message, step, status='default'):
    tqloginfo = {'mid': '',
                'data': {
                    'workcentre': 'hermle01',
                    'step': '',
                    'status': '',
                    'message': '' 
                        }
                }
    if type(mid) == type(str()):
        if len(mid) == 36:
            tqloginfo['mid'] = mid
    else:
        return
    if type(message) == type(str()) and type(message) == type(str()):
        tqloginfo['data']['message'] = message
        tqloginfo['data']['step'] = step
    else:
        return
    tqloginfo['data']['status'] = status
    try:
        TQlogger.info(json.dumps(tqloginfo, ensure_ascii=False))
    except Exception:
        pass
    return {'res': True}


# ----------------------------------------------------------------------------------------------

def sendCMD(ip=localZMQIp,port=port1,funcname='', filename='default'):
    print('>>>>  in sendCMD', 'funcname', funcname, 'msg', filename)
    context = zmq.Context()
    zmqSocket = context.socket(zmq.REQ)
    # zmqSocket.connect("tcp://172.16.45.199:5000")
    zmqSocket.connect("tcp://" + ip + ":" + port)
    zmqData = {funcname:filename}
    zmqSocket.send_string(json.dumps(zmqData), flags=0, encoding='utf-8')
    zmqResponse = zmqSocket.recv_json()
    return zmqResponse

def send2Root(ip, port, funcname, msg=''):
    context = zmq.Context()
    zmqSocket = context.socket(zmq.REQ)
    # zmqSocket.connect("tcp://172.16.45.199:5000")
    zmqSocket.connect("tcp://" + ip + ":" + port1)
    zmqData = {funcname:msg}
    zmqSocket.send_string(json.dumps(zmqData), flags=0, encoding='utf-8')
    zmqResponse = zmqSocket.recv_json()
    return zmqResponse


def valvemotion(n):
    conn = snap7.client.Client()
    conn.connect(plcIP, reck, slot)
    if n == '11':
        conn.write_area(area=0x83, dbnumber=0, start=4, data=tqdata1)
    elif n == '10':
        conn.write_area(area=0x83, dbnumber=0, start=4, data=tqdata0)
        conn.write_area(area=0x83, dbnumber=0, start=2, data=tqdata1) 
        conn.write_area(area=0x83, dbnumber=0, start=2, data=tqdata0)
    elif n == '21':
        conn.write_area(area=0x83, dbnumber=0, start=5, data=tqdata1)
    elif n == '20':
        conn.write_area(area=0x83, dbnumber=0, start=5, data=tqdata0)
        conn.write_area(area=0x83, dbnumber=0, start=2, data=tqdata1) 
        conn.write_area(area=0x83, dbnumber=0, start=2, data=tqdata0)
    elif n == 'read':
        res = conn.read_area(area=0x83, dbnumber=1, start=2, size=6)
        res1 = struct.unpack('6?',res)
        conn.disconnect()
        conn.destroy()
        return {'shelfStatus': res1}
    else:
        conn.write_area(area=0x83, dbnumber=0, start=3, data=tqdata1)
        conn.write_area(area=0x83, dbnumber=0, start=3, data=tqdata0)
    conn.disconnect()
    conn.destroy()
    return n

class WaitWorkingsheet(task.Task):
    
    def execute(self):
        while True:
            res = sendCMD(ip=localZMQIp,port=port1,funcname='readworkingstep',filename='default')
            print('>>>> ', res)
            if res['workingstep'] == '1':
                break
            time.sleep(1)
            

class local_recieve_orderList(task.Task):

    def execute(self, filename='default', *args, **kwargs):
        global orderlist
        res = sendCMD(funcname='orderlist')
        orderlist = res['orderlist']
        # actionfile = {'11BBH1400200':'11BBH1400200_TEST-2.H'}
        actionfile = {'program':orderlist['program']}
        orderlist['actionfile'] = actionfile
        print('>> 取到的工单：', res)
        orderlist['orderstatus'] = 'START'
        orderlist['starttime'] = getTime()
        timemsg = {'orderkey':orderlist['orderkey'],'pValue': orderlist['step'] + '开始加工','orderstatus':orderlist['orderstatus'],'data':{'机床开始加工':{'pName':'机床开始加工','pType':'datetime','pValue':orderlist['starttime'],'pDescription':orderlist['step']}}}
        try:
            tqlogger(orderlist['orderkey'], '已经获取到工单信息', orderlist['step'])
        except Exception:
            pass
        try:
            res = sendCMD(funcname='rabbitmsg',filename = timemsg)
        except Exception:
            pass
        return


class MT_bindPlate(task.Task):

    def execute(self):
        global orderlist
        print('正在获取托盘信息......')
        
        # TQlogger.info('正在获取托盘信息...')
        try:
            tqlogger(orderlist['orderkey'], '正在获取托盘信息...', orderlist['step'])
        except Exception:
            pass
        status = sendCMD(funcname='readStatus')
        sendCMD(funcname='uploadStatus', ip=rootServerIP, port=port_update2server, filename={'deviceName': 'hermle01', 'data': status['机床状态']})
        plateStatus = {}
        plateStatus['1'] = status['机床状态']['1'][1:]
        plateStatus['2'] = status['机床状态']['2'][1:]
        plateStatus['3'] = status['机床状态']['3'][1:]
        for k,v in plateStatus.items():
            if v[0] == 1101: # paltePosition is  int
                spot_1101 = k
        orderlist['spot_1101'] = spot_1101 # plateNumber is string
        print('托盘信息已绑定。托盘号为: ', spot_1101)
        try:
            tqlogger(orderlist['orderkey'], '托盘信息已绑定，托盘号为: "%s"'%(spot_1101), orderlist['step'])
        except Exception:
            pass
        # TQlogger.info('托盘信息已绑定。托盘号为: ' + spot_1101)


class MT_changeToAutomatic(task.Task):

    def execute(self, *args, **kwargs):
        while True:
            res = sendCMD(funcname=tqfDict['f_changeToAutomatic'])
            print(res)
            if res['msg'] == '切换自动模式成功':
                try:
                    tqlogger(orderlist['orderkey'], '切换自动模式成功', orderlist['step'])
                except Exception:
                    pass
                # TQlogger.info('')
                break
            time.sleep(1.5)


class MT_downloadFiles(task.Task):

    def execute(self, *args, **kwargs):
        res = sendCMD(funcname=tqfDict['f_downloadFiles'], filename=orderlist['actionfile']['program'])
        print(res)
        try:
            tqlogger(orderlist['orderkey'], '加工文件下载完成', orderlist['step'])
        except Exception:
            pass
        # TQlogger.info('加工文件下载完成 ：' + orderlist['actionfile']['program'])
        time.sleep(1)


class MT_selectFile(task.Task):

    def execute(self, *args, **kwargs):
        doneSignal = True
        while doneSignal:
            res = sendCMD(funcname=tqfDict['f_selectFile'], filename=orderlist['actionfile']['program'])
            if res.get('msg') == '下载加工文件成功':
                doneSignal = False
            else:
                time.sleep(1)
        try:
            tqlogger(orderlist['orderkey'], '已经选择指定加工文件', orderlist['step'])
        except Exception:
            pass
        # TQlogger.info('已经选择制定加工文件：' + orderlist['actionfile']['program'])
        time.sleep(1)


class MT_preStart(task.Task):

    def execute(self):
        plateNum = orderlist['spot_1101']
        print('马上结束加工准备工作')
        # TQlogger.info('马上结束加工准备工作')
        try:
            tqlogger(orderlist['orderkey'], '即将结束加工准备工作', orderlist['step'])
        except Exception:
            pass
        while True:
            sendCMD(funcname=tqfDict['f_writeStatus'], filename='80'+ plateNum + '1')
            # time.sleep(1.5)
            status = sendCMD(funcname='readStatus')
            print('>>>>    status in preStart : ', status['机床状态'][plateNum][2])
            sendCMD(funcname='uploadStatus', ip=rootServerIP, port=port_update2server, filename={'deviceName': 'hermle01', 'data': status['机床状态']})
            if status['机床状态'][plateNum][2] == 'Rohteil':
                time.sleep(0.5)
                print('加工准备完成')
                try:
                    tqlogger(orderlist['orderkey'], '加工准备完成', orderlist['step'])
                except Exception:
                    pass
                # TQlogger.info('加工准备完成')
                break


class MT_sendPlate(task.Task):

    def execute(self):
        plateNum = orderlist['spot_1101']
        print('开始将托盘送入加工区')
        try:
            tqlogger(orderlist['orderkey'], '收到将托盘送入加工区域命令', orderlist['step'])
        except Exception:
            pass
        # TQlogger.info('开始将托盘送入加工区')
        while True:
            status = sendCMD(funcname='readStatus')
            sendCMD(funcname='uploadStatus', ip=rootServerIP, port=port_update2server, filename={'deviceName': 'hermle01', 'data': status['机床状态']})
            print('>>>>    platePosition : ', status['机床状态'][plateNum][1])
            if status['机床状态'][plateNum][1] != 1101:
                print('待加工零件已经在路上')
                try:
                    tqlogger(orderlist['orderkey'], '待加工零件正在递送加工区域中', orderlist['step'])
                except Exception:
                    pass
                # TQlogger.info('待加工零件已经在路上')
                break
            else:
                time.sleep(2)
                sendCMD(funcname='writeStatus', filename=('sendPlate' + plateNum))     


class MT_readytoStart(task.Task):

    def execute(self):
        plateNum = orderlist['spot_1101']
        while True:
            status = sendCMD(funcname='readStatus')
            sendCMD(funcname='uploadStatus', ip=rootServerIP, port=port_update2server, filename={'deviceName': 'hermle01', 'data': status['机床状态']})
            print('>>>>    not in position yet...', status['机床状态'][plateNum][1])
            if status['机床状态'][plateNum][1] == 5101:                
                print('加工条件满足，准备加工')
                try:
                    tqlogger(orderlist['orderkey'], '加工条件满足，准备加工', orderlist['step'])
                except Exception:
                    pass
                # TQlogger.info('加工条件满足，准备加工')
                # time.sleep(5)
                if status['机床状态'].get('Arbeitsraum') == 'rot':
                    time.sleep(2.5)
                    break


class MT_startPrograme(task.Task):

    def execute(self):
        print('正在发送加工命令')
        try:
            tqlogger(orderlist['orderkey'], '加工命令已发送', orderlist['step'])
        except Exception:
            pass
        # TQlogger.info('正在发送加工命令')
        sendCMD(funcname='startCMD', filename=orderlist['actionfile']['program'])


class MT_startchecked(task.Task):

    def execute(self):
        plateNum = orderlist['spot_1101']
        while True:
            sendCMD(funcname=tqfDict['f_writeStatus'], filename='80'+ plateNum + '2')
            status = sendCMD(funcname='readStatus')
            sendCMD(funcname='uploadStatus', ip=rootServerIP, port=port_update2server, filename={'deviceName': 'hermle01', 'data': status['机床状态']})
            print('>>>>    status in if mechining : ', status['机床状态'][plateNum][2])
            if status['机床状态'][plateNum][2] == 'Teilbearbeitet':
                print('现在开始加工了')
                try:
                    tqlogger(orderlist['orderkey'], '加工开始了', orderlist['step'])
                except Exception:
                    pass
                # TQlogger.info('开始加工')
                break



class MT_readytoGetout(task.Task):
    
    def execute(self):
        plateNum = orderlist['spot_1101']
        while True:
            status = sendCMD(funcname= 'readStatus')
            sendCMD(funcname='uploadStatus', ip=rootServerIP, port=port_update2server, filename={'deviceName': 'hermle01', 'data': status['机床状态']})
            print('>>>>    check if ready to getout', status['机床状态'][plateNum][2])
            if status['机床状态'][plateNum][2] == 'Fertigteil':
                print('零件已经加工完成')
                try:
                    tqlogger(orderlist['orderkey'], '零件已经加工完成了', orderlist['step'])
                except Exception:
                    pass
                # TQlogger.info('零件已经加工完成')
                break


class MT_getPlate(task.Task):

    def execute(self):
        plateNum = orderlist['spot_1101']
        print('准备取出零件')
        #TQlogger.info('准备取出零件')
        tqlogger(orderlist['orderkey'], '准备取出零件', orderlist['step'])
        while True:
            print('正在等待响应')
            status = sendCMD(funcname='readStatus')
            print('>>>>    status in getPlate : ', status['机床状态'][plateNum][1])
            sendCMD(funcname='uploadStatus', ip=rootServerIP, port=port_update2server, filename={'deviceName': 'hermle01', 'data': status['机床状态']})
            if status['机床状态'][plateNum][1] != 5101:
                print('零件在路上了')
                try:
                    tqlogger(orderlist['orderkey'], '零件正送往上料区', orderlist['step'])
                except Exception:
                    pass
                # TQlogger.info('零件在路上了')
                break
            else:
                sendCMD(funcname='writeStatus', filename=('getPlate' + plateNum))
                # time.sleep(1.5)


class MT_ifGetout(task.Task):

    def execute(self):
        plateNum = orderlist['spot_1101']
        while True:
            status = sendCMD(funcname='readStatus')
            print('>>>>    status in getPlate : ', status['机床状态'][plateNum][1])
            sendCMD(funcname='uploadStatus', ip=rootServerIP, port=port_update2server, filename={'deviceName': 'hermle01', 'data': status['机床状态']})
            if status['机床状态'][plateNum][1] == 1101:
                print('零件已送出，等待iiwa抓取...')
                try:
                    tqlogger(orderlist['orderkey'], '零件已经送出，等待iiwa抓取', orderlist['step'])
                except Exception:
                    pass
                # TQlogger.info('零件已送出，等待iiwa抓取')
                break


class GiveBackLoggingStep(task.Task):

    def execute(self, *args, **kwargs):
        sendCMD(funcname='setLoggingStep', ip=localZMQIp, port=port1, filename='True')


class MT_taskOver(task.Task):

    def execute(self, *args, **kwargs):
        global orderlist
        orderlist['哈默加工'] = '哈默加工完成啦！！！'
        if orderlist['processing'] == '毛坯加工':
            orderlist['orderstatus'] = 'SUSPEND'
            orderlist['completedtime'] = getTime()
        else:
            orderlist['orderstatus'] = 'COMPLETED'
            orderlist['completedtime'] = getTime()
        timemsg = {'orderkey':orderlist['orderkey'],'pValue': orderlist['step'] +'完成','orderstatus':orderlist['orderstatus'],'data':{'机床完成加工':{'pName':'机床完成加工','pType':'datetime','pValue':orderlist['completedtime'],'pDescription':orderlist['step']},'加工机床':{'pName':'加工机床','pType':'string','pValue':'Hermle01','pDescription':'加工机床'},'加工台面':{'pName':'加工台面','pType':'string','pValue':orderlist['spot_1101'],'pDescription':'加工台面'}}}
        sendCMD(funcname='rabbitmsg',filename = timemsg)
        sendCMD(funcname='taskover',filename = orderlist)
        # orderList['on_plate'] = 
        # TQlogger.info('MT Response Code: {}'.format(status_code))


if __name__ == "__main__":
    tqfDict = {}
    tqfDict['f_readStatus'] = 'readStatus'
    
    tqfDict['f_writeStatus'] = 'writeStatus'
    tqfDict['f_changeToManual'] = 'changeToManual'
    tqfDict['f_downloadFiles'] = 'downloadFiles'
    tqfDict['f_changeToAutomatic'] = 'changeToAutomatic'
    tqfDict['f_selectFile'] = 'selectFile'
    tqfDict['f_startCMD'] = 'startCMD'

    # orderList = {}
    # orderList['mid'] = 'asdfghjklqwertyuiopasdfghjklzxcvbnm'
    # orderList['mechining_filename'] = 'TEST.H'
    # orderList['testing_filename'] = 'test1.PRG'
    flow = linearflow.Flow('simple-linear-listen-websites-fetch').add(
                                                        WaitWorkingsheet(),
                                                        local_recieve_orderList(),
                                                        MT_bindPlate(),
                                                        MT_downloadFiles(),
                                                        MT_changeToAutomatic(),
                                                        MT_selectFile(),
                                                        MT_preStart(),
                                                        MT_sendPlate(),
                                                        MT_readytoStart(),
                                                        MT_startPrograme(),
                                                        MT_startchecked(),
                                                        MT_readytoGetout(),
                                                        MT_getPlate(),
                                                        MT_ifGetout(),
                                                        GiveBackLoggingStep(),
                                                        MT_taskOver()

                                                    )

while True:
    engine = taskflow.engines.load(flow, store=dict())
    engine.run()

    