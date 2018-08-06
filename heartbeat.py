from ControllerBase import Controller
from subprocess import Popen, PIPE, TimeoutExpired
import re  # EVERYBODY STAND BACK xkcd.com/208


class heartbeat(Controller):
    """
    'Controller' that pings another server to see if it is alive
    """
    def __init__(self, opts):
        super().__init__(opts)
        self.command = f'ping -c {self.ping_count} {self.address}'
        number = r'[0-9]+(?:\.[0-9]+)?'
        self.value_count = 4  # number of values returned
        pattern = '/'.join([f'({number})']*self.value_count)
        self.time_taken = re.compile(pattern)
        self.popen_args = {'shell' : True, 'stdout' : PIPE, 'stderr' : PIPE}

        class DummyObject(object):
            def close(self):  # we need a '_device' object with a 'close' routine
                return
        self._device = DummyObject()

    def _getControl(self):
        """
        Nothing to do here
        """
        return True

    def Readout(self):
        proc = Popen(self.command, **self.popen_args)
        try:
            out, err = proc.communicate(timeout=self.ping_count*3)
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        if not len(out) or len(err):
            status = [-1]*self.value_count
            data = [0]*self.value_count
            self.logger.error('Problem pinging server!')
        else:
            m = self.time_taken.search(out.decode())
            if not m:
                status = [-2]*self.value_count
                data = [0]*self.value_count
                self.logger.error('Problem parsing output!')
            else:
                status = [0]*self.value_count
                data = map(float, m.groups())
        return {'retcode' : status, 'data' : data}

