#! /usr/bin/env python3.3

import os
import time
import datetime
import logging
from argparse import ArgumentParser
import cryoSerial
import cryoLAN
import cryoWriter
import threading
import sys



class cryoMaster(object):
    """
    Main function to controll the cryo con 22 c cryo controller.
    The function can be called with several options in the command line mode.
    It will start automatically a connection to the cryo controller on the choosen connection (LAN, serial, ...).
    It can run in interactive shells as well as a standalone python program (call via 'python cryoMaster.py -opts').
    """
    def __init__(self, opts, logger):

        self.logger = logger
        self.opts = opts
        self.controller = None
        if self.opts.addresses[0] == "SER":
            self.controller = cryoSerial.cryoSerial(logger)
        elif self.opts.addresses[0] == "LAN":
            self.controller = None
            self.ipaddress = self.opts.addresses[1]
            self.port = self.opts.addresses[2]
            self.controller = cryoLAN.cryoLAN(logger, self.ipaddress, self.port)
        if self.controller is None:
            self.logger.fatal("Controller not initialized correctly")
            exit()

        self._lifes = 99999999999999999999999
        if hasattr(self.opts, 'log_path'):
            self.cryo_writer = cryoWriter.cryoWriter(logger, log_path = self.opts.log_path)
        else:
            self.cryo_writer = cryoWriter.cryoWriter(logger)
        
        self.logHead()

        self.writerThread = ReadoutThread(self.logger, self.opts, self.cryo_writer, self.controller)

    def cryomaster(self):
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
        sensa = self.controller.getInputSensor('A')
        sensb = self.controller.getInputSensor('B')
        self.cryo_writer.write(str("# Reading from Cryo Controller: %s . Its name is %s ."%(self.controller.getDeviceIdent(), self.controller.getInstrumentName())))
        self.cryo_writer.write(str("Naming scheme: Channel A: %s, Channel B: %s"%(self.controller.getInputName('A'),self.controller.getInputName('B'))))        
        self.cryo_writer.write(str("Input sensors: Ch A: %s, Ch A: %s"%(sensa, sensb)))
        self.cryo_writer.write(str("Input sensor names: Ch A: %s, Ch A: %s"%(self.controller.getSensorName(sensa),self.controller.getSensorName(sensb))))        
        self.cryo_writer.write(str("Input sensor types: Ch A: %s, Ch A: %s"%(self.controller.getSensorType(sensa),self.controller.getSensorType(sensb))))        
        self.cryo_writer.write(str("Input alarm status Ch A: low: %s, high: %s"%(self.controller.getAlarmHighStatus('A'),self.controller.getAlarmLowStatus('A'))))
        self.cryo_writer.write(str("Input alarm status Ch B: low: %s, high: %s"%(self.controller.getAlarmHighStatus('B'),self.controller.getAlarmLowStatus('B'))))
        self.cryo_writer.write(str("Input sensors alarms high: Ch A: %s, Ch A: %s"%(self.controller.getAlarmHighVal('A'),self.controller.getAlarmHighVal('B'))))        
        self.cryo_writer.write(str("Input sensors alarms low: Ch A: %s, Ch A: %s"%(self.controller.getAlarmLowVal('A'),self.controller.getAlarmLowVal('B'))))        
        self.cryo_writer.write(str("Loop types: 1: %s, 2: %s, 3: %s, 4: %s"%(self.controller.getLoopType('1'),self.controller.getLoopType('2'),self.controller.getLoopType('3'),self.controller.getLoopType('4'))))        
        self.cryo_writer.write(str("Loop sources: 1: %s, 2: %s, 3: %s, 4: %s"%(self.controller.getLoopSource('1'),self.controller.getLoopSource('2'),self.controller.getLoopSource('3'),self.controller.getLoopSource('4'))))        
        self.cryo_writer.write(str("\n\n"))
        self.cryo_writer.write("^ date (Y-m-d) ^ time (H:M:S) ^ Temp A (K) ^ Temp B (K) ^ getLoopPower 1 (%) ^ getLoopPowerOut 1 (%) ^ Setpoint 1 (K) ^ Setpoint 2 (K) ^ Alarm Status Ch A ^ Alarm Status Ch B ^")
        return

    def close(self):
        self.logger.info("Closing the logger")
        self.writerThread.stopped = True
        self.writerThread.Tevent.set()
        self.cryo_writer.close()
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
        self.cryo_writer = writer
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
        print("!!!!!!!!!!! ATTENTION: We have overwritten cryocon22.ReadOutT with queued_ReadOutT !!!!")
        self.logger.debug("Reading data for log...")
        now = datetime.datetime.now()
        readout = str("| %s | %s | %s | %s | %s | %s | %s |"%(now.strftime('%Y-%m-%d | %H:%M:%S'),self.controller.getTemp('A'),self.controller.getTemp('B'), self.cryocon_22c_master.controller.getLoopPower('1'), self.cryocon_22c_master.controller.getLoopPowerOut('1'), self.cryocon_22c_master.controller.getSetPoint('1'), self.cryocon_22c_master.controller.getSetPoint('2'), self.controller.getAlarmStatus('A'),self.controller.getAlarmStatus('B')))
        self.cryo_writer.write(readout)
        self.logger.info("Logged string: %s"%readout)


if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to readout the cryo con controller 22c')
    parser.add_argument("-l", "--lan", action="store_true", dest="lan", help="use the lan connection to the cryo controller", default=False)
    parser.add_argument("-s", "--serial", action="store_true", dest="serial", help="use the serial/usb connection to the cryo controller", default=False)
    parser.add_argument("-d", "--debug", dest="loglevel", type=int, help="switch to loglevel debug", default=10)
    parser.add_argument("-i", "--interval", dest="loginterval", type=int, help="logging interval in s, default value: 30 s", default=30)
    parser.add_argument("-a", "--address", dest="ipaddress", type=str, help="ip address for the lan connection. Not needed in case of serial connection", default="192.168.1.5")
    parser.add_argument("-p", "--port", dest="port", type=int, help="UDP port to the cryo controller", default=5001)
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

    if (opts.serial and opts.lan) or (not opts.serial and not opts.lan):
        logger.fatal("Choose one connection option: lan or serial (-l or -s option). Only one at once allowed.")
        sys.exit(-1)

    cryo_master = cryoMaster(opts, logger)
    cryo_master.cryomaster()
    sys.exit(0)
