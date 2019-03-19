import serial
import socket
import time
import logging
import queue
import threading
from functools import partial


class Sensor(object):
    """
    Generic sensor class. Defines the interface with Doberman
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
        self.SetParameters()

    def _Setup(self):
        self.cmd_queue = queue.Queue(30)
        if self.OpenDevice():
            self.Setup()
            time.sleep(0.2)
            self.running = True
            self.readout_thread = threading.Thread(target=self.ReadoutScheduler)
            self.readout_thread.start()
        else:
            self.logger.error('Something went wrong during initialization...')
            raise ValueError('Initialization failed')

    def SetParameters(self):
        """
        A function for a controller to set its operating parameters (commands,
        _ms_start token, etc). Will be called by the c'tor
        """
        pass

    def Setup(self):
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

    def ReadoutScheduler(self):
        """
        Pulls tasks from the command queue and deals with them. If the queue is empty
        it sleeps for 10ms and retries. This function returns when self.running
        becomes False. While the sensor is in normal operation, this is the only
        function that should call SendRecv to avoid issues with simultaneous
        access (ie, the isThisMe routine avoids this)
        """
        while self.running:
            try:
                packet = self.cmd_queue.get_nowait()
            except queue.Empty:
                time.sleep(0.01)
                continue
            else:
                command, callback = packet
                ret = self.SendRecv(command)
                callback(ret)

    def AddToSchedule(self, reading_name=None, command=None, callback=None):
        """
        Adds one thing to the command queue. This is the only function called
        by the owning Plugin (other than [cd]'tor, obv), so everything else
        works around this function.

        :param command: the command to issue to the sensor
        :param callback: the function called with the results. Must accept
            a dictionary as argument with the result from SendRecv. Required for
            reading_name != None
        :returns None
        """
        if reading_name is not None:
            if callback is None:
                return
            self.logger.debug('Queuing %s' % (reading_name))
            self.cmd_queue.put((self.reading_commands[reading_name],
                partial(self._ProcessReading(reading_name=reading_name, cb=callback))))
        elif command is not None:
            self.cmd_queue.put((command, lambda x : None))

    def _ProcessReading(self, pkg, reading_name=None, cb=None):
        """
        Reads one value from the sensor. Unpacks the result from SendRecv
        and passes the data to ProcessOneReading for processing. The results, along
        with timestamp, are passed back upstream.

        :param pkg: the dict returned by SendRecv
        :param reading_name: the name of the reading
        :param cb: a function to call with the results. Must accept
            as argument a tuple containing (name, value, retcode). Will
            most often be the 'put' method on the owning Plugin's process_queue.
            If ProcessOneReading throws an exception, value will be None
        :returns None
        """
        try:
            value = self.ProcessOneReading(reading_name, pkg['data'])
        except (ValueError, TypeError, ZeroDivisionError, UnicodeDecodeError, AttributeError) as e:
            self.logger.debug('Caught a %s: %s' % (type(e),e))
            value = None
        self.logger.debug('Name %s values %s' % (reading_name, value))
        if isinstance(value, (list, tuple)):
            for n,v in zip(self.reading_commands.keys(), value):
                cb(n, v, pkg['retcode'])
        else:
            cb(reading_name, value, pkg['retcode'])
        return

    def ProcessOneReading(self, name, data):
        """
        Takes the raw data as returned by SendRecv and parses
        it for the (probably) float. Does not need to catch exceptions.
        If the data is "simple", add a 'reading_pattern' member that is a
        regex with a named 'value' group that is float-castable, like:
        re.compile(('OK;(?P<value>%s)' % utils.number_regex).encode())

        :param name: the name of the reading
        :param data: the raw bytes string
        :returns: probably a float. Sensor-dependent
        """
        if hasattr(self, 'reading_pattern'):
            return float(self.reading_pattern.search(data).group('value'))
        raise NotImplementedError()

    def FeedbackReadout(self):
        """
        TODO update for >= 4.x
        Reads the variable used during feedback. Just a single call to SendRecv.
        Must return [timestamp (since epoch), value, retcode]
        """
        raise NotImplementedError()

    def SendRecv(self, message):
        """
        General sensor interface. Returns a dict with retcode -1 if sensor not connected,
        -2 if there is an exception, (larger numbers also possible) and whatever data was read. Adds _msg_start and _msg_end
        to the message before sending it
        """
        raise NotImplementedError()

    def ExecuteCommand(self, command):
        """
        Allows Doberman to issue commands to the sensor (change setpoints, valve
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
        try:
            self._device.close()
        except:
            pass
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return


class SoftwareSensor(Sensor):
    """
    Class for software-only sensors (heartbeats, system monitors, etc)
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


class SerialSensor(Sensor):
    """
    Serial sensor class. Implements more direct serial connection specifics
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
        Makes sure the specified sensor is the correct one
        """
        raise NotImplementedError()

    def SendRecv(self, message, dev=None):
        device = dev if dev else self._device
        ret = {'retcode' : 0, 'data' : None}
        if not self._connected and dev is None:
            self.logger.error('No sensor connected, can\'t send message %s' % message)
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


class LANSensor(Sensor):
    """
    Class for LAN-connected sensors
    """

    def OpenDevice(self):
        """
        Connects to the sensor
        """
        self._device = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._device.settimeout(1)
            self._device.connect((self.ip, int(self.port)))
        except socket.error as e:
            self.logger.error('Couldn\'t connect to %s:%i' % (self.ip, self.port))
            return False
        self._connected = True
        return True

    def SendRecv(self, message):
        ret = {'retcode' : 0, 'data' : None}

        if not self._connected:
            self.logger.error('No sensor connected, can\'t send message %s' % message)
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
            self.logger.fatal('Could not receive data from sensor. Error: %s' % e)
            ret['retcode'] = -2
        return ret

