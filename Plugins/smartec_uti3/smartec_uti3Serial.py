#! /usr/bin/env python3.3

import serial
import subprocess
from subprocess import Popen, PIPE, TimeoutExpired
import smartec_uti3Command
import smartec_uti3Config

import os
import time
import logging


class smartec_uti3Serial(smartec_uti3Command.smartec_uti3Command):
    """
    Class that holds the uti transducer serial connection. In total analogy to the cryoSerial which holts the cryoCon_22c
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
        #self.serialNumber = opts.addresses[3]
        self.serialNumber = 'DN01NAMY'
        self.opts = opts
        self.ttyUSB = -1
        self.mode = smartec_uti3Config.mode
        self.ref = smartec_uti3Config.ref
        self.bridgeref = smartec_uti3Config.bridgeref
        self.output = smartec_uti3Config.output
        self.wire = smartec_uti3Config.wire

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
        super(smartec_uti3Serial, self).__init__(**kwds)

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
        try:
            self.greet()
            self.setMode(self.mode)
            self.setSlow()
        except Exception as e:
            self.logger.error('Tried initializing device, failed: %s' % e)


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
            #self.ttyUSB = self.get_ttyUSB(self.vendorID,self.productID, start_ttyUSB=self.ttyUSB+1)
            self.ttyUSB = self.get_ttyUSB(serial_number=self.serialNumber)
            if self.ttyUSB == -1:
                try:
                    dev = subprocess.Popen(["which_tty_controller"], stdout=subprocess.PIPE).communicate()[0]
                except OSError:
                    which_tty_controller = os.path.abspath('which_tty_controller')
                    print(("*** OSError:  path to 'which_tty_controller': ", which_tty_controller, "  ****"))
                    if not os.path.exists(which_tty_controller):
                        raise OSError("Can not find binary which_tty_controller")
                    dev = subprocess.Popen([which_tty_controller], stdout=subprocess.PIPE).communicate()[0]
                dev = "/dev/" + dev.decode()
                dev = dev.rstrip('\n')
                self.logger.info("Device found at %s. Trying to connect to it...",dev)
            else:
                dev = '/dev/ttyUSB'+str(self.ttyUSB)

            if self.ttyUSB in self.occupied_ttyUSB:
                self.logger.info('ttyUSB%i is already occupied? We\'ll try it anyway...' % self.ttyUSB)
            else:
                self.logger.debug('Connecting to ttyUSB%i' % self.ttyUSB)
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

    def get_ttyUSB(self, serial_number):
        '''
        Returns the ttyUSB which the device with given serial is connected to, by looking through dmesg
        '''
        self.logger.debug('Looking for USB device with serial %s' % serial_number)
        proc = Popen('dmesg | grep %s | tail -n 1' % serial_number, shell=True, stdout=PIPE, stderr=PIPE)
        try:
            out, err = proc.communicate(timeout=10)
        except TimeoutExpired:
            self.logger.error('Timed out while looking for serial device')
            proc.kill()
            out, err = proc.communicate()
        if len(err) or not len(out):
            self.logger.error('Error looking for serial device. Stdout: %s. Stderr: %s' % (out.decode(), err.decode()))
            return -1
        usbid = out.decode().split()[3]
        proc = Popen('dmesg | grep %s | grep -o "ttyUSB[0-9]"' % usbid, shell=True, stdout=PIPE, stderr=PIPE)
        try:
            out, err = proc.communicate(timeout=10)
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        if len(err) or not len(out):
            self.logger.error('Could not find USB device, stdout: %s, stderr: %s' % (out.decode(), err.decode()))
            return -1
        tty_ID = out.decode()[-2] # [-1] is \n
        return int(tty_ID)
        """
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
            tty_ID = os.popen("udevadm info -a -n /dev/ttyUSB%d | grep '{serial}' | head -n1"%(ttyport)).readline()
            if (tty_Vendor != [] and tty_Product != [] and tty_ID == "    ATTRS{serial}==\"DN01NAM1\"\n"):
                self.logger.info("Device with vendorID = '%s' and productID = '%s' and serialID = 'DN01NAM1' found at ttyUSB%d"%(vendor_ID, product_ID,ttyport))
                return ttyport
        self.logger.warning("Device with vendorID = '%s' and productID = '%s' and serialID = 'DN01NAM1' NOT found at any ttyUSB"%(vendor_ID, product_ID))
        return -1

        """
    def connected(self):
        self.logger.info("The device connection status is: %s",self.__connected)
        return self.__connected

    def checkController(self):
        """
        Checks whether the connected device is a uti transducer
        """
        resp = ''
        resp = self.communicate("@")
        if resp != 'test':
            self.logger.info("Device connected.")
            try: #Adding to ttyusb list
                with open(os.path.join(self.opts.path, 'ttyUSB_assignement.txt'),"a+") as f:
                    f.write("    %d    |'uti transducer'\n"%self.ttyUSB)
            except Exception as e:
                self.logger.warning("Can not add uti transducer to 'ttyUSB_assignement.txt'. Error %s"%e)
            finally:
                return 0
        elif resp == -1:
            self.logger.warning("uti transducer is not answering correctly.")
            self.__connected = False
            return -1

        elif  resp != self._ID and len(resp) == 4:
            self.logger.warning("ID not correct. Not the matching controller connected (Check ID on controller to make sure. Should be '%s' is '%s')"%(self._ID,resp))
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
            self.logger.warning("No transducer connected. Cannot send message %s",message)
            return -1
        try:
            message = str(message)
            self.__device.write(message.encode())
            resp = ''
            time.sleep(0.3)
            bytes_to_read = self.__device.inWaiting()
            if bytes_to_read:
                resp = self.__device.read(bytes_to_read).decode()
            #while self.__device.inWaiting() > 0:
            #    resp += self.__device.read(1).decode()

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
        call this to properly close the serial connection to the uti transducer
        """
        #self.powerDown()
        self.logger.debug('Shutting down...')
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
        self.logger.debug('We come in peace')
        self.communicate(message)
        return

    def setSlow(self):
        """
        Switches to slow mode
        """
        message = 's'
        self.logger.debug('Setting slow...')
        self.communicate(message)
        return

    def setFast(self):
        """
        Switches to fast mode
        """
        message = 'f'
        self.logger.debug('Setting fast...')
        self.communicate(message)
        return

    def setMode(self, mode):
        """
        Sets measurement mode between mode 0 and mode 4
        """
        self.logger.debug('Setting mode %s...' % self.mode)
        self.communicate(mode)
        return

    def powerDown(self):
        """
        Powers down the uti transducer. Note that you have to power-cycle
        the board (unplug + replug) to bring it back online
        """
        message = 'p'
        self.logger.debug('Powering down...')
        self.communicate(message)
        return

    def measure(self):
        """
        Starts a measurement cycle and calculates final value
        """
        try:
            self.communicate(self.mode)
            time.sleep(0.1)
            resp = self.communicate("m")
            if resp == '':
                return -1
            resp = resp.split()
            valuea = int(resp[0],16)
            valueb = int(resp[1],16)
            valuec = int(resp[2],16)
            if len(resp) >= 4:
                valued = int(resp[3],16)
            if len(resp) == 5:
                valuee = int(resp[4],16)
            resp = []
            if self.mode == 'D' or self.mode == 'E':
                if valuee == valuea:
                    resp.append(0.0)
                else:
                    resp.append((valuec-valuea)/(valuee-valuea*1.0)*self.bridgeref)
                if valued == valuea:
                    resp.append(0.0)
                else:
                    resp.append((valueb-valuea)/(valued-valuea*1.0)*self.ref)
                return resp
            if self.wire == 3:
                if valueb == valuea:
                    resp.append(0.0)
                else:
                    resp.append((valuec-valued)/(valueb-valuea*1.0))
            else:
                if valueb == valuea:
                    resp.append(0.0)
                else:
                    #resp.append((valuea-valuec)/(valueb-valuec*1.0))
                    resp.append((valuec-valuea)/(valueb-valuea*1.0))
                    #print ("###################UTI3####################")
                    self.logger.debug( "A: {:.3f}  B: {:.3f}  C: {:.3f}".format(valuea,valueb,valuec)  )
                    self.logger.debug(  "  -> (C-A)/(B-A) = {:.3f} * REF = {:.3f} ".format( resp[-1], resp[-1]*self.ref ) )
            if self.output >= 2:
                if valueb == valuea:
                    resp.append(0.0)
                else:
                    resp.append((valued-valuea)/(valueb-valuea*1.0))
            if self.output == 3:
                if valueb == valuea:
                    resp.append(0.0)
                else:
                    resp.append((valuee-valuea)/(valueb-valuea*1.0))
            if self.mode in {9,'A','B','C'}:
                resp = [x * self.bridgeref for x in resp]
            else:
                resp = [x * self.ref for x in resp]
            if self.mode == 9:
                resp = [x / 32 for x in resp]
            if self.mode == 'A':
                resp = [x / 480 for x in resp]
            if self.mode == 'C':
                resp = [x / 15 for x in resp]
            return resp
        except Exception as e:
            self.logger.error('Could not make measurement! %s' % e)
            return -1



if __name__ == '__main__':
    import os
    import time
    import logging
    logging.basicConfig()
    logger = logging.getLogger()
    logger.setLevel(10)

    utis = smartec_uti3Serial(logger)
    print('\n\nAs a test I print ID, Address, Communication Parameters, Setpoint1 and current value')
    print((utis.getID()))
    print((utis.getAddress()))
    print((utis.getCommunicationParameters()))
    print((utis.getSetpoint(1)))
    print((utis.getDisplayedValue()))

