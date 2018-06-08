#! /usr/bin/env python3.3

import smartec_uti1Master
import smartec_uti1Config

import datetime
#import Queue


class smartec_uti1Control(object):
    """
    Connection function between utiMaster and slowControl
    Can not run on its own, use python utiMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        self.logger = opts.logger
        self.smartec_uti_master = smartec_uti1Master.smartec_uti1Master(opts, self.logger)

        self.__name = 'smartec_uti1'
        self.queue=opts.queue
        ### IF we are in a mode where we read not 1 but 3 external capacitances (mode 2 or mode 4) redefine ReadOutT:
        if smartec_uti1Config.mode in [2,4]:
            smartec_uti1Master.ReadoutThread.ReadOutT = self.queued_ReadOutT #Redefine ReadOutT


    def smartec_uti1control(self):
        self.smartec_uti_master.utimaster()

    def __exit__(self):
        self.smartec_uti_master.__exit__()


    def queued_ReadOutT(self):
        '''
        Redefines readout. Compare to cryoMaster ReadOutT. Sends data to queue instead of file. 
        '''
        self.logger.debug("Reading data for log...")
        now = datetime.datetime.now()

        #collect data
        data = self.smartec_uti_master.controller.measure() 
        #readout = str("| %s | %s | %s | %s | %s | %s | %s | %s | %s |"%(now.strftime('%Y-%m-%d | %H:%M:%S'),data[0],data[1],str(data[2]),str(data[3]),str(data[4]),str(data[5]),status[0],status[1]))
        #self.logger.info("Logged string: %s"%readout)

        #convert data to float
        for ii in range(len(data)):
            try:
                data[ii] = float(data[ii])
            except Exception as e:
                self.logger.warning("Cold not convert data to float: %s"%e)
                data[ii] = 0
                status[ii] = 3

        # Changing status to correct format
        status = []
        if len(data) != 3:
        # TODO: improve verbosity of status 
            status = [-1,-1,-1] 
        else:
            status = [1,1,1]
        # Put to queue
        try:
            self.queue.put([self.__name,now,data,status])
            self.logger.info("smartec_uti1 successfully put data to queue: '{}' '{}' '{}' '{}'".format(self.__name,now,data,status))
        except Exception as e:
            self.logger.warning("Can not put data to queue. Error: %s"%str(e))


