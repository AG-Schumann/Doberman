#! /usr/bin/env python3.3

import serial
from serial import SerialException
import subprocess
import pressureCommand

import os
import time
import logging


class pressureSerial(pressureCommand.pressureCommand):
    """
    Class that holds the pressure controller serial connection. In total analogie to the cryoSerial which holts the cryoCon_22c
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
        self.__ETX = chr(3)  # \x03
        self.__CR = chr(13)
        self.__LF = chr(10)
        self.__ENQ = chr(5)  # \x05
        self.__ACK = chr(6)  # \x06
        self.__NAK = chr(21)  # \x15

        self.opts = opts
        self.logger = logger
        self.vendorID = opts.addresses[1]
        self.productID = opts.addresses[2]
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
        super(pressureSerial, self).__init__(**kwds)
        
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
                    baudrate=38400,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
		    timeout = 1
                )
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
        self.logger.info("The device connection status is: %s",self.__connected)
        return self.__connected
    
    def checkController(self):
        """
        Checks whether the connected device is a pressure controller
        """
        if self.sendMsg("TID") != 0:
            self.logger.warning("No pressure controller connected")
            self.__connected = False
            return -1
        response = ''
        response = self.read()
        if response == -1:
            self.logger.warning("Pressure controller is not answering correctly.")
            self.__connected = False            
            return -2
        self.logger.debug("Device answered: %s",response)
        response = response.split(',')
        if response[0] not in ['TPR','IKR9','IKR11','PKR','PBR','IMR','CMR','noSen','noid']:
            self.logger.warning("Connected device is no pressure controller.")
            self.__connected = False
            return -3
        self.logger.info("Device connected. Attached gauge is %s",self.getGaugeTyp())
        try: #Adding to ttyusb list
            with open(os.path.join(self.opts.path, 'ttyUSB_assignement.txt'),"a+") as f:
                f.write("    %d    |'Pfeiffer pressure controller TPG 61'\n"%self.ttyUSB)
        except Exception as e:
                self.logger.warning("Can not add Pfeiffer pressure controller to 'ttyUSB_assignement.txt'. Error %s"%e)
        finally:
            return 0

    def sendMsg(self, message):
        """
        Send the message to the device
        """
        if not self.__connected:
            self.logger.warning("No controller connected. Cannot send message %s",message)
            return -1
        try:
            message = str(message)+self.__CR+self.__LF           
            self.__device.write(message)
            time.sleep(0.1)
            response = self.__device.readline()
            response = response.rstrip(self.__LF).rstrip(self.__CR)
            if response == self.__NAK:
                logging.warning('Negative acknowledgement for sending a message. Trying again...')
                message = str(message)+self.__CR+self.__LF           
                self.__device.write(message)
                time.sleep(0.1)
                response = self.__device.readline()
                response = response.rstrip(self.__LF).rstrip(self.__CR)
        except serial.SerialException as e:
            self.logger.debug("Can not send Message. Serial exception '%s'."%e) 
            return -1
        if response == self.__NAK:
            logging.warning('Negative acknowledgement for sending a message.')
            return -1
        elif response == '':
            self.logger.debug('No response from controller.')
            self.__device.write(self.__ENQ)
            second_response=self.__device.readline()
            second_response = second_response.rstrip(self.__LF).rstrip(self.__CR)
            if  second_response == '0':
                self.logger.debug('Connected but no acces to controller.')
            else:
                self.logger.error('No response from the controller.')
            return -1
        elif response != self.__ACK:
            self.logger.error('Can not communicate with device. Unknown response.')
            self.logger.debug('Device responded: %s. (The message to the controller was %s)'%(response, message.rstrip(self.__LF).rstrip(self.__CR))) 
            self.stopContinuousMode() 
            return -1
        else:   
            time.sleep(0.1)
            return 0



    def read(self):
        """
        Get data from the Controller. Returns a string
        """
        self.__device.write(self.__ENQ)
        response = self.__device.readline()
        return response.rstrip(self.__LF).rstrip(self.__CR)
        """
        min_sleeptime = 0.01 # seconds
        max_sleeptime = 0.2 # seconds
        sleeptime = min_sleeptime #seconds
        result = ''
        counter = 0
        self.logger.debug("Trying to read data from device...")
        if self.__connected:
            try:
                self.__device.write(self.__ENQ)
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
        return result.rstrip(self.__LF).rstrip(self.__CR)
        """

    def stopContinuousMode(self):
        """
        After the controller is turned off and on again it sends in continous mode. This fuction tries to bring it back to normal communication mode. 
        """
        if self.busy_stopContinuousMode:
            return
        self.busy_stopContinuousMode = True
        counter=0
        self.logger.debug('Try to stop continuous mode...') 
        if counter == 0:
             time.sleep(0.5)         
        while self.checkController() != 0:
            self.__device.flushInput()
            self.__device.flushOutput()
            self.__device.write('TID'+self.__CR+self.__LF)
            self.__device.flushInput()
            self.__device.write('TID'+self.__CR+self.__LF)
            response = self.__device.readline()
            self.logger.debug('Device responded %s during stop continuous mode' %str(response)) 
            response = response.rstrip(self.__LF).rstrip(self.__CR)
            if response == self.__ACK:   
                self.__device.write(self.__ENQ)           
                response = self.__device.readline()
                self.logger.debug('Device responded %s during stop continuous mode' %str(response)) 
                response = response.rstrip(self.__LF).rstrip(self.__CR)  
                response = response.split(',')
                if (response[0] in ['TPR','IKR9','IKR11','PKR','PBR','IMR','CMR','noSen','noid']) and self.__device.inWaiting()==0:
                    self.__connected = True
                    time.sleep(0.5)          
            elif response == self.__NAK:
                self.logger.debug('Negative Acknowledgement, trying again...')                 
                continue
            else:
                counter += 1
            if counter > 10:
                self.logger.debug('Can not regain control by try to stop continuous mode') 
                self.busy_stopContinuousMode = False  
                return    
        self.logger.info("Regained control by stopping continous mode")
        self.busy_stopContinuousMode = False

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
    
    ps = pressureSerial(logger=logger,vendorID=0o711,productID=0o230)
    print('\n\nAs a test I print Error Status, Gauge Control Settings, Pressure Data and Pressure Unit')
    print((ps.getErrorStatus()))
    print((ps.getGaugeControl()))
    print((ps.getPressureData()))
    print((ps.getPressureUnit()))

    print('other stuff')
    print((ps.getTransmissionRate()))

