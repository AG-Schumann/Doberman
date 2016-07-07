#! /usr/bin/env python3.3

import serial
import subprocess
import TeledyneCommand

import os
import time
import logging

class TeledyneSerial(TeledyneCommand.TeledyneCommand):
    """
    Class that holds the Teledyne flow controller THCD-100 serial connection. In total analogie to the cryoSerial which holts the cryoCon_22c
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
        self.__CR = chr(13)
        self.__LF = chr(10)

        self.__AddressLetter = 'a' #Addressletter can be changed manually on the controller (a-h), default = a
        self.opts = opts
        self.logger = logger
        self.vendorID = self.opts.addresses[2]
        self.productID = self.opts.addresses[1]
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

        super(TeledyneSerial, self).__init__(**kwds)
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
                self.logger.fatal("Exceeded maximum connection tries to serial device. Haven't found a pressure controller")
                self.__connected = False
                self.close()
                break

    def _getControl(self, nexttty = False):
        """
        connect controller (/dev/ttyUSBn)
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
        Checks whether the connected device is a pressure controller
        """
        response = ''
        response = self.communicate("add?")
        if response in [-1,-2,-3]:
            self.logger.warning("Teledyne flow controller is not answering correctly.")
            self.__connected = False 
            return -1
        if response[1] == 'ADDR: %s'%self.__AddressLetter: 
            self.logger.info("Device connected. Address letter confirmed")
            try: #Adding to ttyusb list
                with open(os.path.join(self.opts.path, 'ttyUSB_assignement.txt'),"a+") as f:
                    f.write("    %d    |'Teledyne flow controller THCD-100'\n"%self.ttyUSB)
            except Exception as e:
                self.logger.warning("Can not add Teledyne to 'ttyUSB_assignement.txt'. Error %s"%e)
            finally:
                return 0
        else:
            self.logger.debug("Unknown response. Device answered: %s",response)
            return -3
    
    def communicate(self, message):
        """
        Send the message to the device and reads the response
        Message format is ("accc[?][arg]\r\n") 
        where a is the address letter, ccc the 1-3 letter command, ? the query identification, arg is the comma separated parameter list 
        \r\n are removed automaticelly
        """
        if not self.__connected:
            self.logger.warning("No controller connected. Cannot send message %s",message)
            return -1
        try:
            if self.__device.inWaiting() != 0:
                self.logger.debug("There is information on the input which will be lost as input will be flushed in order to communicate properly.")
                self.__device.flushInput()

            message = self.__AddressLetter + str(message) + self.__CR + self.__LF           
            self.__device.write(message)
            time.sleep(0.1)
            response=[]
            while self.__device.inWaiting() != 0:
                response_line = self.__device.readline()
                response_line = response_line.rstrip(self.__LF).rstrip(self.__CR)
                response.append(response_line)
                if len(response) >3:
                    self.logger.debug("Answer longer than 3 lines. Only 3 lines are returned.")
                    break
        except serial.SerialException as e:
            self.logger.debug("Can not send Message. Serial exception '%s'."%e) 
            return -1
        if response == []:
            self.logger.debug('No response from controller.')
            return -1
        if len(response) < 2:
            self.logger.debug('Response too short (%s)'%str(response))
            return -1
        if str(response[0][4:7]) != str(message[1:4]):
            self.logger.debug("Wrong echo on message: message = %s, echo = %s, expected = %s"%(message,response[0][4:7], message[1:4]))
            return -2

        #Check last line if transmission was okey
        if response[-1] != '!%s!o!'%self.__AddressLetter:
            if response[-1] == '!%s!w!'%self.__AddressLetter:
                self.logger.debug("Device busy, could not answer. Message was %s."%message)
                return -2
            elif response[-1] == '!%s!e!'%self.__AddressLetter:
                self.logger.debug("Syntax error in message (%s)."%message)
                return -2
            elif response[-1] == '!%s!b!'%self.__AddressLetter:
                self.logger.debug("Message (%s) was not recognized or has incorrect/invalid parameters."%message)
                return -2
            else:
                self.logger.debug("Unknown status of response:%s"%response[-1])
                return -2
        else:
            response[-1] = '0'

        time.sleep(0.1)
        return response

    def read(self):
        """
        For continuous mode only. Otherways use self.communicate
        """
        response = self.__device.readline()
        return response.rstrip(self.__LF).rstrip(self.__CR)

    def close(self):
        """
        call this to properly close the serial connection to the pressure controller
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

if __name__ == '__main__':
    import os
    import time
    import logging
    logging.basicConfig()
    logger = logging.getLogger()
    logger.setLevel(10)
    
    Td = TeledyneSerial(logger,'0557','2008',)
    print('\n\nAs a test I print: Address letter, Setpoint mode, current data, current unit')
    print(Td.getAddressLetter())
    print(Td.getSetpointMode())
    print(Td.readData())
    print(Td.getUnit())


