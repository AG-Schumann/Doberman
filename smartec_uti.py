from ControllerBase import SerialController
import logging
from subprocess import Popen, PIPE, TimeoutExpired
import re  # EVERYBODY STAND BACK


class smartec_uti(SerialController):
    """
    Level meter controllers
    """

    def __init__(self, opts):
        self.logger = logging.getLogger(opts.name)
        self.commands = {
                'greet' : '@',
                'help' : '?',
                'setSlow' : 's',
                'setFast' : 'f',
                'setMode0' : '0',
                'setMode1' : '1',
                'setMode2' : '2',
                'setMode4' : '4',
                'measure' : 'm',
                'powerDown' : 'p', # if you use this, you need to plug-cycle the board
                }
        self._msg_start = ''
        self._msg_end = '\r\n'
        super().__init__(opts, self.logger)

    def _getControl(self):
        if not super()._getControl():
            return False
        self.SendRecv(self.commands['greet'])
        self.SendRecv(self.commands['setSlow'])
        self.SendRecv(self.commands['setMode%s' % int(self.mode)])
        return True

    def isThisMe(self, dev):
        """
        The smartec serial protocol is very poorly designed, so we have to use
        dmesg to see if we found the right controller
        """
        ttyUSB = int(dev.port.split('USB')[-1])
        proc = Popen('dmesg | grep ttyUSB%i | tail -n 1' % ttyUSB,
                shell=True, stdout=PIPE, stderr=PIPE)
        try:
            out, err = proc.communicate(timeout=5)
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        if not len(out) or len(err):
            self.logger.error('Could not check controller! stdout: %s, stderr: %s' % (
                out.decode(), err.decode()))
            return False
        pattern = r'usb (?P<which>[^:]+):'
        match = re.search(pattern, out.decode())
        if not match:
            #self.logger.error('Could not find controller')
            return False
        proc = Popen('dmesg | grep \'%s: SerialNumber\' | tail -n 1' % match.group('which'),
                shell=True, stdout=PIPE, stderr=PIPE)
        try:
            out, err = proc.communicate(timeout=5)
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        if not len(out) or len(err):
            #self.logger.error('Could not check controller! stdout: %s, stderr: %s' % (
            #    out.decode(), err.decode()))
            pass
        if self.serialID in out.decode():
            return True
        return False

    def Readout(self):
        val = self.SendRecv(self.commands['measure'])
        if val['retcode']:
            return val
        try:
            values = val['data'].split()
            values = list(map(lambda x : int(x,16), values))

            resp = []

            c_off = values[0]
            div = values[1] - values[0]
            self.logger.debug('UTI measured %s' % values)
            if div: # evals to (value[cde] - valuea)/(valueb - valuea)
                resp = [(v-c_off)/div*self.c_ref for v in values[2:]]
                stat = [0] * len(values[2:])
            else:
                resp = [-1]*len(values[2:])
                stat = [-2]*len(values[2:])
            self.logger.debug('UTI evaluates to %s' % resp)

            val['data'] = resp
            val['retcode'] = stat
        except Exception as e:
            self.logger.error('LM error: %s' % e)
            val['retcode'] = -3
            val['data'] = None
        return val
