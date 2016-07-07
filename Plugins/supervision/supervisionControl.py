#! /usr/bin/env python3.3

import supervisionMaster

import datetime
import Queue



class supervisionControl(object):
    """
    Connection function between supervisionMaster and slowControl
    Can not run on its own, use python supervisionMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        self.logger = opts.logger
        self.__name = 'supervision'
        self.queue=opts.queue
        opts.server_address = opts.addresses[1]
	    opts.server_port = int(opts.addresses[2])
	    opts.remote_address = opts.additional_parameters[0]
	    opts.remote_port = int(opts.additional_parameters[1])

        self.supervision_master = supervisionMaster.supervisionMaster(opts, self.logger)
        supervisionMaster.ReadoutThread.ReadOutT = self.queued_ReadOutT #Redefine ReadOutT

    def supervisioncontrol(self):
        self.supervision_master.supervisionmaster()

    def queued_ReadOutT(self):
        '''
        Redefines readout. Compare to supervisionMaster ReadOutT. Sends data to queue instead of file. 
        '''
        self.logger.debug("Reading data for log...")
        now = datetime.datetime.now()
       
        #collect data
        data = [self.supervision_master.super_vision_client.querry_online(), self.supervision_master.super_vision_client.querry_warning(), self.supervision_master.super_vision_client.querry_alarm()]
        status = [self.supervision_master.super_vision_server.status_online(),self.supervision_master.super_vision_server.status_warning(),self.supervision_master.super_vision_server.status_alarm()]
        readout = str("| %s | %i | %i | %i | %i | %i| %i |"%(now.strftime('%Y-%m-%d | %H:%M:%S'),str(data[0]),str(data[1]),str(data[2]),str(data[3]),str(status[0]),str(status[1]), str(status[2])))
        self.logger.info("Logged string: %s"%readout)

        #convert data to float
        for ii in range(len(data)):
            try:
                data[ii] = float(data[ii])
            except Exception as e:
                self.logger.warning("Cold not convert data to float: %s"%e)
                data[ii] = 0
                status[ii] = 3
        # Put to queue
        try:
            self.queue.put([self.__name,now,data,status])
            self.logger.debug("supervision sucessfully put data to queue")
        except Exception as e:
            self.logger.warning("Can not put data to queue. Error: %s"%str(e))

    def __exit__(self):
        self.supervision_master.__exit__()
