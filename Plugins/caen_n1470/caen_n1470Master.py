#! /usr/bin/env python3.3

import os
import time
import datetime
import logging
from argparse import ArgumentParser
import caen_n1470Serial
import caen_n1470Writer
import threading
import sys



class caen_n1470Master(object):
    """
    Main function to controll the CAEN N1470 module.
    The function can be called with several options in the command line mode.
    It will start automatically a serial connection to the caen_n1470 module.
    It can run in interactive shells as well as a standalone python program (call via 'python caen_n1470Master.py -opts').
    """
    def __init__(self, opts, logger):

        self.logger = logger
        self.opts = opts
        self.controller = None
        self.controller = caen_n1470Serial.caen_n1470Serial(opts, logger)
        
        if self.controller is None:
            self.logger.fatal("Controller not initialized correctly")
            exit()

        self._lifes = 99999999999999999999999
        
        if hasattr(self.opts, 'log_path'):
            self.caen_n1470_writer = caen_n1470Writer.caen_n1470Writer(logger, log_path = self.opts.log_path)
        else:
            self.caen_n1470_writer = caen_n1470Writer.caen_n1470Writer(logger, opts.queue)

        if not self.opts.queue:
            self.logHead()

        self.writerThread = ReadoutThread(self.logger, self.opts, self.caen_n1470_writer, self.controller)

    def caen_n1470master(self):
        """
        This function starts the read out process from the module.
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
        self.caen_n1470_writer.writeToFile(str("# Reading from CAEN N1470 module: The SN is %s ."%(self.controller.getSN())))
       
        self.caen_n1470_writer.writeToFile(str("\n\n"))
        self.caen_n1470_writer.writeToFile("^ date (Y-m-d) ^ time (H:M:S) ^ V_0 [V] ^ V_1 [V] ^ V_2 [V] ^ V_3 [V] ^ Vset_0 [V] ^ Vset_1 [V] ^ Vset_2 [V] ^ V_3 [V] ^ I_0 [muA] ^ I_1 [muA] ^ I_2 [muA] ^ I_3 [muA] ^")
        return

    def close(self):
        self.logger.info("Closing the logger")
        self.writerThread.stopped = True
        self.writerThread.Tevent.set()
        self.caen_n1470_writer.close()
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
        self.caen_n1470_writer = writer
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
        data = [self.controller.getV(0),self.controller.getV(1),self.controller.getV(2),self.controller.getV(3),self.controller.getVset(0),self.controller.getVset(1),self.controller.getVset(2),self.controller.getVset(3),self.controller.getI(0),self.controller.getI(1),self.controller.getI(2),self.controller.getI(3)]
        self.caen_n1470_writer.write(data, now)



if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to readout the CAEN N1470 module')
    parser.add_argument("-d", "--debug", dest="loglevel", type=int, help="switch to loglevel debug", default=10)
    parser.add_argument("-i", "--interval", dest="loginterval", type=int, help="logging interval in s, default value: 30 s", default=30)
    parser.add_argument("-v", "--idvendor", dest="vendorID", type=str, help="VendorID. default: None", default=None)
    parser.add_argument("-p", "--idproduct", dest="productID", type=str, help="ProductID. default: None", default=None)
    opts = parser.parse_args()
    opts.addresses = ['SER',opts.productID, opts.vendorID]
    
    logger = logging.getLogger()
    if not opts.loglevel in [0,10,20,30,40,50]:
        print(("ERROR: Given log level %i not allowed. Fall back to default value of 10"%opts.loglevel))
    logger.setLevel(int(opts.loglevel))

    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)

    caen_n1470_master = caen_n1470Master(opts, logger)
    caen_n1470_master.caen_n1470master()
    sys.exit(0)
