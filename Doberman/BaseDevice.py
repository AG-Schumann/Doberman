try:
    import serial
    has_serial = True
except ImportError:
    has_serial = False
import socket
import time
import threading
from subprocess import PIPE, Popen, TimeoutExpired

__all__ = 'Device SoftwareDevice SerialDevice LANDevice CheapSocketDevice'.split()


class Device(object):
    """
    Generic device class. Defines the interface with Doberman
    """
    _msg_start = ''
    _msg_end = ''

    def __init__(self, opts, logger, event):
        """
        opts is the document from the database
        """
        logger.debug('Device base ctor')
        if 'address' in opts:
            for k, v in opts['address'].items():
                setattr(self, k, v)
        self.params = opts.get('params', {})
        self.sensors = opts['sensors']
        self.logger = logger
        self.event = event
        self.cv = threading.Condition()
        self.cmd_queue = []
        self.set_parameters()
        self.base_setup()

    def base_setup(self):
        try:
            self.setup()
            time.sleep(0.2)
        except Exception as e:
            self.logger.error('Something went wrong during initialization...')
            self.logger.error(type(e))
            self.logger.error(e)
            raise ValueError('Initialization failed')

    def shutdown(self):
        """
        A function for a child class to implement with anything that should happen
        before shutdown, such as closing an active hardware connection
        """

    def set_parameters(self):
        """
        A function for a device to set its operating parameters (commands,
        _ms_start token, etc). Will be called by the c'tor
        """

    def setup(self):
        """
        If a device needs to receive a command after opening but
        before starting "normal" operation, that goes here
        """
        pass

    def readout_scheduler(self):
        """
        Pulls tasks from the command queue and deals with them. If the queue is empty
        it waits until it isn't. This function returns when the event is set.
        While the device is in normal operation, this is the only
        function that should call send_recv to avoid issues with simultaneous
        access (ie, the isThisMe routine avoids this)
        """
        self.logger.debug('Readout scheduler starting')
        while not self.event.is_set():
            try:
                command = None
                with self.cv:
                    self.cv.wait_for(lambda: (len(self.cmd_queue) > 0 or self.event.is_set()))
                    if len(self.cmd_queue) > 0:
                        command, ret = self.cmd_queue.pop(0)
                if command is not None:
                    self.logger.debug(f'Executing {command}')
                    t_start = time.time()  # we don't want perf_counter because we care about
                    pkg = self.send_recv(command)
                    t_stop = time.time()  # the clock time when the data came out not cpu time
                    pkg['time'] = 0.5*(t_start + t_stop)
                    if ret is not None:
                        d, cv = ret
                        with cv:
                            d.update(pkg)
                            cv.notify()
            except Exception as e:
                self.logger.error(f'Scheduler caught a {type(e)} while processing {command}: {e}')
        self.logger.debug('Readout scheduler returning')

    def add_to_schedule(self, command, ret=None):
        """
        Adds one thing to the command queue. This is the only function called
        by the owning Plugin (other than [cd]'tor, obv), so everything else
        works around this function.

        :param command: the command to issue to the device
        :param ret: a (dict, Condition) tuple to store the result for asynchronous processing.
        :returns None
        """
        #self.logger.debug(f'Scheduling {command}')
        with self.cv:
            self.cmd_queue.append((command, ret))
            self.cv.notify()
        return

    def process_one_value(self, name=None, data=None):
        """
        Takes the raw data as returned by send_recv and parses
        it for the (probably) float. Does not need to catch exceptions.
        If the data is "simple", add a 'value_pattern' member that is a
        regex with a named 'value' group that is float-castable, like:
        re.compile((f'OK;(?P<value>{utils.number_regex})').encode())

        :param name: the name of the sensor
        :param data: the raw bytes string
        :returns: probably a float. Device-dependent
        """
        if hasattr(self, 'value_pattern'):
            return float(self.value_pattern.search(data).group('value'))
        raise NotImplementedError()

    def send_recv(self, message):
        """
        General device interface. Returns a dict with retcode -1 if device not connected,
        -2 if there is an exception, (larger numbers also possible) and whatever data was read.
        Adds _msg_start and _msg_end to the message before sending it
        """
        raise NotImplementedError()

    def _execute_command(self, quantity, value):
        """
        Allows Doberman to issue commands to the device (change setpoints, valve
        positions, etc)
        :param quantity: string, the thing you want changed
        :param value: string, the value you want {quantity} changed to
        """
        try:
            cmd = self.execute_command(quantity, value)
        except Exception as e:
            self.logger.warning(f'Tried to process command "{quantity}" "{value}", got a {type(e)}: {e}')
            cmd = None
        if cmd is not None:
            self.add_to_schedule(command=cmd)

    def execute_command(self, quantity, value):
        """
        Implemented by a child class
        """

    def close(self):
        self.event.set()
        with self.cv:
            self.cv.notify()
        self.shutdown()

    def __del__(self):
        self.close()

    def __exit__(self):
        self.close()


class SoftwareDevice(Device):
    """
    Class for software-only devices (heartbeats, webcams, etc)
    """

    def send_recv(self, command, timeout=1, **kwargs):
        for k, v in zip(['shell', 'stdout', 'stderr'], [True, PIPE, PIPE]):
            if k not in kwargs:
                kwargs.update({k: v})
        proc = Popen(command, **kwargs)
        ret = {'data': None, 'retcode': 0}
        try:
            out, err = proc.communicate(timeout=timeout, **kwargs)
            ret['data'] = out
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            ret['data'] = err
            ret['retcode'] = -1
        return ret


class SerialDevice(Device):
    """
    Serial device class. Implements more direct serial connection specifics
    """

    def setup(self):
        if not has_serial:
            raise ValueError('This host doesn\'t have the serial library')
        self._device = serial.Serial()
        self._device.baudrate = 9600 if not hasattr(self, 'baud') else self.baud
        self._device.parity = serial.PARITY_NONE
        self._device.stopbits = serial.STOPBITS_ONE
        self._device.timeout = 0  # nonblocking mode
        self._device.write_timeout = 1
        if not hasattr(self, 'msg_sleep'):
            # so we can more easily change this later
            self.msg_sleep = 1.0

        if self.tty == '0':
            raise ValueError('No tty port specified!')
        try:
            if self.tty.startswith('/'):  # Full path to device TTY specified
                self._device.port = self.tty
            else:
                self._device.port = f'/dev/tty{self.tty}'
            self._device.open()
        except serial.SerialException as e:
            raise ValueError(f'Problem opening {self._device.port}: {e}')
        if not self._device.is_open:
            raise ValueError('Error while connecting to device')

    def shutdown(self):
        self._device.close()

    def is_this_me(self, dev):
        """
        Makes sure the specified device is the correct one
        """
        raise NotImplementedError()

    def send_recv(self, message, dev=None):
        device = dev if dev else self._device
        ret = {'retcode': 0, 'data': None}
        try:
            message = self._msg_start + str(message) + self._msg_end
            device.write(message.encode())
            time.sleep(self.msg_sleep)
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


class LANDevice(Device):
    """
    Class for LAN-connected devices
    """

    def setup(self):
        if not hasattr(self, 'msg_sleep'):
            self.msg_sleep = 0.01
        self.packet_bytes = 1024
        self._device = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._device.settimeout(1)
            self._device.connect((self.ip, int(self.port)))
        except socket.error as e:
            raise ValueError(f'Couldn\'t connect to {self.ip}:{self.port}. Got a {type(e)}: {e}')
        self._connected = True
        return True

    def shutdown(self):
        self._device.close()

    def send_recv(self, message):
        ret = {'retcode': 0, 'data': None}

        if not self._connected:
            self.logger.error(f'No device connected, can\'t send message {message}')
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
        time.sleep(self.msg_sleep)

        try:
            ret['data'] = self._device.recv(self.packet_bytes)
        except socket.error as e:
            self.logger.fatal('Could not receive data from device. Error: %s' % e)
            ret['retcode'] = -2
        return ret


class CheapSocketDevice(LANDevice):
    """
    Some hardware treats sockets as disposable and expects a new one for each connection, so we do that here
    """
    def setup(self):
        if not hasattr(self, 'msg_sleep'):
            self.msg_sleep = 0.01
        self.packet_bytes = 1024
        self._device = None
        self._connected = True
        return True

    def shutdown(self):
        return

    def send_recv(self, message):
        with socket.create_connection((self.ip, int(self.port)), timeout=0.1) as self._device:
            return super().send_recv(message)

