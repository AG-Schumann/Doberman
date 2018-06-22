from subprocess import Popen, PIPE, TimeoutExpired
import logging
import serial
import os.path
import socket


class Controller(object):
    """
    Generic controller class. Defines the interface with Doberman
    """
    __msg_start = ''
    __msg_end = ''

    def __init__(self, opts):
        self.logger = logging.getLogger(__name__)
        self.name = opts.name
        self.__connected = False
        self.__device = self._getControl()
        if self.checkController():
            self.logger.error('Something went wrong here...')

    def connected(self):
        return self.__connected

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
        to call SendRecv with the measurement message
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
        self.__connected = False
        self.__device.close()
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

    def __init__(self, opts):
        self.productID = opts.productID
        self.vendorID = opts.vendorID
        self.serialID = opts.additional_parameters.split('|')[0]
        self._ID = opts.additional_parameters.split('|')[1]
        self.ttyUSB = -1
        super().__init__(opts)
        self.ttypath = os.path.join(opts.path, "ttyUSB_assignment.txt")
        return

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
        tty_ID = out.decode()[-2] # [-1] is \n
        return int(tty_ID)

    def _getControl(self):
        self.ttyUSB = self.get_ttyUSB(self.vendorID, self.productID, self.serialID)
        if self.ttyUSB == -1:
            self.logger.error('Could not find device')
            return None
        num_tries = 3
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
                self.__connected = True
                self.logger.info('Successfully connected to device')
                return dev
        return None

    def SendRecv(self, message):
        ret = {'retcode' : 0, 'data' : None}
        if not self.__connected:
            self.logger.error('No controller connected, can\'t send message %s' % message)
            ret['retcode'] = -2
            return ret
        try:
            message = self.__msg_start + str(message) + self.__msg_end
            self.__device.write(message.encode())
            time.sleep(0.3)
            if self.__device.in_waiting:
                ret['data'] = self.__device.read(self.__device.in_waiting).decode()
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

    def __init__(self, opts, **kwargs):
        self.address = opts.ipaddress
        self.port = opts.port
        super().__init__(opts)
        return

    def _getControl(self):
        """
        Connects to the controller
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        num_tries = 3
        for _ in range(num_tries):
            try:
                sock.settimeout(5)  # keeps things going
                sock.connect((self.address, self.port))
            except socket.error as e:
                self.logger.error('Didn\'t find anything at %s:%i. Trying again in 5 seconds...' % (self.address, self.port))
                sock.close()
                sock = None
                time.sleep(5)
            else:
                self.__connected = True
                self.logger.info('Successfully connected to device')
                return sock
        return None

    def SendRecv(self, message):
        ret = {'retcode' : 0, 'data' : None}

        if not self.__connected:
            self.logger.error('No controller connected, can\'t send message %s' % message)
            ret['retcode'] = -2
            return ret
        message = str(message).rstrip()
        message = self.__msg_start + message + self.__msg_end
        try:
            self.__device.sendall(message.encode())
        except socket.error as e:
            self.logger.fatal("Could not send message %s. Error: %s" % (message.strip(), e))
            ret['retcode'] = -1
            return ret
        time.sleep(0.01)

        try:
            ret['data'] = self.__device.recv(1024).decode().rstrip()
        except socket.error as e:
            self.logger.fatal('Could not receive data from controller. Error: %s' % e)
            ret['retcode'] = -1
        return ret

