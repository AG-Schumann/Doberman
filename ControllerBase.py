import serial
import socket
import time
import logging
import threading
import queue
from subprocess import Popen, PIPE, TimeoutExpired

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
        self.logger = logging.getLogger(opts['name'])
        for key, value in opts.items():
            setattr(self, key, value)
        self._connected = False
        self.cmd_queue = queue.Queue(30)
        self.q_lock = threading.RLock()
        if self.initialize:
            if self._getControl():
                time.sleep(0.2)
                self.running = True
                self.readout_thread = threading.Thread(target=self.ReadoutScheduler)
                self.readout_thread.start()
            else:
                self.logger.error('Something went wrong during initialization...')
                raise ValueError('Initialization failed')

    def _getControl(self):
        """
        Opens the connection to the device
        """
        raise NotImplementedError()

    def ReadoutScheduler(self):
        """
        Pulls tasks from the command queue and deals with them. If the queue is empty
        it sleeps for 100ms and retries. This function returns when self.running
        becomes False. While the sensor is in normal operation, this is the only
        function that should call SendRecv to avoid issues with simultaneous
        access (ie, the isThisMe routine avoids this)
        """
        while self.running:
            try:
                packet = self.cmd_queue.get_nowait()
            except queue.Empty:
                time.sleep(0.1)
                continue
            else:
                command, callback = packet
                if isinstance(command, int):  # reading index
                    command = self.reading_commands[command]
                ret = self.SendRecv(command)
                callback(ret)

    def AddToSchedule(self, reading_index=None, command=None, callback=None):
        """
        Adds one thing to the command queue. This is the only function called
        by the owning Plugin (other than [cd]'tor, obv), so everything else
        works around this function.

        :param reading_index: the i-th reading to do
        :param command: a string other than a reading command
        :param callback: the function called with the results. Must accept
            a dictionary as argument with the result from SendRecv. Required for
            reading_index != None
        :returns None
        """
        if reading_index is not None:
            if callback is None:
                return
            self.logger.debug('Queuing %i' % (reading_index))
            self.cmd_queue.put((reading_index,
                # is there a better way to do this?
                lambda x : self._ProcessReading(reading_index, x, callback)))
        elif command is not None:
            self.cmd_queue.put((command, lambda x : None))


    def _ProcessReading(self, index, pkg, callback):
        """
        Reads one value from the sensor. Unpacks the result from SendRecv
        and passes the data to ProcessOneReading for processing. The results, along
        with timestamp, are passed back upstream.

        :param index: the index of the reading
        :param pkg: the dict returned by SendRecv
        :param callback: a function to call with the results. Must accept
            as argument a tuple containing (index, timestamp, value, retcode). Will
            most often be the 'put' method on the owning Plugin's process_queue.
            If ProcessOneReading throws an exception, value will be None
        :returns None
        """
        try:
            value = self.ProcessOneReading(index, pkg['data'])
        except (ValueError, TypeError, ZeroDivisionError, UnicodeDecodeError, AttributeError) as e:
            self.logger.debug('Caught a %s: %s' % (type(e),e))
            value = None
        self.logger.debug('Index %i values %s' % (index, value))
        if isinstance(value, (list, tuple)):
            now = time.time()
            for i,v in enumerate(value):
                callback((i, now, v, pkg['retcode']))
        else:
            callback((index, time.time(), value, pkg['retcode']))
        return

    def ProcessOneReading(self, index, data):
        """
        Takes the raw data as returned by SendRecv and parses
        it for the (probably) float. Does not need to catch exceptions

        :param index: the index of the reading
        :param data: the raw bytes string
        :returns: probably a float. Sensor-dependent
        """
        raise NotImplementedError()

    def FeedbackReadout(self):
        """
        TODO update for >= 4.x
        Reads the variable used during feedback. Just a single call to SendRecv.
        Must return [timestamp (since epoch), value, retcode]
        """
        raise NotImplementedError()

    def SendRecv(self, message, dev=None):
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
            self.AddToSchedule(command=func(m))
            return
        self.logger.error("Did not understand command '%s'" % command)

    def close(self):
        self.running = False
        self.readout_thread.join()
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

    def __init__(self, opts):
        self._device = self.DummyObject()
        super().__init__(opts)

    def _getControl(self):
        return True

    def call(self, command, timeout=1, **kwargs):
        for k,v in zip(['shell','stdout','stderr'],[True,PIPE,PIPE]):
            if k not in kwargs:
                kwargs.update({k:v})
        proc = Popen(command, **kwargs)
        try:
            out, err = proc.communicate(timeout=timeout, **kwargs)
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        return out, err


class SerialController(Controller):
    """
    Serial controller class. Implements more direct serial connection specifics
    """

    def __init__(self, opts):
        self.ttyUSB = -1
        self._device = serial.Serial()
        self._device.baudrate=9600 if not hasattr(self, 'baud') else self.baud
        self._device.parity=serial.PARITY_NONE
        self._device.stopbits=serial.STOPBITS_ONE
        self._device.timeout=0  # nonblocking mode
        self._device.write_timeout = 5
        super().__init__(opts)

    def _getControl(self):
        if self.ttyUSB == -1:
            self.logger.error('Could not find device: no ttyUSB')
            return False
        self._device.port = '/dev/ttyUSB%i' % (self.ttyUSB)
        try:
            self._device.open()
        except serial.SerialException as e:
            self.logger.error('Problem opening %s: %s' % (self._device.port, e))
            raise
        if not self._device.is_open:
            self.logger.error('Error while connecting to device')
            return False
        else:
            self._connected = True
            return True
        return False

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

    def __init__(self, opts):
        self._device = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        super().__init__(opts)

    def _getControl(self):
        """
        Connects to the controller
        """
        num_tries = 3
        for _ in range(num_tries):
            try:
                self._device.settimeout(5)
                self._device.connect((self.ip, int(self.port)))
            except socket.error as e:
                self.logger.error('Didn\'t find anything at %s:%i. Trying again in 5 seconds...' % (self.ip, self.port))
                #sock._device.close()
                time.sleep(5)
            else:
                self._connected = True
                return True
        return False

    def SendRecv(self, message, dev=None):
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

