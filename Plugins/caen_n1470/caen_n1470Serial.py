#! /usr/bin/env python3.3

import serial
import subprocess
import caen_n1470Command

import os
import time
import logging


class caen_n1470Serial(caen_n1470Command.caen_n1470Command):
    """
    Class that holds the caen_n1470 controller serial connection. In total analogie to the cryoSerial which holts the cryoCon_22c
    Don't forget to allow write/read access to usb0:
    - create file: /etc/udev/rules.d/caen_n1470.rules
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
        self._moduleadr = "00" # change if module got another address

        self.__BDname = "N1470"
        self._SN = '1116'

        self.__checkSN = False

        self.logger = logger
        self.opts = opts
        self.productID = self.opts.addresses[1]
        self.vendorID = self.opts.addresses[2]

        if hasattr(self.opts, 'BDname'):
            self.__BDName = self.opts.BDname
        if hasattr(self.opts, 'moduleadr'):
            self._moduleadr = self.opts.moduleadr
        if hasattr(self.opts, 'SN'):
            self._SN = self.opts.SN
            self.__checkSN = True
        self.ttyUSB = -1

        if not hasattr(self.opts, 'occupied_ttyUSB'):
            self.opts.occupied_ttyUSB = []

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
        super(caen_n1470Serial, self).__init__(**kwds)

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
        response = self.communicate("CMD:MON,PAR:BDNAME")
        if isinstance(response, str):
            if self.__BDname in response:
                self.logger.info("Device connected. Name confirmed")
                if self.__checkSN:
                    responseSN = self.communicate("CMD:MON,PAR:BDSNUM")
                    if self._SN in responseSN:
                        self.logger.info("Verifing Seial No of CAEN N1470 HV module: OK")
                        try: #Adding to ttyusb list
                            with open(os.path.join(self.opts.path, 'ttyUSB_assignement.txt'),"a+") as f:
                                f.write("    %d    |'caen_n1470'\n"%self.ttyUSB)
                        except Exception as e:
                            self.logger.warning("Can not add caen_n1470 to 'ttyUSB_assignement.txt'. Error %s"%e)
                        finally:
                            return 0
                    else:
                        self.logger.warning("Verifing Seial No of CAEN N1470 HV module: FAIL. Serial No is: %s."%responseSN)
                        self.__connected = False
                        return -1
                else:
                    try: #Adding to ttyusb list
                        with open(os.path.join(self.opts.path, 'ttyUSB_assignement.txt'),"a+") as f:
                            f.write("    %d    |'caen_n1470'\n"%self.ttyUSB)
                    except Exception as e:
                        self.logger.warning("Can not add caen_n1470 to 'ttyUSB_assignement.txt'. Error %s"%e)
                    finally:
                        return 0
        elif response == -1:
            self.logger.warning("CAEN N1470 controller is not answering correctly.")
            self.__connected = False 
            return -2
        else:
            self.__connected = False
            self.logger.debug("Unknown response. Device answered: %s",response)
            return -3
    
    def communicate(self, message):
        """
        Send the message to the device and reads the response
        The format for sending is: "$BD:**,CMD:***,CH*,PAR:***,VAL:***.**\r\n":
        The fields that form the command are :
            BD : 0..31 module address (to send the command)
            CMD : MON, SET
            CH : 0..4 (4 for the commands related to all Channels)
            PAR : (see parameters tables)
            VAL : (numerical value must have a Format compatible with resolution and range)
        The answer has a format "#BD:00,CMD:OK,VAL:1116\r\n" . \r\n are removed automaticelly
        """
        if not self.__connected:
            self.logger.warning("No controller connected. Cannot send message %s",message)
            return -1
        try:
            message = '$BD:'+str(self._moduleadr)+','+str(message)+self.__CR+self.__LF
            self.__device.write(message)

            response = (self.__device.readline())
            response = response.rstrip(self.__LF).rstrip(self.__CR)

        except serial.SerialException as e:
            self.logger.debug("Can not send Message. Serial exception '%s'."%e) 
            return -1

        if response == '':
            self.logger.debug('No response from controller.')
            return -1

        elif response[7:] == 'CMD:ERR':
            self.logger.warning("Wrong command Format or command not recognized, send command: %s"%message)
            return -1
        elif response[7:] == 'CH:ERR':
            self.logger.warning("Channel Field not present or wrong Channel value, send command: %s"%message)
            return -1
        elif response[7:] == 'PAR:ERR':
            self.logger.warning("Field parameter not present or parameter not recognized, send command: %s"%message)
            return -1
        elif response[7:] == 'VAL:ERR':
            self.logger.warning("Wrong set value (<Min or >Max), send command: %s"%message)
            return -2
        elif response[7:] == 'LOC:ERR':
            self.logger.warning("Command SET with module in LOCAL mode, send command: %s"%message)
            return -1
        else:   
            time.sleep(0.05)
            return response[18:]

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
    
    iser = caen_n1470Serial(logger)
    print('\n\nAs a test I print some values')
    print((iser.getSN()))
    print((iser.getPolarity(0)))
    print((iser.getFWRel()))
    print((iser.getControlMode(1)))
