#! /usr/bin/env python3.3

import cryoMaster

import datetime
import queue

class cryocon_22cControl(object):
    """
    Connection function between pressureMaster and slowControl
    Can not run on its own, use python pressureMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        self.__name = 'cryocon_22c'
        self.logger = opts.logger
        self.queue=opts.queue
        self.cryocon_22c_master = cryoMaster.cryoMaster(opts, self.logger)
        cryoMaster.ReadoutThread.ReadOutT = self.queued_ReadOutT #Redefine ReadOutT

    def cryocon_22ccontrol(self):
        '''
        Starts cryo Master
        '''
        self.cryocon_22c_master.cryomaster()

    def queued_ReadOutT(self):
        '''
        Redefines readout. Compare to cryoMaster ReadOutT. Sends data to queue instead of file. 
        '''
        self.logger.debug("Reading data for log...")
        now = datetime.datetime.now()
       
        #collect data
        data = [self.cryocon_22c_master.controller.getTemp('A'), self.cryocon_22c_master.controller.getTemp('B'), self.cryocon_22c_master.controller.getLoopPower('1'), self.cryocon_22c_master.controller.getLoopPowerOut('1'), self.cryocon_22c_master.controller.getSetPoint('1'), self.cryocon_22c_master.controller.getSetPoint('2')]
        status = [str(self.cryocon_22c_master.controller.getAlarmStatus('A')),str(self.cryocon_22c_master.controller.getAlarmStatus('B')),'--','--','--','--']
        readout = str("| %s | %s | %s | %s | %s | %s | %s | %s | %s |"%(now.strftime('%Y-%m-%d | %H:%M:%S'),data[0],data[1],str(data[2]),str(data[3]),str(data[4]),str(data[5]),status[0],status[1]))
        self.logger.info("Logged string: %s"%readout)

        #convert data to float
        for ii in range(len(data)):
            try:
                data[ii] = float(data[ii])
            except Exception as e:
                self.logger.warning("Cold not convert data to float: %s"%e)
                data[ii] = 0
                status[ii] = 3

        # Changing status to correct format
        for ii in range(len(data)):
            if data[ii] == -1 or data[ii] == '':
                status[ii] = -1
            elif status[ii] == '--':
                status[ii] = 0
            elif status[ii] == 'SF':
                status[ii] = 1
            elif status[ii] == 'HI' or 'LO':
                status[ii] = 2
            else:
                status[ii] = -2

        # Put to queue
        try:
            self.queue.put([self.__name,now,data,status])
            self.logger.debug("cryocon_22c sucessfully put data to queue")
        except Exception as e:
            self.logger.warning("Can not put data to queue. Error: %s"%str(e))

    def __exit__(self):
        self.cryocon_22c_master.__exit__()
