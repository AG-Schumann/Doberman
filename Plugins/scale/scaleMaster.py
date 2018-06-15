#! /usr/bin/env python3.3

import os
import time
import datetime
import logging
from argparse import ArgumentParser
import scaleSerial
import scaleWriter
import threading
import sys



class scaleMaster(object):
    """
    Main function to control the scale.
    The function can be called with several options in the command line mode.
    It will start automatically a serial connection to the scale.
    It can run in interactive shells as well as a standalone python program (call via 'python scaleMaster.py -opts').
    """
    def __init__(self, opts, logger):

        self.logger = logger
        self.opts = opts
        self.controller = None
        self.controller = scaleSerial.scaleSerial(opts, logger)
        
        if self.controller is None:
            self.logger.fatal("Scale not initialized correctly")
            exit()

        self._lifes = 99999999999999999999999
        
        if not hasattr(self.opts, 'queue'):
            self.opts.queue = None
        
        if hasattr(self.opts, 'log_path'):
            self.scale_writer = scaleWriter.scaleWriter(logger, self.opts.queue, log_path = self.opts.log_path)
        else:
            self.scale_writer = scaleWriter.scaleWriter(logger, self.opts.queue)

        if not self.opts.queue is None:
            self.logHead()

        self.writerThread = ReadoutThread(self.logger, self.opts, self.scale_writer, self.controller)

    def scalemaster(self):
        """
        This function starts the read out process from the scale.
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

    def logHead(self):#TODO: add further parameters to loghead
        """
        Defines the read out values and writes the logging file header header.
        """
        self.scale_writer.writeToFile(str("# Reading from scale: The ID is %s . Its address is %s ."%("test ID", "test address")))
        self.scale_writer.writeToFile(str("# Reading from scale: The high alarm value is: %s ."%("test high alarm")))
        self.scale_writer.writeToFile(str("# Reading from scale: The low alarm values is: %s ."%("test low alarm")))
       
        self.scale_writer.writeToFile(str("\n\n"))
        self.scale_writer.writeToFile("^ date (Y-m-d) ^ time (H:M:S) ^ Measured value ^")
        return

    def close(self):
        self.logger.info("Closing the logger")
        self.writerThread.stopped = True
        self.writerThread.Tevent.set()
        self.scale_writer.close()
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
        self.scale_writer = writer
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
        now = datetime.datetime.now()
        self.scale_writer.write(self.controller.measure(), now)



if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to readout the scale')
    parser.add_argument("-d", "--debug", dest="loglevel", type=int, help="switch to loglevel debug", default=10)
    parser.add_argument("-i", "--interval", dest="loginterval", type=int, help="logging interval in s, default value: 30 s", default=30)
    parser.add_argument("-v", "--idvendor", dest="vendorID", type=int, help="VendorID. default: None", default=None)
    parser.add_argument("-p", "--idproduct", dest="productID", type=int, help="ProductID. default: None", default=None)
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

    scale_master = scaleMaster(opts, logger)
    scale_master.scalemaster()
    sys.exit(0)
