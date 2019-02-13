import serial
import socket
import time
import logging
from subprocess import Pope, PIPE, TimeoutExpired

class Controller(object):
    """
    Generic controller class. Defines the interface with Doberman
    """
    _msg_start = ''
    _msg_end = ''

    def __init__(self, opts):
        """
        opts is a dict with all the options needed for initialization
        (addresses, configuration options, etc)
        """
        for key, value in opts.items():
            setattr(self, key, value)
        self.logger = logging.getLogger(self.name)
        self._connected = False
        self.SetupBeforeOpening()
        if self.initialize:
            if self.OpenDevice():
                self.SetupAfterOpening()
                time.sleep(0.2)
            else:
                raise ValueError('Could not properly initialize!')

    def SetupBeforeOpening(self):
        """
        A function for a controller to set its operating parameters (commands,
        _ms_start token, etc). Will be called by the c'tor
        """
        pass

    def SetupAfterOpening(self):
        """
        If a controller needs to receive a command after opening but
        before starting "normal" operation, that goes here
        """
        pass

    def OpenDevice(self):
        """
        Opens the connection to the device. The instance MUST have a _device object
        after this function returns successfully. Should return True on success
        """
        raise NotImplementedError()

    def Readout(self):
        """
        Main readout function. Should be implemented for individual controller
        to call SendRecv with the measurement message. This function is called
        by the readout thread.
        """
        raise NotImplementedError()

    def FeedbackReadout(self):
        """
        Reads the variable used during feedback. Just a single call to SendRecv.
        Must return [timestamp (since epoch), value, status]
        """
        raise NotImplementedError()

    def SendRecv(self, message):
        """
        General controller interface. Returns a dict with retcode -1 if controller not connected,
        -2 if there is an exception, (larger numbers also possible) and whatever data was read. Adds _msg_start and _msg_end
        to the message before sending it
        """
        raise NotImplementedError()

    def ExecuteCommand(self, command):
        """
        Allows Doberman to issue commands to the controller (change setpoints, valve
        positions, etc)
        """
        if not hasattr(self, 'command_patterns'):
            self.logger.error("I don't accept specific commands")
            return
        for pattern, func in self.command_patterns:
            m = pattern.search(command)
            if not m:
                continue
            resp = self.SendRecv(func(m))
            if resp['retcode']:
                self.logger.error("Did not accept command '%s'" % command)
            return
        self.logger.error("Did not understand command '%s'" % command)

    def close(self):
        #self.logger.debug('Shutting down %s' % self.name)
        self._connected = False
        self._device.close()
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return


class SoftwareController(Controller):
    """
    Class for software-only controllers (heartbeats, system monitors, etc)
    """
    class DummyObject(object):
        def close():
            return

    def OpenDevice(self):
        self._device = self.DummyObject()
        return True

    def SendRecv(self, command, timeout=1, **kwargs):
        for k,v in zip(['shell','stdout','stderr'],[True,PIPE,PIPE]):
            if k not in kwargs:
                kwargs.update({k:v})
        proc = Popen(command, **kwargs)
        ret = {'data' : None, 'retcode' : 0}
        try:
            out, err = proc.communicate(timeout=timeout, **kwargs)
            ret['data'] = out
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            ret['data'] = err
            ret['retcode'] = -1
        return ret


class SerialController(Controller):
    """
    Serial controller class. Implements more direct serial connection specifics
    """

    def OpenDevice(self):
        self._device = serial.Serial()
        self._device.baudrate=9600 if not hasattr(self, 'baud') else self.baud
        self._device.parity=serial.PARITY_NONE
        self._device.stopbits=serial.STOPBITS_ONE
        self._device.timeout=0  # nonblocking mode
        self._device.write_timeout = 5
        if self.ttyUSB == -1:
            self.logger.error('Could not find device: no ttyUSB')
            return False
        self._device.port = '/dev/ttyUSB%i' % (self.ttyUSB)
        try:
            self._device.open()
        except serial.SerialException as e:
            self.logger.error('Problem opening %s: %s' % (self._device.port, e))
            return False
        if not self._device.is_open:
            self.logger.error('Error while connecting to device')
            return False
        else:
            self._connected = True
            return True

    def isThisMe(self, dev):
        """
        Makes sure the specified controller is the correct one
        """
        raise NotImplementedError()

    def SendRecv(self, message, dev=None):
        device = dev if dev else self._device
        ret = {'retcode' : 0, 'data' : None}
        if not self._connected and dev is None:
            self.logger.error('No controller connected, can\'t send message %s' % message)
            ret['retcode'] = -1
            return ret
        try:
            message = self._msg_start + str(message) + self._msg_end
            device.write(message.encode())
            time.sleep(1.0)
            if device.in_waiting:
                s = device.read(device.in_waiting)
                ret['data'] = s
        except serial.SerialException as e:
            self.logger.error('Could not send message %s. Error %s' % (message, e))
            ret['retcode'] = -2
            return ret
        except serial.SerialTimeoutException as e:
            self.logger.error('Could not send message %s. Error %s' % (message, e))
            ret['retcode'] = -2
            return ret
        time.sleep(0.2)
        return ret


class LANController(Controller):
    """
    Class for LAN-connected controllers
    """

    def OpenDevice(self):
        """
        Connects to the controller
        """
        self._device = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._device.settimeout(5)
            self._device.connect((self.ip, int(self.port)))
        except socket.error as e:
            self.logger.error('Couldn\'t connect to %s:%i' % (self.ip, self.port))
            return False
        self._connected = True
        return True

    def SendRecv(self, message):
        ret = {'retcode' : 0, 'data' : None}

        if not self._connected:
            self.logger.error('No controller connected, can\'t send message %s' % message)
            ret['retcode'] = -1
            return ret
        message = str(message).rstrip()
        message = self._msg_start + message + self._msg_end
        try:
            self._device.sendall(message.encode())
        except socket.error as e:
            self.logger.fatal("Could not send message %s. Error: %s" % (message.strip(), e))
            ret['retcode'] = -2
            return ret
        time.sleep(0.01)

        try:
            ret['data'] = self._device.recv(1024)
        except socket.error as e:
            self.logger.fatal('Could not receive data from controller. Error: %s' % e)
            ret['retcode'] = -2
        return ret

