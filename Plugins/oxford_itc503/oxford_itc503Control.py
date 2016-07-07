#! /usr/bin/env python3.3

import itc503Master

import datetime
import Queue

class oxford_itc503Control(object):
    """
    Connection function between pressureMaster and slowControl
    Can not run on its own, use python pressureMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        self.__name = 'oxford_itc503'
        self.logger = opts.logger
        self.queue=opts.queue
        self.oxford_itc503_master = itc503Master.itc503Master(opts, self.logger)
        itc503Master.ReadoutThread.ReadOutT = self.queued_ReadOutT #Redefine ReadOutT

    def oxford_itc503control(self):
        '''
        Starts itc503 Master
        '''
        self.oxford_itc503_master.itc503master()

    def queued_ReadOutT(self):
        '''
        Redefines readout. Compare to itc503Master ReadOutT. Sends data to queue instead of file. 
        '''
        self.logger.debug("Reading data for log...")
        now = datetime.datetime.now()
       
        #collect data
        data = [self.oxford_itc503_master.controller.get_temperature(1),self.oxford_itc503_master.controller.get_temperature(2), self.oxford_itc503_master.controller.get_temperature(3), self.oxford_itc503_master.controller.get_heater_load(True)]
        status = [str(self.oxford_itc503_master.controller.get_alarm_status(1)),str(self.oxford_itc503_master.controller.get_alarm_status(2)),str(self.oxford_itc503_master.controller.get_alarm_status(3)),str(self.oxford_itc503_master.controller.get_alarm_status(0))]
        readout = str("| %s | %s | %s | %s | %s | %s | %s | %s | %s |"%(now.strftime('%Y-%m-%d | %H:%M:%S'), str(data[0]), str(data[1]), str(data[2]),str(data[3]),str(status[0]),str(status[1]),str(status[2]),str(status[3])))
        self.logger.info("Logged string: %s"%readout)

        #convert data to float
        for ii in range(len(data)):
            try:
                data[ii] = float(data[ii])
            except Exception as e:
                self.logger.warning("Cold not convert data to float: %s"%e)
                data[ii] = 0
                status[ii] = 3

        for ii in range(len(data)):
            if data[ii] == -1 or '':
                status[ii] = -1
            elif status[ii] == 0:
                status[ii] = 0
            elif status[ii] == -1:
                status[ii] = 1
            elif status[ii] == -2:
                status[ii] = 2
            else:
                status[ii] = 3

        # Put to queue
        try:
            self.queue.put([self.__name,now,data,status])
            self.logger.debug("oxford itc503 sucessfully put data to queue")
        except Exception as e:
            self.logger.warning("Can not put data to queue. Error: %s"%str(e))

    def __exit__(self):
        self.oxford_itc503_master.__exit__()
