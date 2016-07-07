#! /usr/bin/env python3.3

import serial
import subprocess
import itc503command

import os
import time
import logging


class itc503Serial(itc503command.itc503Command):
    """
    Class that holds the oxford itc 503 controller serial connection.
    Don't forget to allow write/read access to usb0:
    - create file: /etc/udev/rules.d/oxford_itc503.rules
    - write in it (without quotation marks):
    "# USB card access rights for reading and writing
    ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", OWNER=="basho", GROUP="basho", MODE="0661"
    - change the ttyusb if necessary
    -run:
    sudo udevadm trigger
    sudo reload udev
    """
    def __init__(self, opts, logger, **kwds):
        self.logger = logger
        self.opts = opts
        self.vendorID = None
        self.productID = None
        if not self.opts is None:
            self.productID = self.opts.addresses[1]
            self.vendorID = self.opts.addresses[2]
        else:
            self.vendorID = kwds['vendorID']
            self.productID = kwds['productID']

        self.ttyUSB = -1
        try: #Reading which ports are already occupied.
            with open(os.path.join(opts.path, 'ttyUSB_assignement.txt'),"r") as f:
                self.occupied_ttyUSB = []
                for line in f:
                    ttyUSB_line =line.split()[0]
                    if ttyUSB_line == '#':
                        continue
                    else:
                        self.occupied_ttyUSB.append(int(ttyUSB_line))
        except Exception as e:
            if not self.opts is None:
                self.logger.warning("Can not read 'ttyUSB_assignement.txt'. Error %s. Continue with only the predifined occupied ports (%s). This might disturb an other controller."%(e,str(opts.occupied_ttyUSB)))
                self.occupied_ttyUSB = opts.occupied_ttyUSB
            else:
                self.occupied_ttyUSB = []

        self.__connected = False
        super(itc503Serial, self).__init__()
        self.__device = self._getControl()
        if not self.__device.isOpen():
            self.__device.open()
        if self.__device.isOpen():            
            self.__connected = True
        self.busy_stopContinuousMode = False # used so that the function stop continous mode can only be executed once at the time
        self.__device.flush()
        self.__device.flushInput()
        self.__device.flushOutput()
        self.logger.debug("Port In- and Output flushed.")
        time.sleep(0.1)
        counter = 0
        while self.checkController() != 0:
            self.__device = self._getControl(True)
            counter += 1
            if counter > 3:
                self.logger.fatal("Exceeded maximum connection tries to serial device. Haven't found a pressure controller")
                self.__connected = False
                self.close()
                break
            time.sleep(0.1)

    def _getControl(self, nexttty = False):
        """
        connect the controller (/dev/ttyUSBn)
        """
        connected = False
        port = None
        if not nexttty:
            self.ttyUSB = -1
        while not connected:
            self.ttyUSB = self.get_ttyUSB(self.vendorID,self.productID, start_ttyUSB=self.ttyUSB+1)
            if self.ttyUSB == -1:    
                try:
                    dev = subprocess.Popen(["which_tty_controller"], stdout=subprocess.PIPE).communicate()[0]
                except OSError:
                    which_tty_controller = os.path.abspath('which_tty_controller')
                    if not os.path.exists(which_tty_controller):
                        raise OSError("Can not find binary which_tty_controller")
                    dev = subprocess.Popen([which_tty_controller], stdout=subprocess.PIPE).communicate()[0]
                dev = "/dev/" + dev.decode()
                dev = dev.rstrip('\n')
                self.logger.info("Device found at %s. Trying to connect to it...",dev)
            else:
                dev = '/dev/ttyUSB'+str(self.ttyUSB)
            try:
                port = serial.Serial(port=dev, baudrate=9600, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout = 0.7)
                connected = True
            except serial.SerialException as e:
                connected = False
                self.logger.error(e)
                self.logger.error("Waiting 5 seconds")
                time.sleep(1)
        self.__connected = True
        self.logger.info("Successfully connected to controller via serial port.")
        return port

    def get_ttyUSB(self,vendor_ID,product_ID, start_ttyUSB = 0):
        '''
        Retruns the ttyUSB which the device with given ID is connected to, by looking throung the ttyUSB 0 to 4 and comparing IDs.
        Use start_port if you do not want to start at port 0, eg. if there is a other controller with same ID found before
        '''
        if start_ttyUSB >= 10:
            self.logger.debug("Start port too high, set back to 0")
            start_ttyUSB = 0
        for ttyport in range(start_ttyUSB,10):
            if ttyport in self.occupied_ttyUSB:
                self.logger.debug("ttyUSB%d is already occupied."%ttyport)
                continue
            self.logger.debug("Searching in ttyUSB%s ..."%ttyport)
            tty_Vendor = os.popen("udevadm info -a -p  $(udevadm info -q path -n /dev/ttyUSB%d) | grep 'ATTRS{idVendor}=="%(ttyport) + '"%s"'%str(vendor_ID) + "'").readlines()
            tty_Product = os.popen("udevadm info -a -p  $(udevadm info -q path -n /dev/ttyUSB%d) | grep 'ATTRS{idProduct}=="%(ttyport) + '"%s"'%str(product_ID) + "'").readlines() 
            if (tty_Vendor != [] and tty_Product != []):
                self.logger.info("Device with vendorID = '%s' and productID = '%s' found at ttyUSB%d"%(vendor_ID, product_ID,ttyport))
                return ttyport
        self.logger.warning("Device with vendorID = '%s' and productID = '%s' NOT found at any ttyUSB"%(vendor_ID, product_ID))       
        return -1
  
    def connected(self):
        """
        Returns the connection status of the controller.
        """
        self.logger.info("The device connection status is: %s",self.__connected)
        return self.__connected

    def checkController(self):
        """
        Checks whether the connected device is a itc503 controller.
        """
        if self.sendMsg("V") != 0:
            self.logger.warning("No itc503 controller connected")
            self.__connected = False
            return -1
        response = self.read()
        if response == -1:
            self.logger.warning("ITC503 controller is not answering.")
            self.__connected = False            
            return -2
        self.logger.debug("Device answered: %s",response)
        if not 'ITC503' in response and not 'OXFORD' in response:
            self.logger.warning("Connected device is no oxford itc503 controller.")
            self.__connected = False
            return -3
        self.logger.info("ITC503 connected.")
        try: #Adding to ttyusb list
            with open(os.path.join(self.opts.path, 'ttyUSB_assignement.txt'),"a+") as f:
                f.write("    %d    |'Oxford ITC503'\n"%self.ttyUSB)
        except Exception as e:
                self.logger.warning("Can not add Oxford ITC503 controller to 'ttyUSB_assignement.txt'. Error %s"%e)
        finally:
            return 0

    def sendMsg(self, message):
        """
        Send the message to the device
        """
        if not self.__connected:
            self.logger.warning("No controller connected. Cannot send message %s",message)
            return -1
        self.__device.flush()
        self.__device.flushInput()
        self.__device.flushOutput()
        message = str(message).rstrip('\n').rstrip()
        self.logger.debug("Sending message: %s to device..."%(message+'\r\n').encode('utf-8'))
        self.__device.write((message+'\r\n').encode('utf-8'))
        time.sleep(0.15)
        return 0

    def read(self):
        """
        Get data from the Controller. Returns a string
        """
        min_sleeptime = 0.05 # seconds
        max_sleeptime = 0.9 # seconds
        sleeptime = min_sleeptime #seconds
        result = ''
        counter = 0
        self.logger.debug("Trying to read data from device...")
        while result == '':
            counter += 1
            if self.__connected:
                try:
                    if self.__device.inWaiting():
                        while self.__device.inWaiting():
                            result = result+self.__device.readline().strip().decode()
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
            if counter > 4:
                self.logger.error("IOError. Exceeded maximum amounts of reconnections...")
                return -1
            self.__device.flush()
            self.__device.flushInput()
            self.__device.flushOutput()
        else:
            self.__device.flush()
            self.__device.flushInput()
            self.__device.flushOutput()
            self.logger.debug("Got data from device: %s",result.rstrip())
            return result.rstrip()

    def close(self):
        """
        call this to properly close the serial connection to the itc503 controller
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
    crs = itc503Serial(None, logger, vendorID = '0403', productID = '6001')
