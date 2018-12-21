from ControllerBase import SoftwareController
from subprocess import Popen, PIPE, TimeoutExpired
import re  # EVERYBODY STAND BACK xkcd.com/207
from utils import number_regex


class sysmon(SoftwareController):
    """
    Controller to monitor the health of the computer
    """
    args = {'shell' : True, 'stdout' : PIPE, 'stderr' : PIPE}
    mem_patterns = {
            'free' : re.compile('MemFree: +(?P<free>%s) kB' % number_regex),
            'avail' : re.compile('MemAvailable: +(?P<avail>%s) kB' % number_regex),
            'swap' : re.compile('SwapFree: +(?P<swap>%s) kB' % number_regex)
        }

    def Readout(self):
        kb_to_gb = 1 << 20
        ret = [-1]*7
        filename = '/proc/loadavg'
        out, err = self.call(filename)
        if not len(out) or len(err):
            pass
        else:
            ret[:3] = list(map(float, out.decode().split(' ')[:3]))

        filename = '/proc/meminfo'
        out, err = self.call(filename)
        if not len(out) or len(err):
            pass
        else:
            out = out.decode()
            m = mem_patterns['free'].search(out)
            if m:
                ret[3] = int(m.group('free'))/kb_to_gb
            m = mem_patterns['avail'].search(out)
            if m:
                ret[4] = int(m.group('avail'))/kb_to_gb
            m = mem_patterns['swap'].search(out)
            if m:
                ret[5] = (self.swap_total_kb - int(m.group('swap')))/kb_to_gb

        filename = '/sys/devices/platform/coretemp.0/hwmon/%s/temp1_input' % self.hwmon
        out, err = self.call(filename)
        if not len(out) or len(err):
            pass
        else:
            ret[6] = int(out)/1000
        return {'data' : ret, 'retcode' : [0]*len(ret)}

    def call(self, filename):
        proc = Popen('cat %s' % filename, **self.args)
        try:
            out, err = proc.communicate(timeout=1)
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        return out, err
