#! /usr/bin/env python3.3

import os
import time
import datetime
import logging
from argparse import ArgumentParser
import TemperNTCWriter
import threading
import sys
import usb.core
#pyusb 1.0 necessary!


class TemperNTCMaster(object):
    """
    Main function to controll the temperNTC USB stick.
    The function can be called with several options in the command line mode.
    It will start automatically a connection to the temperntc.
    It can run in interactive shells as well as a standalone python program (call via 'python TemperNTCMaster.py -opts').

    needs pyusb 1.0:
    sudo apt-get install python libusb-1.0-0-dev
    git clone https://github.com/walac/pyusb
    cd pyusb && sudo python setup.py install
    """
    def __init__(self, opts, logger):

        self.logger = logger
        self.opts = opts

        self._lifes = 99999999999999999999999

        self.__connected = False
        self.__device = self._getControl()

        self.__unit = 'K'
        self.__ext_alarm = (0,999)
        self.__internal_alarm = (0,888)
        
        if hasattr(self.opts, 'log_path'):
            self.temperNTC_writer = TemperNTCWriter.temperNTCWriter(logger, log_path = self.opts.log_path)
        else:
            self.temperNTC_writer = TemperNTCWriter.temperNTCWriter(logger)

        self.logHead()
        self.writerThread = ReadoutThread(self.logger, self.opts, self.temperNTC_writer, self)

    def TemperNTCMaster(self):
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
        self.temperNTC_writer.write(str("# The set temperature unit is %s ."%self.get_temperature_unit()))
        self.temperNTC_writer.write(str("# The set external temperature alarm values are %s ."%str(self.get_external_alarm())))
        self.temperNTC_writer.write(str("# The set internal temperature alarm values are %s ."%str(self.get_internal_alarm())))
        self.temperNTC_writer.write(str("\n\n"))
        self.temperNTC_writer.write("^ date (Y-m-d) ^ time (H:M:S) ^ external Temp  (%s) ^ internal Temp (%s) ^  Alarm status external temperature ^ Alarm status internal temperature ^"%(self.get_temperature_unit(),self.get_temperature_unit()))
        return

    def set_external_alarm(self, temp = (0,999)):
        """
        set the values for the alarm for the external sensor as tuple(low, high). To be given in the set temperature unit.
        """
        if not isinstance(temp, tuple) and not isinstance(temp, list):
            self.logger.warning("Alarm values for external sensor not modified due to invalid type. Must be tuple(float, float).")
            return -1
        if not len(temp) == 2:
            self.logger.warning("Alarm values for external sensor not modified due to invalid length. Must be tuple(float, float).")
            return -1
        for vt in temp:
            if not isinstance(vt, float) and not isinstance(vt, int):
                self.logger.warning("Alarm values for external sensor not modified due to invalid type. Must be tuple(float, float).")
                return -1
        if temp[0] <= temp[1]:
            self.__ext_alarm = (self._get_temp_calced(temp[0]), self._get_temp_calced(temp[1]))
        else:
            self.__ext_alarm = (self._get_temp_calced(temp[1]), self._get_temp_calced(temp[0]))
        return
    
    def set_internal_alarm(self, temp = (0,888)):
        """
        set the values for the alarm for the internal sensor as tuple(low, high) To be given in the set temperature unit.
        """
        if not isinstance(temp, tuple) and not isinstance(temp, list):
            self.logger.warning("Alarm values for internal sensor not modified due to invalid type. Must be tuple(float, float).")
            return -1
        if not len(temp) == 2:
            self.logger.warning("Alarm values for external sensor not modified due to invalid length. Must be tuple(float, float).")
            return -1
        for vt in temp:
            if not isinstance(vt, float) and not isinstance(vt, int):
                self.logger.warning("Alarm values for external sensor not modified due to invalid type. Must be tuple(float, float).")
                return -1
        if temp[0] <= temp[1]:
            self.__ext_alarm = (self._get_temp_calced(temp[0]), self._get_temp_calced(temp[1]))
        else:
            self.__ext_alarm = (self._get_temp_calced(temp[1]), self._get_temp_calced(temp[0]))
        return

    def get_external_alarm(self):
        """
        returns a tuple with the alarm values for the external sensor
        """
        return (self._get_temp_calced(self.__ext_alarm[0]), self._get_temp_calced(self.__ext_alarm[1]))
    
    def get_internal_alarm(self):
        """
        returns a tuple with the alarm values for the internal sensor
        """
        return (self._get_temp_calced(self.__internal_alarm[0]), self._get_temp_calced(self.__internal_alarm[1]))

    def get_temperature_unit(self):
        """
        read the temperature unit
        """
        return self.__unit

    def set_temperature_unit(self, unit = 'K'):
        """
        change the temperature unit: keywords: 'K' or 'C': Kelvin or degree Celsius
        """
        if unit == 'K' or unit == 'k':
            self.__unit = 'K'
        elif unit == 'C' or unit == 'c':
            self.__unit = 'C'
        return

    def check_internal_alarm(self):
        """
        Check whether temp is in the alarm range
        """
        temp = self.get_internal_temperature()
        if not isinstance(temp, float) and not isinstance(temp, int):
            self.logger.error("Cannot check whether temp is in the alarm range: invalid type. Must be int or float.")
            return -1
        if temp <= self.__internal_alarm[0]:
            self.logger.warning("Temperature %s of internal sensor out of alarm range (%s)."%(temp, self.get_internal_alarm()))
            return -2
        elif temp >= self.__internal_alarm[1]:
            self.logger.warning("Temperature %s of internal sensor out of alarm range (%s)."%(temp, self.get_internal_alarm()))
            return -3
        self.logger.info("Temperature %s of internal sensor in alarm range (%s)."%(temp, self.get_internal_alarm()))
        return 0

    def check_external_alarm(self):
        """
        Check whether temp is in the alarm range
        """
        temp = self.get_external_temperature()
        if not isinstance(temp, float) and not isinstance(temp, int):
            self.logger.error("Cannot check whether temp is in the alarm range: invalid type. Must be int or float.")
            return -1
        if temp <= self.__ext_alarm[0]:
            self.logger.warning("Temperature %s of external sensor out of alarm range (%s)."%(temp, self.get_external_alarm()))
            return -2
        elif temp >= self.__ext_alarm[1]:
            self.logger.warning("Temperature %s of external sensor out of alarm range (%s)."%(temp, self.get_external_alarm()))
            return -3
        self.logger.info("Temperature %s of external sensor in alarm range (%s)."%(temp, self.get_external_alarm()))
        return 0
    
    def _get_temp_calced(self, temp):
        """
        Return a stored temp as set unit transf temp (C or K)
        """
        if self.__unit == 'K':
            return temp
        elif self.__unit == 'C':
            return self._calc_temp(temp, 'K2C')

    def _calc_temp(self, temp, mode = 'K2C'):
        """
        Calculate the temperature in the given unit. temp must be given in K in standard mode = 'K2C' (other: 'C2K').
        """
        if not mode in ['K2C','C2K']:
            self.logger.error("Calculation of the temperature with this mode not possible!")
            return -1
        if mode == 'K2C':
            return (temp-273.15)
        elif mode == 'C2K':
            return (temp+273.15)
        else:
            self.logger.error("Unknown mode for temperature calculation")
            return -2

    def get_internal_temperature(self):
        """
        get the internal temperature at the stick
        https://github.com/padelt/temper-python/
        """
        temperature = None

        nullTrailer = ''
        for i in range(0, 24):
            nullTrailer = nullTrailer + chr(0)
        
        try: 
            temperatureBuffer = self.__device.ctrl_transfer(0xa1, 1, 0x300, 0x1, 256, 0)
        except usb.core.USBError as e:
            self.logger.error("Cannot read temperature from TemperNTC USB device, most likely unconnected... Exact error: %s"%e)
            return -999
        
        if len(temperatureBuffer) > 1:
            if temperatureBuffer[0] == 0 and temperatureBuffer[1] == 255:
                self.logger.warning("Failed to retrieve temperature")
                return None
            temperature = int(temperatureBuffer[0] << 8) + int(temperatureBuffer[1] & 0xff)# + self.calibrationConstant
            temperature = temperature * (125.0 / 32000.0)+273.15
        else:
            self.logger.warning("Failed to retrieve valid temperature from TemperNTC USB device.")
            return None
        self.logger.debug("Internal temperature read as: %s"%str(temperature))
        return self._get_temp_calced(temperature)

    def get_external_temperature(self):
        """
        get the temperature of the external sensor
        """
        temp = None
        #TODO> write this function
        return 0.0
        return self._get_temp_calced(temp)


    def _control_transfer(self, data):
        """
        Send device a control request with standard parameters and <data> as
        payload.
        """
        self.logger.debug('Ctrl transfer: {0}'.format(data))
        self.__device.ctrl_transfer(bmRequestType=0x21, bRequest=0x09, wValue=0x0200, wIndex=0x01, data_or_wLength=data, timeout=TIMEOUT)

    def _interrupt_read(self):
        """
        Read data from device.
        """
        data = self.__device.read(ENDPOINT, REQ_INT_LEN, timeout=TIMEOUT)
        self.logger.debug('Read data: {0}'.format(data))
        return data

    def _getControl(self):
        """
        connect the temperNTC usb stick
        """
        devices = None
        connected = False
        self.logger.debug("Trying to get control over the TemperNTC usb temperature sensor... ")
        while not connected:
            try:
                self.logger.debug("Looking for TemperNTC device ...")
                devices = usb.core.find(idVendor = 0x1130, idProduct = 0x660c)
            except:
                self.logger.error("Unexpected error when trying to find temperNTC usb stick:%s", str(sys.exc_info()[0]))
                raise
            if devices is None:
                self.logger.error("Cannot identify TemperNTC USB stick. Check whether stick is connected properly. Trying again in 5s...")
                connected = False
                time.sleep(5)
                continue
            try:
                if devices.is_kernel_driver_active(0):
                    devices.detach_kernel_driver(0)
                if devices.is_kernel_driver_active(1):
                    devices.detach_kernel_driver(1)
            except NotImplementedError as e:
                #Note: some system do not implement is_kernel_driver_active
                try:
                    devices.detach_kernel_driver(0)
                    devices.detach_kernel_driver(1)
                except Exception as e:
                    self.logger.error("An error appeared when detaching the TemperNTC USB driver from kernel: %s"%str(e))
                    time.sleep(5)
                    continue
            except Exception as e:
                self.logger.error("An error appeared when detaching the active TemperNTC USB driver from kernel: %s"%str(e))
                time.sleep(5)
                continue

            try:
                self.logger.debug("Found TemperNTC device, setting it up ...")
                devices.set_configuration()
                connected = True
            except usb.core.USBError as e:
                connected = False
                self.logger.error("Cannot access TemperNTC USB device: insufficient permissions: %s"%str(e))
                time.sleep(5)
                continue
        else:
            self.__connected = True
            self.logger.info("Successfully connected to TemperNTC USB stick.")

        self.logger.debug("Trying to initialise TemperNTC USB stick...")
        nullTrailer = ''
        for i in range(0, 24):
            nullTrailer = nullTrailer + chr(0)
        firstMagicSequence = chr(10) + chr(11) + chr(12) + chr(13)  + chr(0) + chr(0) + chr(2) + chr(0) + nullTrailer
        secondMagicSequence = chr(0x54) + chr(0) + chr(0) + chr(0) + chr(0) + chr(0) + chr(0) + chr(0) + nullTrailer
        thirdMagicSequence = chr(0) + chr(0) + chr(0) + chr(0) + chr(0) + chr(0) + chr(0) + chr(0) + nullTrailer
        fourthMagicSequence = chr(10) + chr(11) + chr(12) + chr(13)  + chr(0) + chr(0) + chr(1) + chr(0) + nullTrailer

        #for device in self.__devices:
        bytesSent = devices.ctrl_transfer(0x21, 9, 0x200, 0x1, firstMagicSequence, 32)
        bytesSent = devices.ctrl_transfer(0x21, 9, 0x200, 0x1, secondMagicSequence, 32)
        for i in range(0, 7):
            bytesSent = devices.ctrl_transfer(0x21, 9, 0x200, 0x1, thirdMagicSequence, 32)
        bytesSent = devices.ctrl_transfer(0x21, 9, 0x200, 0x1, fourthMagicSequence, 32)
        self.logger.info("Successfully initialized to TemperNTC USB stick.")
        return devices
    
    def connected(self):
        """
        Returns the connection status of the controller.
        """
        self.logger.info("The device connection status is: %s",self.__connected)
        return self.__connected

    def __del__(self):
        self.close()
        return
    
    def __exit__(self):
        self.close()
        return

    def close(self):
        self.logger.info("Closing the logger")
        self.writerThread.stopped = True
        self.writerThread.Tevent.set()
        self.temperNTC_writer.close()
        self.__connected = False
        self.logger.info("Trying to deactivate active temperNTC USB device...")
        if self.__device.is_kernel_driver_active(0):
            self.__device.detach_kernel_driver(0)
        if self.__device.is_kernel_driver_active(1):
            self.__device.detach_kernel_driver(1)

        loggerslist = list(self.logger.handlers)
        for lle in loggerslist:
            self.logger.removeHandler(lle)
            lle.flush()
            lle.close()
        return


class ReadoutThread(threading.Thread):
    """
    Class that is the read out thread. Controlls the thread: starting, running and stopping it.
    """
    def __init__(self, logger, opts, writer, ntcmaster):

        self.ReadOutInterval = 30
        self.logger = logger
        self.opts = opts
        self.temperNTC_writer = writer
        self.temperNTCMaster = ntcmaster

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
        self.logger.warning("set temp unit %s"%self.temperNTCMaster.get_temperature_unit())
        readout = str("| %s | %s | %s |"%(now.strftime('%Y-%m-%d | %H:%M:%S'),self.temperNTCMaster.get_internal_temperature(), self.temperNTCMaster.get_external_temperature()))
        self.temperNTC_writer.write(readout)
        self.logger.info("Logged string: %s"%readout)


if __name__ == '__main__':
    parser = ArgumentParser(usage='%(prog)s [options] \n\n Program to readout the temper NTC USB stick')
    parser.add_argument("-d", "--debug", dest="loglevel", type=int, help="switch to loglevel debug", default=10)
    parser.add_argument("-i", "--interval", dest="loginterval", type=int, help="logging interval in s, default value: 30 s", default=30)
    opts = parser.parse_args()
    
    logger = logging.getLogger('slowcontrol.plugins.temperntclogger')
    if not opts.loglevel in [0,10,20,30,40,50]:
        print("ERROR: Given log level %i not allowed. Fall back to default value of 10"%opts.loglevel)
    logger.setLevel(int(opts.loglevel))

    chlog = logging.StreamHandler()
    chlog.setLevel(int(opts.loglevel))
    formatter = logging.Formatter('%(levelname)s:%(process)d:%(module)s:%(funcName)s:%(lineno)d:%(message)s')
    chlog.setFormatter(formatter)
    logger.addHandler(chlog)

    temperNTC_master = TemperNTCMaster(opts, logger)
    print "test", temperNTC_master.get_internal_temperature()
    temperNTC_master.TemperNTCMaster()
    sys.exit(0)
