from subprocess import Popen, PIPE, TimeoutExpired
import logging
import serial
import os.path
import socket
import time


class Controller(object):
    """
    Generic controller class. Defines the interface with Doberman
    """
    _msg_start = ''
    _msg_end = ''

    def __init__(self, opts, logger):
        self.name = opts.name
        self.logger = logger
        self.logger.debug('c\'tor starting')
        for key, value in opts.address.items():
            self.logger.debug('%s: %s' % (key, value))
            setattr(self, key, value)
        self._connected = False
        self._device = self._getControl()
        if self.checkController():
            self.logger.error('Something went wrong here...')
        self.logger.debug('c\'tor ending')

    def connected(self):
        return self._connected

    def _getControl(self):
        """
        Opens the connection to the device
        """
        raise NotImplementedError()

    def checkController(self):
        """
        Makes sure the connected controller is the correct one
        """
        raise NotImplementedError()

    def Readout(self):
        """
        Main readout function. Should be implemented for individual controller
        to call SendRecv with the measurement message. This function is called
        by the readout thread
        """
        raise NotImplementedError()

    def SendRecv(self, message):
        """
        General controller interface. Returns a dict with retcode -2 if controller not connected,
        -1 if there is an exception, and whatever data was read. Adds __msg_start and __msg_end
        to the message before sending it
        """
        raise NotImplementedError()

    def close(self):
        self.logger.debug('Shutting down %s' % self.name)
        self._connected = False
        self._device.close()
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return


class SerialController(Controller):
    """
    Serial controller class. Implements more direct serial connection specifics
    Also holds the static list of which tty ports are currently in use
    """
    occupied_ttyUSB = []

    def __init__(self, opts, logger):
        self.ttyUSB = -1
        self.ttypath = os.path.join(opts.path, "settings", "ttyUSB_assignment.txt")
        self.logger = logger
        self.logger.debug('c\'tor starting')
        super().__init__(opts, logger)
        self.logger.debug('c\'tor ending')

    def get_ttyUSB(self, vendorID, productID, serialID):
        '''
        Finds the ttyUSB assignment for the device by looking through dmesg
        '''
        self.logger.debug('Looking for tty device with product %s, vendor %s, serial %s' % (
            self.productID, self.vendorID, self.serialID))
        proc = Popen('dmesg | grep %s | tail -n 1' % self.serialID, shell=True, stdout=PIPE, stderr=PIPE)
        try:
            out, err = proc.communicate(timeout=10)
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        if len(err) or not len(out):
            self.logger.error('Could not find USB device, stdout: %s, stderr: %s' % (out.decode(), err.decode()))
            return -1
        usb_number = out.decode().split()[3]  # '3-14.1:' or something
        proc = Popen('dmesg | grep %s | grep -o ttyUSB[0-9] | tail -n 1' % usb_number,
                shell=True, stdout=PIPE, stderr=PIPE)
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

    def add_ttyUSB(self):
        if self.ttyUSB == -1:
            self.logger.error('No ttyUSB value, not storing')
            return -1
        self.occupied_ttyUSB.append(self.ttyUSB)
        try:
            with open(self.ttypath, 'a+') as f:
                f.write(' %i | %s\n' % (self.ttyUSB, self.name))
        except Exception as e:
            self.logger.warning('Could not add ttyUSB to file! Error %s' % e)
        return 0

    def _getControl(self):
        self.ttyUSB = self.get_ttyUSB(self.vendorID, self.productID, self.serialID)
        if self.ttyUSB == -1:
            self.logger.error('Could not find device')
            return None
        num_tries = 2
        for _ in range(num_tries):
            try:
                dev = serial.Serial(
                        port = '/dev/ttyUSB%i' % self.ttyUSB,
                        baudrate=9600,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        timeout=5
                        )
            except serial.SerialException as e:
                self.logger.error('Error while connecting to device: %s. Trying again in 5 seconds...' % e)
                time.sleep(5)
            else:
                self._connected = True
                self.logger.info('Successfully connected to device')
                return dev
        return None

    def SendRecv(self, message):
        ret = {'retcode' : 0, 'data' : None}
        if not self._connected:
            self.logger.error('No controller connected, can\'t send message %s' % message)
            ret['retcode'] = -2
            return ret
        try:
            message = self._msg_start + str(message) + self._msg_end
            self._device.write(message.encode())
            time.sleep(0.3)
            if self._device.in_waiting:
                ret['data'] = self._device.read(self._device.in_waiting).decode().rstrip()
        except serial.SerialException as e:
            self.logger.error('Could not send message %s. Error %s' % (message, e))
            ret['retcode'] = -1
            return ret
        time.sleep(0.1)
        return ret


class LANController(Controller):
    """
    Class for LAN-connected controllers
    """


    def __init__(self, opts):

        super().__init__(opts)

    def _getControl(self):
        """
        Connects to the controller
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        num_tries = 3
        for _ in range(num_tries):
            try:
                sock.settimeout(5)  # keeps things going
                sock.connect((self.ip, self.port))
            except socket.error as e:
                self.logger.error('Didn\'t find anything at %s:%i. Trying again in 5 seconds...' % (self.ip, self.port))
                sock.close()
                time.sleep(5)
            else:
                self._connected = True
                self.logger.info('Successfully connected to device')
                return sock
        return None

    def SendRecv(self, message):
        ret = {'retcode' : 0, 'data' : None}

        if not self._connected:
            self.logger.error('No controller connected, can\'t send message %s' % message)
            ret['retcode'] = -2
            return ret
        message = str(message).rstrip()
        message = self._msg_start + message + self._msg_end
        try:
            self._device.sendall(message.encode())
        except socket.error as e:
            self.logger.fatal("Could not send message %s. Error: %s" % (message.strip(), e))
            ret['retcode'] = -1
            return ret
        time.sleep(0.01)

        try:
            ret['data'] = self._device.recv(1024).decode().rstrip()
        except socket.error as e:
            self.logger.fatal('Could not receive data from controller. Error: %s' % e)
            ret['retcode'] = -1
        return ret

