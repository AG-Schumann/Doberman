#! /usr/bin/env python3.3

from argparse import ArgumentParser
import threading
import sys
import os
import time
import datetime
import logging
from subprocess import Popen, PIPE


class memory_surveillanceControl(object):
    """
    Class for memory survellance
    """
    def __init__(self, opts):
        self.opts = opts
        self.logger = self.opts.logger
        self._lifes = 99999999999999999999999
        self.getDirectory()
        self.writerThread = ReadoutThread(self.opts)

    def getDirectory(self):
        """
        Transforms additional parameter to direcotry if exists
        """
        if self.opts.additional_parameters and self.opts.additional_parameters != ['']:
            self.opts.directory = self.opts.additional_parameters[0]
            return
        try:
            if not self.opts.directory:
                raise
        except:
            self.logger.info("Could not load directory. "
                             "Running with default: '/dev/')")
            self.opts.directory = "/dev/"

    def memory_surveillancecontrol(self):

        """
        This function starts the read out process.
        It opens a new thread and checks from time to time whether
        the thread is still alive, if not it reactivates it.
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
        return

    def __exit__(self):
        self.close()


class ReadoutThread(threading.Thread):
    """
    Class that is the read out thread.
    Controlls the thread: starting, running and stopping it.
    """
    def __init__(self, opts):
        self.opts = opts
        self.sleeptime = self.opts.loginterval
        self.logger = self.opts.logger
        self.stopped = False
        threading.Thread.__init__(self)
        self.Tevent = threading.Event()

    def run(self):
        while not self.stopped:
            self.ReadOutT()
            self.Tevent.wait(self.sleeptime)

    def ReadOutT(self):
        """
        Read out thread itself. Defines the read out format.
        """
        self.logger.debug("Reading data for log...")
        data, status, names = self.checkMemory()
        now = datetime.datetime.now()
        if self.opts.queue:
            self.opts.queue.put(["memory_surveillance", now, data, status])
        else:
            print("\n")
            for ii, used_space in enumerate(data):
                print("  Memory of %s: Used %s%% (status: %s)" %
                      (str(names[ii]), str(used_space), str(status)))
            print("\n")

    def checkMemory(self):
        """
        Reading memory at opts.directory
        """
        try:
            p = Popen(['df', ], stdin=PIPE, stdout=PIPE, stderr=PIPE)
            output, e = p.communicate()
            if e:
                self.logger.error("Error in memory check: %s." % e)
                return [0], [10], ""
            output = [line for line in output.splitlines()[1:]
                      if str(self.opts.directory) in line]
        except Exception as e:
            self.logger.warning("Error while checking memory space: %s." % e)
            return [0], [-1], ""
        if not output:
            self.logger.error("Directory space with '%s' not found. Can not "
                              "check memory space." % self.opts.directory)
            return [0], [11], ""
        try:
            output = [line.split() for line in output]
            names = [item[0] for item in output]
            occupied_space = [item[4].rstrip("%") for item in output]
            if len(output) > 1:
                self.logger.warning("More than one directory space with '%s' "
                                    "found. Transmitting all (%s) ..." %
                                    (self.opts.directory, str(names)))
        except Exception as e:
            self.logger.warning("Error while analysing memory space output. "
                                "Error: %s." % e)
            return [0], [12], ""
        return occupied_space, [0]*len([occupied_space]), names


if __name__ == '__main__':
    parser = ArgumentParser(usage=("%(prog)s [options] \n\n Program "
                                   "to readout the memory used."))
    parser.add_argument("-d",
                        "--debug",
                        dest="loglevel",
                        type=int,
                        help="switch to loglevel debug",
                        default=10)
    parser.add_argument("-i",
                        "--interval",
                        dest="loginterval",
                        type=int,
                        help="logging interval in s, default value: 30 s",
                        default=30)
    parser.add_argument("-dir",
                        "--directory",
                        dest="directory",
                        type=str,
                        help=("Directory (path) where program runs, "
                              "default = '/dev/'"),
                        default='/dev/')
    opts = parser.parse_args()
    logger = logging.getLogger()
    if opts.loglevel not in [0, 10, 20, 30, 40, 50]:
        print("ERROR: Given log level %i not allowed. "
              "Fall back to default value of 10" % opts.loglevel)
    logger.setLevel(int(opts.loglevel))
    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:'
                                  '%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)
    opts.logger = logger
    opts.queue = None  # To get compatible with Doberman
    opts.additional_parameters = [""]  # To get compatible with Doberman
    ms = memory_surveillanceControl(opts)
    ms.memory_surveillancecontrol()
    sys.exit(0)
