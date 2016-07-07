#! /usr/bin/env python3.3

import TemperNTCMaster

import datetime
import Queue

class TemperNTCControl(object):
    """
    Connection function between TemperNTC and slowControl
    Can not run on its own, use python TemperNTCMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        self.__name = 'TemperNTC'
        self.logger = opts.logger
        self.queue=opts.queue
        self.TemperNTC_master = TemperNTCMaster.TemperNTCMaster(opts, self.logger)
        TemperNTCMaster.ReadoutThread.ReadOutT = self.queued_ReadOutT #Redefine ReadOutT

    def TemperNTCcontrol(self):
        '''
        Starts cryo Master
        '''
        self.TemperNTC_master.TemperNTCMaster()

    def queued_ReadOutT(self):
        '''
        Redefines readout. Compare to cryoMaster ReadOutT. Sends data to queue instead of file. 
        '''
        self.logger.debug("Reading data for log...")
        now = datetime.datetime.now()
       
        #collect data
        data = [self.TemperNTC_master.get_internal_temperature(), self.TemperNTC_master.get_external_temperature()]
        status = [str(self.TemperNTC_master.check_internal_alarm()),str(self.TemperNTC_master.check_external_alarm())]
        readout = str("| %s | %s | %s | %s | %s |"%(now.strftime('%Y-%m-%d | %H:%M:%S'),data[0],data[1],status[0],status[1]))
        self.logger.info("Logged string: %s"%readout)

        #convert data to float
        for ii in range(len(data)):
            try:
                data[ii] = float(data[ii])
            except Exception as e:
                self.logger.warning("Cold not convert data to float: %s"%e)
                data[ii] = 0
                status[ii] = -5

        for ii in range(len(data)):
            if data[ii] == -1 or '':
                status[ii] = -1
            elif status[ii] == 0:
                status[ii] = 0
            elif status[ii] == -2:
                status[ii] = -2
            elif status[ii] == -3:
                status[ii] = -3
            else:
                status[ii] = -4

        # Put to queue
        try:
            self.queue.put([self.__name,now,data,status])
            self.logger.debug("TemperNTC sucessfully put data to queue")
        except Exception as e:
            self.logger.warning("Can not put data to queue. Error: %s"%str(e))

    def __exit__(self):
        self.TemperNTC_master.__exit__()
