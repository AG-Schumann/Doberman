#! /usr/bin/env python3.3

import os
import time
import datetime
import logging
from argparse import ArgumentParser
import itc503Serial
import itc503Writer
import threading
import sys



class itc503Master(object):
    """
    Main function to controll the oxford itc 503 controller.
    The function can be called with several options in the command line mode.
    It will start automatically a connection to the itc503 controller on the serial connection.
    It can run in interactive shells as well as a standalone python program (call via 'python itc503Master.py -opts').
    """
    def __init__(self, opts, logger):

        self.logger = logger
        self.opts = opts
        self.controller = itc503Serial.itc503Serial(opts, logger)

        self._lifes = 99999999999999999999999
        if hasattr(self.opts, 'log_path'):
            self.itc503_writer = itc503Writer.itc503Writer(logger, log_path = self.opts.log_path)
        else:
            self.itc503_writer = itc503Writer.itc503Writer(logger)
        
        self.logHead()

        self.writerThread = ReadoutThread(self.logger, self.opts, self.itc503_writer, self)

    def itc503master(self):
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
        self.itc503_writer.write(str("# Read from itc503 controller with the type and firmware version: %s ."%self.controller.get_itc503version()))
        self.itc503_writer.write(str("Input sensors for heater: %s"%self.controller.get_heater_sensor()))
        self.itc503_writer.write(str("Temperature setpoint: %s"%self.controller.get_temperature(0)))
        self.itc503_writer.write(str("PID status: %s"%(self.controller.get_PID_status())))        
        self.itc503_writer.write(str("Controlling heater automatically: %s"%str(self.controller.get_auto_man_status()[0])))        
        self.itc503_writer.write(str("\n\n"))
        self.itc503_writer.write("^ date (Y-m-d) ^ time (H:M:S) ^ Temp 1 (K) ^ Temp 2 (K) ^ Temp 3 (K) ^ heater power (%) ^")
        return

    def close(self):
        self.logger.info("Closing the logger")
        self.writerThread.stopped = True
        self.writerThread.Tevent.set()
        self.itc503_writer.close()
        self.controller.close()
        loggerslist = list(self.logger.handlers)
        for lle in loggerslist:
            self.logger.removeHandler(lle)
            lle.flush()
            lle.close()
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
    def __init__(self, logger, opts, writer, master):

        self.ReadOutInterval = 20
        self.logger = logger
        self.opts = opts
        self.itc503_writer = writer
        self.itc503_master = master

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
            # Hack to get around the pretty slow readout of the oxford device (takes ages to read it)
            __counter = 0
            __waittime = self.ReadOutInterval
            while(__counter<10 and self.ReadOutInterval):
                __counter += 1
                __waittime -=1.
            self.Tevent.wait(__waittime)
#            self.Tevent.wait(self.ReadOutInterval)

    def ReadOutT(self):
        """
        Read out thread itself. Defines the read out format.
        """
        self.logger.debug("Reading data for log...")
        now = datetime.datetime.now()
        readout = str("| %s | %s | %s | %s | %s |"%(now.strftime('%Y-%m-%d | %H:%M:%S'),self.itc503_master.controller.get_temperature(1),self.itc503_master.controller.get_temperature(2), self.itc503_master.controller.get_temperature(3), self.itc503_master.controller.get_heater_load(True)))
        self.itc503_writer.write(readout)
        self.logger.info("Logged string: %s"%readout)


if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to readout the oxford itc503 controller')
    parser.add_argument("-d", "--debug", dest="loglevel", type=int, help="switch to loglevel debug", default=10)
    parser.add_argument("-i", "--interval", dest="loginterval", type=int, help="logging interval in s, default value: 30 s", default=30)
    parser.add_argument("-p", "--idproduct", dest="productID", type=str, help="ProductID. default: None", default='6001')
    parser.add_argument("-v", "--idvendor", dest="vendorID", type=str, help="VendorID. default: None", default="0403")
    opts = parser.parse_args()
    
    logger = logging.getLogger('slowcontrol.plugins.itc503masterlogger')
    if not opts.loglevel in [0,10,20,30,40,50]:
        print(("ERROR: Given log level %i not allowed. Fall back to default value of 10"%opts.loglevel))
    logger.setLevel(int(opts.loglevel))

    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)

    itc503_master = itc503Master(opts, logger)
    itc503_master.itc503master()
    sys.exit(0)
