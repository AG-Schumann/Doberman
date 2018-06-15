#! /usr/bin/env python3.3

import pressureMaster
import queue
import datetime

class PfeifferGaugeControl(object):
    """
    Connection function between pressureMaster and slowControl
    Can not run on its own, use python pressureMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        self.__name = 'PfeifferGauge'
        self.logger = opts.logger
        self.queue = opts.queue

        self.PfeifferGauge_master = pressureMaster.pressureMaster(opts, self.logger)
        pressureMaster.ReadoutThread.ReadOutT = self.queued_ReadOutT #Redefine ReadOutT

    def PfeifferGaugecontrol(self):
        self.PfeifferGauge_master.pressuremaster()

    def queued_ReadOutT(self):
        '''
        Redefines readout. Compare to cryoMaster ReadOutT. Sends data to queue instead of file. 
        '''
        self.logger.debug("Reading data for log...")
        pressure = self.PfeifferGauge_master.controller.getPressureData()
        now = datetime.datetime.now()
        if pressure != -1:
            try:
                status = int(pressure[0])
                data = float(pressure[1])
                # Changing status to correct format
                if pressure[0] in [1, 2]:
                    status = 1
                elif pressure[0] in [3, 4, 5]:
                    status = 2
                    data = 0
                elif pressure[0] == [6]:
                    status = 3
                    data = 0
            except TypeError as e:
                self.logger.warning("No data collected. Error %s."%e)
                data = pressure
                status = -1
            except Exception as e:
                self.logger.warning("Can not change status of measurement %s to correct format. Error %s. Setting data=0 status=3."%(str(pressure),e))
                data = 0
                status = 3
        elif pressure == -1:  
            self.logger.warning("No data collected")
            status = -1
            data = 0

        # Put to queue
        try:
            self.queue.put([self.__name,now,[data],[status]])
            self.logger.debug("Pfeiffer Gauge sucessfully put data to queue (%s, %s, %s, %s)"%(self.__name,str(now),str([data]),str([status])))
        except Exception as e:
            self.logger.warning("Can not put data to queue. Error: %s"%str(e))

    def __exit__(self):
        self.PfeifferGauge_master.__exit__()

if __name__ == '__main__':
    import logging

    logging.basicConfig()
    logger = logging.getLogger()
    logger.setLevel(10)
    
    queue = queue.Queue()


    opts = type('Test', (object,), {})  
    opts.queue = queue
    opts.logger = logger

    PGC = PfeifferGaugeControl(opts)
    
