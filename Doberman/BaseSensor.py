try:
    import serial
    has_serial=True
except ImportError:
    has_serial=False
import socket
import queue
import time
import threading

__all__ = 'Sensor SoftwareSensor SerialSensor LANSensor'.split()

class Sensor(object):
    """
    Generic sensor class. Defines the interface with Doberman
    """
    _msg_start = ''
    _msg_end = ''

    def __init__(self, opts, logger):
        """
        opts is the document from the database
        """
        for k, v in opts['address'].items():
            setattr(self, k, v)
        if 'additional_params' in opts:
            for k, v in opts['additional_params'].items():
                setattr(self, k, v)
        self.readings = opts['readings']
        self.logger = logger
        self.SetParameters()
        self.BaseSetup()

    def BaseSetup(self):
        self.cmd_queue = queue.Queue()
        try:
            self.SetupChild()
            self.Setup()
            time.sleep(0.2)
            self.event = threading.Event()
            self.readout_thread = threading.Thread(target=self.ReadoutScheduler)
            self.readout_thread.start()
        except Exception as e:
            self.logger.error('Something went wrong during initialization...')
            self.logger.error(type(e))
            self.logger.error(e)
            raise ValueError('Initialization failed')

    def Shutdown(self):
        """
        A function for a child class to implement with anything that should happen
        before shutdown, such as closing an active hardware connection
        """
        pass

    def SetParameters(self):
        """
        A function for a sensor to set its operating parameters (commands,
        _ms_start token, etc). Will be called by the c'tor
        """
        pass

    def Setup(self):
        """
        If a sensor needs to receive a command after opening but
        before starting "normal" operation, that goes here
        """
        pass

    def SetupChild(self):
        """
        A function for a child class to implement with any setup that needs
        to be done before handing off to the user's code (such as opening a
        hardware connection)
        """
        pass

    def ReadoutScheduler(self):
        """
        Pulls tasks from the command queue and deals with them. If the queue is empty
        it sleeps for 1ms and retries. This function returns when self.running
        becomes False. While the sensor is in normal operation, this is the only
        function that should call SendRecv to avoid issues with simultaneous
        access (ie, the isThisMe routine avoids this)
        """
        self.logger.debug('Readout scheduler starting')
        while not self.event.is_set():
            try:
                command, retq = self.cmd_queue.get(timeout=0.001)
                ret = self.SendRecv(command)
                self.cmd_queue.task_done()
                if retq is not None:
                    retq.put(ret)
            except queue.Empty:
                pass
        self.logger.debug('Readout scheduler returning')

    def AddToSchedule(self, reading_name=None, command=None, retq=None):
        """
        Adds one thing to the command queue. This is the only function called
        by the owning Plugin (other than [cd]'tor, obv), so everything else
        works around this function.

        :param reading_name: the name of the reading to schedule
        :param command: the command to issue to the sensor
        :param retq: a queue to put the result for asyncronous processing.
            Required for reading_name != None
        :returns None
        """
        if reading_name is not None:
            if retq is None:
                return
            self.cmd_queue.put((self.readings[reading_name], retq))
        elif command is not None:
            self.cmd_queue.put((command, None))
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
        self.event.set()
        if hasattr(self, 'readout_thread'):
            self.readout_thread.join()
        self.Shutdown()
        return

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return


class SoftwareSensor(Sensor):
    """
    Class for software-only sensors (heartbeats, webcams, etc)
    """
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
    def SetupChild(self):
        if not has_serial:
            raise ValueError('This host doesn\'t have the serial library')
        self._device = serial.Serial()
        self._device.baudrate=9600 if not hasattr(self, 'baud') else self.baud
        self._device.parity=serial.PARITY_NONE
        self._device.stopbits=serial.STOPBITS_ONE
        self._device.timeout=0  # nonblocking mode
        self._device.write_timeout = 1

        if self.tty == '0':
            raise ValueError('No tty port specified!')
        try:
            self._device.port = '/dev/tty%s' % (self.name)
        except serial.SerialException as e:
            try:
                self._device.port = '/dev/tty%s' % self.tty
                self._device.open()
            except serial.SerialException as e:
                raise ValueError('Problem opening %s: %s' % (self._device.port, e))
            if not self._device.is_open:
                raise ValueError('Error while connecting to device')
        return

    def Shutdown(self):
        self._device.close()

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

    def SendRecv(self, message):
        ret = {'retcode' : 0, 'data' : None}

        message = str(message).rstrip()
        message = self._msg_start + message + self._msg_end
        try:
            with socket.create_connection((self.ip, self.port), timeout=1) as s:
                s.sendall(message.encode())
                time.sleep(0.001)
                ret['data'] = s.recv(1024)
        except socket.error as e:
            self.logger.error("Error with message %s: %s" % (message.strip(), e))
            ret['retcode'] = -2
        return ret
