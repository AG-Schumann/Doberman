#! /usr/bin/env python3.3

import serial
import subprocess
import scaleCommand

import os
import time
import logging


class scaleSerial(scaleCommand.scaleCommand):
    """
    Class that holds the scale serial connection. In total analogy to the cryoSerial which holts the cryoCon_22c
    Don't forget to allow write/read access to usb0:
    - create file: /etc/udev/rules.d/pfeiffer.rules
    - write in it:
    # USB Karte fuer Lese&Schreibzugriff freischalten
    ATTRS{idVendor}=="0557", ATTRS{idProduct}=="2008", OWNER=="lhep", GROUP="lhep", MODE="0661"
    - change the ttyusb if necessary
    -run:
    sudo udevadm trigger
    sudo reload udev
    """
    def __init__(self, opts, logger, **kwds):  
        self.__startcharakter = "*"  #Startcharakter may change if manualy set another   
        self.__CR = chr(13)
        self.__LF = chr(10)

        self._ID = '0000' # ID may be manually changed, be careful. Also change here! 

        self.logger = logger
        self.productID = opts.addresses[1]
        self.vendorID = opts.addresses[2]
        self.opts = opts
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
            self.logger.warning("Can not read 'ttyUSB_assignement.txt'. Error %s. Continue with only the predifined occupied ports (%s). This might disturb an other controller."%(e,str(opts.occupied_ttyUSB)))
            self.occupied_ttyUSB = opts.occupied_ttyUSB

        self.__connected = False
        super(scaleSerial, self).__init__(**kwds)

        self.__device = self._getControl()
        if not self.__device.isOpen():
            self.__device.open()
        if self.__device.isOpen():            
            self.__connected = True
       
        counter = 0
        
        while self.checkController() != 0:
            self.__device = self._getControl(True)
            counter += 1
            if counter > 3:
                self.logger.fatal("Exceeded maximum connection tries to serial device. Haven't found a pressure controller")
                self.__connected = False
                self.close()
                break


    def _getControl(self, nexttty = False):
        """
        connect controller (/dev/ttyUSBn)
        """
        # TODO : need to check behaviour of which tty script vs multiple serial devices, just wanna get the next one if multiple connected
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
                port = serial.Serial(
                    port=dev,
                    baudrate=9600,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout = 5
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
    
    def get_ttyUSB(self,vendor_ID,product_ID):
        '''
        Retruns the ttyUSB which the device with given ID is connected to, by looking throung the ttyUSB 0 to 4 and comparing IDs
        '''
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
        self.logger.info("The device connection status is: %s",self.__connected)
        return self.__connected
    
    def checkController(self):
        """
        Checks whether the connected device is a scale
        """
        resp = ''
        resp = self.communicate("@")
        if resp != 'test':
            self.logger.info("Device connected.")
            try: #Adding to ttyusb list
                with open(os.path.join(self.opts.path, 'ttyUSB_assignement.txt'),"a+") as f:
                    f.write("    %d    |'scale'\n"%self.ttyUSB)
            except Exception as e:
                self.logger.warning("Can not add scale to 'ttyUSB_assignement.txt'. Error %s"%e)
            finally:
                return 0
        elif resp == -1:
            self.logger.warning("scale is not answering correctly.")
            self.__connected = False 
            return -1

        elif  resp != self._ID and len(resp) == 4:
            self.logger.warning("ID not correct. Not the matching controller connected (Check ID on controller to make sure. Shold be '%s' is '%s')"%(self._ID,resp))
            self.__connected = False
            return -2

        else:
            self.logger.debug("Unknown response. Device answered: %s",resp)
            return -3
    
    def communicate(self, message):
        """
        Send the message to the device and reads the response
        """
        if not self.__connected:
            self.logger.warning("No scale connected. Cannot send message %s",message)
            return -1
        try:
            message = str(message)
            self.__device.write(message)
            resp = ''
            time.sleep(0.3)
            while self.__device.inWaiting() > 0:
                resp += self.__device.read(1)

        except serial.SerialException as e:
            self.logger.debug("Can not send Message. Serial exception '%s'."%e) 
            return -1
 
        time.sleep(0.1)
        return resp

    def read(self):
        """
        For continuous mode only. Otherways use self.communicate
        """
        resp = self.__device.readline()
        return resp

    def close(self):
        """
        call this to properly close the serial connection to the scale
        """
        self.__connected = False
        self.__device.close()
        return
        #raise SystemExit("Closed pressure serial")

    def __del__(self):
        self.close()
        return
    
    def __exit__(self):
        self.close()
        return

    def greet(self):
        """
        Establishes connection by sending '@'
        """
        message = '@'
        self.communicate(message)
        return

    def setSlow(self):
        """
        Switches to slow mode
        """
        message = 's'	
        self.communicate(message)
        return

    def setFast(self):
        """
        Switches to fast mode
        """
        message = 'f'	
        self.communicate(message)
        return

    def setMode(self, mode):
        """
        Sets measurement mode between mode 0 and mode 4
        """
        self.communicate(mode)
        return

    def powerDown(self):
        """
        Powers down the scale
        """
        message = 'p'
        self.communicate(message)
        return

    def measure(self):
        """
        Starts a measurement cycle and calculates final value
        """
        resp = self.communicate('')
        if resp == '':
            return -1
        resp = resp.split('\n')
        weight = resp[-2]
        weight1 = weight[:-4]
        weight2 = float(weight1)
        return weight2



if __name__ == '__main__':
    import os
    import time
    import logging
    logging.basicConfig()
    logger = logging.getLogger()
    logger.setLevel(10)
    
    scales = scaleSerial(logger)
    print('\n\nAs a test I print ID, Address, Communication Parameters, Setpoint1 and current value')
    print(scales.getID())
    print(scales.getAddress())
    print(scales.getCommunicationParameters())
    print(scales.getSetpoint(1))
    print(scales.getDisplayedValue())

