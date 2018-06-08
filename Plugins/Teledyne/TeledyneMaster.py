#! /usr/bin/env python3.3

import os
import time
import datetime
import logging
from argparse import ArgumentParser
import TeledyneSerial
import TeledyneWriter
import threading
import sys

class TeledyneMaster(object):
    """
    Main function to controll the flow controller Teledyne THCD-100.
    The function can be called with several options in the command line mode.
    It will start automatically a serial connection to the flow controller.
    It can run in interactive shells as well as a standalone python program (call via 'python TeledyneMaster.py -opts').
    """
    def __init__(self, opts, logger):

        self.logger = logger
        self.opts = opts
        self.controller = None
        self.controller = TeledyneSerial.TeledyneSerial(opts,logger)

        if self.controller is None:
            self.logger.fatal("Controller not initialized correctly")
            exit()

        self._lifes = 99999999999999999999999

        if hasattr(self.opts, 'log_path'):
            self.Teledyne_writer = TeledyneWriter.TeledyneWriter(logger, opts.queue, log_path = self.opts.log_path)
        else:
            self.Teledyne_writer = TeledyneWriter.TeledyneWriter(logger, opts.queue)
        
        if not opts.queue:
            self.logHead()

        self.writerThread = ReadoutThread(self.logger, self.opts, self.Teledyne_writer, self.controller)


    def Teledynemaster(self):
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
                        self.writerThread = ReadoutThread(self.logger, self.opts, self.Teledyne_writer, self.controller)
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
        self.Teledyne_writer.write(str("Reading from Teledyne Flow Controller THCD-100: The Address letter is %s "%(self.controller.getAddressLetter())))     
        self.Teledyne_writer.write(str("The setpoint mode is set to %s."%(self.controller.getSetpointMode())))
        self.Teledyne_writer.write("^ date (Y-m-d) ^ time (H:M:S) ^ (flow (%s), data status)"%(self.controller.getUnit()))
        return

    def close(self):
        self.logger.info("Closing the logger")
        self.writerThread.stopped = True
        self.writerThread.Tevent.set()
        self.Teledyne_writer.close()
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
        self.Teledyne_writer = writer
        self.controller = controller

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
        flow = self.controller.readData()
        if flow == -1:
            flow = [0,-1]
        now = datetime.datetime.now()
        self.Teledyne_writer.write(flow, now)


if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to readout the Teledyne flow controller THCD-100')
    parser.add_argument("-d", "--debug", dest="loglevel", type=int, help="switch to loglevel debug", default=10)
    parser.add_argument("-i", "--interval", dest="loginterval", type=int, help="logging interval in s, default value: 30 s", default=30)
    parser.add_argument("-v", "--vendorID", dest="vendorID", type=str, help="vendor ID of attached converter", default='0557')
    parser.add_argument("-p", "--productID", dest="productID", type=str, help="product ID of attached converter", default='2008')
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


    Teledyne_master = TeledyneMaster(opts, logger)
    Teledyne_master.Teledynemaster()
    sys.exit(0)

