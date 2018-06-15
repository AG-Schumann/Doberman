#! /usr/bin/env python3.3

import os
import time
import datetime
import logging
from argparse import ArgumentParser
import pressureSerial
import pressureWriter
import threading
import sys

class pressureMaster(object):
    """
    Main function to controll the pressure TPG 61 controller.
    The function can be called with several options in the command line mode.
    It will start automatically a connection to the pressure controller on the choosen connection (LAN, serial, ...).
    It can run in interactive shells as well as a standalone python program (call via 'python pressureMaster.py -opts').
    """
    def __init__(self, opts, logger):

        self.logger = logger
        self.opts = opts
        self.controller = None
        self.controller = pressureSerial.pressureSerial(opts, logger)

        if self.controller is None:
            self.logger.fatal("Controller not initialized correctly")
            exit()

        self._lifes = 99999999999999999999999
        if hasattr(self.opts, 'log_path'):
            self.pressure_writer = pressureWriter.pressureWriter(logger, log_path = self.opts.log_path)
        else:
            self.pressure_writer = pressureWriter.pressureWriter(logger)
        
        if not opts.queue:
            self.logHead()

        self.writerThread = ReadoutThread(self.logger, self.opts, self.pressure_writer, self.controller)

    def pressuremaster(self):
        """
        This function starts the read out process from the controller.
        It opens a new thread and checks from time to time whether the thread is still alive, if not it reactivates it.
        """
        try:
            self.writerThread.start()
            runner = 0
            while runner < self._lifes:
                runner += 1
                self.logger.info("Main program still alive...")
                if runner%2 == 0:
                    if self.writerThread.stopped or not self.writerThread.isAlive():
                        self.logger.fatal("Logging thread died. Reviving...")
                        self.logger.debug("Logging thread died, writerThread.stopped = %s and writerThread.isAlive() = %s ."%(str(self.writerThread.stopped),str(self.writerThread.isAlive())))
                        self.writerThread = ReadoutThread(self.logger, self.opts, self.pressure_writer, self.controller) #test
                        self.writerThread.start()
                time.sleep(30)
            self.close()
        except KeyboardInterrupt:
            self.logger.fatal("\n\nProgram killed by ctrl-c\n\n")
            self.close()

    def logHead(self):
        """
        Defines the read out values and writes the logging file header header.
        """

        gaugecontrol = self.controller.getGaugeControl()
        swfunctionstat = self.controller.getSwFunctionStatus()        
        
        self.pressure_writer.write(str("Reading from pressure Controller TPG 261: The gauge type is %s "%(self.controller.getGaugeTyp())))     
        self.pressure_writer.write(str("The control of gauge 1 is set to %s for activation and %s for deactivation."%(gaugecontrol[0], gaugecontrol[1])))
        if gaugecontrol[0] == 'Automatic' or gaugecontrol[1] == 'Automatic':
            self.pressure_writer.write(str("The ON threshold is %s and the OFF treshold is %s"%(gaugecontrol[2],gaugecontrol[3])))
        #self.pressure_writer.write(str("The current pressure unit is: %s"%(self.__pressure_unit[int(self.controller.getPressureUnit())])))  
        #self.pressure_writer.write(str("The switchinung function statuses are: F1: %s, F2: %s, F3: %s, F4: %s"%(self.__on_off[swfunctionstat[0]],self.__on_off[swfunctionstat[1]],self.__on_off[swfunctionstat[2]],self.__on_off[swfunctionstat[3]])))  
        self.pressure_writer.write("^ date (Y-m-d) ^ time (H:M:S) ^ pressure (%s) ^ data status"%(self.controller.getPressureUnit()))
        return

    def close(self):
        self.logger.info("Closing the logger")
        self.writerThread.stopped = True
        self.writerThread.Tevent.set()
        self.pressure_writer.close()
        self.controller.close()
        return

    def __del__(self):
        self.close()
        return
    
    def __exit__(self):
        self.close()
        return

class ReadoutThread(threading.Thread):
    """
    Class that is the read out thread. Controlls the thread: starting, running and stopping it.
    """
    def __init__(self, logger, opts, writer, controller):

        self.ReadOutInterval = 30
        self.logger = logger
        self.opts = opts
        self.pressure_writer = writer
        self.controller = controller

        self.__measurement_status=['OK','Underrange','Overrange','Sensor Error','Sensor Off','No Sensor','ID Error',]

        if self.opts.loginterval < 1000 and self.opts.loginterval >= 5:
            self.ReadOutInterval = self.opts.loginterval
            self.logger.info("Readout interval set to %i s."%self.ReadOutInterval)
        else:
            self.logger.error("Required readout interval invalid. Running with default 30s.")

        self.stopped = False
        threading.Thread.__init__(self)
        self.Tevent = threading.Event()

    def run(self):
        while not self.stopped:
            self.ReadOutT()
            self.Tevent.wait(self.ReadOutInterval)

    def ReadOutT(self):
        """
        Read out thread itself. Defines the read out format.
        """
        self.logger.debug("Reading data for log...")
        pressure = self.controller.getPressureData()
        if pressure != -1:
            status = int(pressure[0])
            data = float(pressure[1])
        elif pressure == -1:
            pressure = ['No Data',0]        
            self.logger.warning("No data collected")
            status = -1
            data = 0

        if pressure[0] in [1, 2]:
            status = 1
        elif pressure[0] in [3, 4, 5]:
            status = 2
            data = 0
        elif pressure[0] == [6]:
            status = 3
            data = 0

        if not self.opts.queue: #if no queue it writes to the log file
            pressure[0] = str(self.__measurement_status[int(pressure[0])])
            readout = ("| %s | %s | %s |"%(now.strftime('%Y-%m-%d | %H:%M:%S'), str(pressure[1]),str(pressure[0])))
            self.pressure_writer.write(readout)
            self.logger.info("Can not write to database, write to log file: Logged string: %s"%readout)

if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to readout the pressure controller TPG 261')
    parser.add_argument("-d", "--debug", dest="loglevel", type=int, help="switch to loglevel debug", default=10)
    parser.add_argument("-i", "--interval", dest="loginterval", type=int, help="logging interval in s, default value: 30 s", default=30)
    opts = parser.parse_args()
    
    logger = logging.getLogger()
    if not opts.loglevel in [0,10,20,30,40,50]:
        print(("ERROR: Given log level %i not allowed. Fall back to default value of 10"%opts.loglevel))
    logger.setLevel(int(opts.loglevel))

    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)


    pressure_master = pressureMaster(opts, logger)
    pressure_master.pressuremaster()
    sys.exit(0)

