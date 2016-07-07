#! /usr/bin/env python3.3

import socket
import subprocess
import cryoCommand

import os
import time
import logging


class cryoLAN(cryoCommand.cryoCommand):
    """
    Class that holds the cryo controller LAN connection.
    """
    def __init__(self, logger, address, port,**kwds):
        self.logger = logger
        self.__connected = False
        self.__address = str(address)
        self.__port = int(port)
        super(cryoLAN, self).__init__(**kwds)
        
        self.__device = self._getControl()
        if self.__device is None:
            self.logger.fatal("No device found here: %s at port %i. Maximum number of connection tries exceeded..."%(self.__address, self.__port))
            self.close()
            return
        if self.checkController() != 0:
            self.__connected = False
            self.__device = self._getControl()
            if self.__device is None:
                self.logger.fatal("No device found here: %s at port %i. Maximum number of connection tries exceeded..."%(self.__address, self.__port))
                self.close()
                return
            

    def _getControl(self):
        """
        initiate the connection to the controller. Make sure that address and port are set correctly. Should not be called directly
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tconn = 0
        while not self.__connected and tconn < 5:
            tconn += 1
            try:
                sock.connect((self.__address, self.__port))
                self.__connected = True
                self.logger.info("Successfully connected to controller via lan address: %s at port: %i."%(self.__address, self.__port))
            except socket.error as e:
                self.logger.fatal("No device found here: %s at port %i. Trying again in 5 s..."%(self.__address, self.__port))
                self.__connected = False
                sock.close()
                sock = None
                time.sleep(5)
        return sock

    def connected(self):
        """
        Returns the connection status.
        """
        self.logger.info("The device connection status is: %s",self.__connected)
        return self.__connected

    def checkController(self):
        """
        Checks whether the connected device is actually a cryo controller.
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
        if not 'Cryo-con,22C,' in response:
            self.logger.warning("Connected device is no cryo-con 22C controller.")
            self.__connected = False
            return -3
        self.logger.info("Device connected. %s",self.getInstrumentName())
        return 0

    def sendMsg(self, message):
        """
        Send the message to the device.
        """
        if not self.__connected:
            self.logger.error("No controller connected. Cannot send message %s",message)
            return -1
        message = str(message).rstrip('\n').rstrip()
        try:
            self.__device.sendall((message+'\n').encode('utf-8'))
        except socket.error as e:
            self.logger.fatal("Lost Connection. Reconnecting was not successfull. %s"%(e))
            return -1
        time.sleep(0.01)
        return 0

    def read(self):
        """
        Get data from the Controller. Returns a string
        """
        result = ''
        self.logger.debug("Trying to read data from device...")
        if self.__connected:
            try:
                # TODO : check for data, can take a while if none there, what to do?
                result = self.__device.recv(1024).decode().rstrip('\r\n').rstrip()
            except socket.error as e:
                self.logger.fatal("Lost Connection. Reconnecting was not successfull. Error: %s"%(e))
                return -1
        self.logger.debug("Got data from device: %s",result.rstrip())
        return result.rstrip()

    def close(self):
        """
        call this to properly close the lan connection to the cryo controller
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
    crs = cryoLAN(logger,'192.168.1.5',5001)
    print('A')
    print(crs.getTemp('A'))
    print('A')
    print(crs.getTemp('A'))
    print('A')
    print(crs.getTemp('A'))
    print('B')
    print(crs.getTemp('B'))
    print('B')
    print(crs.getTemp('B'))
    print('B')
    print(crs.getTemp('B'))
    print('A')
    print(crs.getTemp('A'))
    print('A')
    print(crs.getTemp('A'))
    print('A')
    print(crs.getTemp('A'))
