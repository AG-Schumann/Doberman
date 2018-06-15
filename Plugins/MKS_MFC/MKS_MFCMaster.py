#! /usr/bin/env python3.3

import os
import time
import datetime
import logging
from argparse import ArgumentParser
import MKS_MFCSerial
import threading
import sys


class MKS_MFCMaster(object):
    """
    Main function to controls the MKS_MFC.
    The function can be called with several options in the command line mode.
    It will start automatically a serial connection to the MKS MFC controller.
    It can run in interactive shells as well as a standalone python program
    (call via 'python MKS_MFCMaster.py -opts').
    """

    def __init__(self, opts):

        self.logger = opts.logger
        self.opts = opts
        self.controller = None
        self.controller = MKS_MFCSerial.MKS_MFCSerial(opts)

        if self.controller is None:
            self.logger.fatal("Controller not initialized correctly")
            exit()

        self._lifes = 99999999999999999999999

        if not self.opts.queue:
            self.logger.critical(
                "No queue to put the data in. No data can be stored.")

        self.writerThread = ReadoutThread(self.opts, self.controller)

    def MKS_MFCmaster(self):
        """
        This function starts the read out process from the controller.
        It opens a new thread and checks from time to time whether the
        thread is still alive, if not it reactivates it.
        """
        try:
            self.writerThread.start()
            runner = 0
            while runner < self._lifes:
                runner += 1
                self.logger.info("Main program still alive...")
                if runner % 2 == 0:
                    if self.writerThread.stopped or not self.writerThread.isAlive():
                        self.logger.fatal("Logging thread died. Reviving...")
                        self.writerThread.start()
                time.sleep(30)
            self.close()
        except KeyboardInterrupt:
            self.logger.fatal("\n\nProgram killed by ctrl-c\n\n")
            self.close()

    def close(self):
        self.logger.info("Closing the logger")
        self.writerThread.stopped = True
        self.writerThread.Tevent.set()
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
    Class that is the read out thread.
    Controlls the thread: starting, running and stopping it.
    """

    def __init__(self, opts, controller):

        self.ReadOutInterval = 30
        self.logger = opts.logger
        self.opts = opts
        self.controller = controller

        if self.opts.loginterval < 1000 and self.opts.loginterval >= 5:
            self.ReadOutInterval = self.opts.loginterval
            self.logger.info("Readout interval set to %i s." %
                             self.ReadOutInterval)
        else:
            self.logger.error("Required readout interval invalid. "
                              "Running with default 30s.")
            self.ReadOutInterval = 30

        self.stopped = False
        threading.Thread.__init__(self)
        self.Tevent = threading.Event()

    def run(self):
        while not self.stopped:
            self.ReadOutT()
            self.Tevent.wait(self.ReadOutInterval)

    def TransformStatus(self, alarmstatus):
        """
        Transforms the status from a list of letters to a number.
        0 = OK
        -2 = No status
        -1 = No connection
        1-9 = Warning
        > 9 = Alarm

        Error statuses:
        C = Valve closed
        CR = Calibration recommended
        E = System error
        H = High alarm condition
        HH = High-high alarm condition
        IP = Insufficient gas inlet pressure
        L = Low alarm condition
        LL = Low-low alarm condition
        M = Memory (EEPROM) failure
        O = OK, no errors to report
        OC = Unexpected change in operating
        conditions
        P = Purge
        T = Over temperature
        U = Uncalibrated
        V = Valve drive level alarm condition
        """
        status_number = []
        for status in alarmstatus:
            if status == "O":
                status = 0
            elif status == "C":
                status = 10
            elif status == "CR":
                status = 1
            elif status == "E":
                status = 11
            elif status in ["H", "HH"]:
                status = 2
            elif status == "IP":
                status = 3
            elif status in ["L", "LL"]:
                status = 4
            elif status == "M":
                status = 12
            elif status == "OC":
                status = 5
            elif status == "P":
                status = 6
            elif status == "T":
                status = 13
            elif status == "U":
                status = 7
            elif status == "V":
                status = 8
            elif status == -1:
                pass
            else:
                status = -2
            if status > 9:
                return [status]
            else:
                status_number.append(status)
        return [status_number[0]]

    def ReadOutT(self):
        """
        Read out thread itself. Defines the read out format.
        """
        # Collect status and data
        self.logger.debug("Reading data for log...")
        status = self.controller.getStatus()
        if status != ["O"]:
            self.logger.warning("MKS_MFC got an alarm status '%s'" % status)
        if self.opts.queue:
            status = self.TransformStatus(status)
        status = status * 3
        logtime = datetime.datetime.now()
        flow_rate = self.controller.getFlowRate()
        units = self.controller.getUnits()
        flow_rate_percent = self.controller.getFlowRatePercent()
        internal_temperature = self.controller.getInternalTemperature()
        data = [flow_rate, flow_rate_percent, internal_temperature]
        # Transform status[ii] to -1 (no connection) when data[ii] = -1
        for ii, d in enumerate(data):
            if d == -1:
                status[ii] = -1
        # Put data to queue or print tgio screen
        if self.opts.queue:
            self.opts.queue.put(['MKS_MFC', logtime, data, status])
            self.logger.info("Put data to queue: %s" %
                             str(['MKS_MFC', logtime, data, status]))
        else:
            self.logger.warning(
                "No queue to send the data! Only printing data to the screen.")
            print("\n\n#############################")
            print("MKS_MFC:\nFlow Rate and Unit:")
            print(("%s [%s]" % (str(flow_rate), units)))
            print("\nMKS_MFC: Flow Rate in percent:")
            print(flow_rate_percent)
            print("\nInternal temperature [C]:")
            print(internal_temperature)
            print("\nMKS_MFC: Status:")
            print(status)
            print("#############################\n\n")

if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to readout '
                                  'the MKS_MFC controller')
    parser.add_argument("-d",
                        "--debug",
                        dest="loglevel",
                        type=int,
                        help="switch to loglevel debug",
                        default=20)
    parser.add_argument("-i",
                        "--interval",
                        dest="loginterval",
                        type=int,
                        help="logging interval in s, default value: 30 s",
                        default=30)
    parser.add_argument("-v",
                        "--idvendor",
                        dest="vendorID",
                        type=str,
                        help="VendorID. default: None",
                        default="0403")
    parser.add_argument("-p",
                        "--idproduct",
                        dest="productID",
                        type=str,
                        help="ProductID. default: None",
                        default="6001")
    opts = parser.parse_args()

    logger = logging.getLogger()
    if opts.loglevel not in [0, 10, 20, 30, 40, 50]:
        print(("ERROR: Given log level %i not allowed. "
              "Fall back to default value of 20" % opts.loglevel))
        opts.loglevel = 20
    logger.setLevel(int(opts.loglevel))

    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:'
                                  '%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)
    opts.logger = logger
    opts.queue = None

    opts.occupied_ttyUSB = []

    MKS_MFC_master = MKS_MFCMaster(opts)
    MKS_MFC_master.MKS_MFCmaster()
    sys.exit(0)
