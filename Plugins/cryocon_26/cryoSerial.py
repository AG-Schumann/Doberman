#! /usr/bin/env python3.3

import serial
import subprocess
import cryoCommand

import os
import time
import logging


class cryoSerial(cryoCommand.cryoCommand):
    """
    Class that holds the cryo controller serial connection.
    Don't forget to allow write/read access to usb0:
    - create file: /etc/udev/rules.d/cryocon.rules
    - write in it (without quotation marks):
    "# USB card access rights for reading and writing
    ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", OWNER=="basho", GROUP="basho", MODE="0661"
    - change the ttyusb if necessary
    -run:
    sudo udevadm trigger
    sudo reload udev
    """
    def __init__(self, logger, **kwds):
        self.logger = logger
        self.__connected = False
        super(cryoSerial, self).__init__(**kwds)

        self.__device = self._getControl()
        if not self.__device.isOpen():
            self.__device.open()
        if self.__device.isOpen():            
            self.__connected = True
        counter = 0
        while self.checkController() != 0:
            self.__device = self._getControl(True)
            counter += 1
            if counter > 5:
                self.logger.fatal("Exceeded maximum connection tries to serial device. Haven't found a cryo controller")
                self.__connected = False
                self.close()
                break


    def _getControl(self, nexttty = False):
        """
        connect the controller (/dev/ttyUSBn)
        """
        # TODO : need to check behaviour of which tty script vs multiple serial devices, just wanna get the next one if multiple connected
        connected = False
        port = None
        while not connected:
            try:
                dev = subprocess.Popen(["which_tty_controller"], stdout=subprocess.PIPE).communicate()[0]
            except OSError:
                which_tty_controller = os.path.abspath('which_tty_controller')
                if not os.path.exists(which_tty_controller):
                    raise OSError("Can not find binary which_tty_controller")
                dev = subprocess.Popen([which_tty_controller], stdout=subprocess.PIPE).communicate()[0]
            dev = "/dev/" + dev.decode()
            dev = dev.rstrip('\n')
            self.logger.info("Device found at %s \n trying to connect to the controller...",dev)
            try:
                port = serial.Serial(
                    port=dev,
                    baudrate=9600,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                )
                connected = True
            except serial.SerialException as e:
                connected = False
                self.logger.error(e)
                self.logger.error("Waiting 5 seconds")
                time.sleep(5)
        self.__connected = True
        self.logger.info("Successfully connected to controller via serial port.")
        return port
    
    def connected(self):
        """
        Returns the connection status of the controller.
        """
        self.logger.info("The device connection status is: %s",self.__connected)
        return self.__connected

    def checkController(self):
        """
        Checks whether the connected device is a cryo controller.
        """
        if self.sendMsg("*IDN?") != 0:
            self.logger.warning("No cryo controller connected")
            self.__connected = False
            return -1
        response = self.read()
        if response == -1:
            self.logger.warning("Cryo controller is not answering.")
            self.__connected = False            
            return -2
        self.logger.debug("Device answered: %s",response)
        if not 'Cryo-con,26,' in response:
            self.logger.warning("Connected device is no cryo-con 26 controller.")
            self.__connected = False
            return -3
        self.logger.info("Device connected. %s",self.getInstrumentName())
        return 0

    def sendMsg(self, message):
        """
        Send the message to the device
        """
        if not self.__connected:
            self.logger.warning("No controller connected. Cannot send message %s",message)
            return -1
        message = str(message).rstrip('\n').rstrip()
        self.__device.write((message+'\n').encode('utf-8'))
        time.sleep(0.1)
        return 0

    def read(self):
        """
        Get data from the Controller. Returns a string
        """
        min_sleeptime = 0.01 # seconds
        max_sleeptime = 0.2 # seconds
        sleeptime = min_sleeptime #seconds
        result = ''
        counter = 0
        self.logger.debug("Trying to read data from device...")
        if self.__connected:
            try:
                if self.__device.inWaiting():
                    while self.__device.inWaiting():
                        result = result+self.__device.readline().strip().decode()+'\n'
                    sleeptime = max(sleeptime/2, min_sleeptime)
                else:
                    sleeptime = min(1.5 * sleeptime, max_sleeptime)
                time.sleep(sleeptime)
            except IOError:
                counter += 1
                self.logger.error("IOError. Trying to reconnect device...")
                self.__device.close()
                self.__device = self._getControl()
            except OSError:
                counter += 1
                self.logger.error("IOError. Trying to reconnect device...")
                self.__device.close()
                self.port = self._getControl()
            if counter > 3:
                self.logger.error("IOError. Exceeded maximum amounts of reconnections...")
                return -1
        self.logger.debug("Got data from device: %s",result.rstrip())
        return result.rstrip()

    def close(self):
        """
        call this to properly close the serial connection to the cryo controller
        """
        self.__connected = False
        self.__device.close()
        return

    def __del__(self):
        self.close()
        return
    
    def __exit__(self):
        self.close()
        return


if __name__ == '__main__':
    import os
    import time
    import logging
    logging.basicConfig()
    logger = logging.getLogger()
    logger.setLevel(10)
    crs = cryoSerial(logger)
    print('A')
    print((crs.getTemp('A')))
    print('A')
    print((crs.getTemp('A')))
    print('A')
    print((crs.getTemp('A')))
    print('B')
    print((crs.getTemp('B')))
    print('B')
    print((crs.getTemp('B')))
    print('B')
    print((crs.getTemp('B')))
    print('A')
    print((crs.getTemp('A')))
    print('A')
    print((crs.getTemp('A')))
    print('A')
    print((crs.getTemp('A')))
