import socketserver
import time
import random
import argparse
import re
import numpy as np
import signal
import threading
import datetime

pattern = (r'[\-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][\-+]?[0-9]+)?').encode()


class FeedbackTester(object):
    def __init__(self):
        signal.signal(signal.SIGINT, self.interrupt)
        signal.signal(signal.SIGTERM, self.interrupt)
        self.run = True
        self.amb_base = 295
        self.amb_amp = 5
        self.amb_period = 7200
        self.amb_noise = 0.3
        self.ro_noise = 0.005
        self.t_bulk = 175
        self.q_out = 100

    def interrupt(self, *args):
        print('Interrupted with signal', args[0])
        self.run = False

    def Simulate(self):
        heat_cap = 5000 # J/K
        epsilon = 2e-8 # J/K^4
        k = 0.005  # W/K
        whoops = 0
        period = 0.01
        q_other = 0
        while self.run:
            t = time.time()
            if np.abs(whoops) < 0.5:
                whoops = 0.5-random.random()
            if np.abs(whoops) < 0.001*period:
                shit_start = t
                if whoops > 0:
                    whoops = 1
                else:
                    whoops = -1
            if whoops in [-1,1]:
                if t - shit_start < 15*60:
                    q_other = whoops*self.shit_happens(t-shit_start)
                else:
                    whoops = q_other = 0
            t_amb = self.T_amb(t)
            q_rad = epsilon * (t_amb**4 - self.t_bulk**4)
            q_cond = k*(t_amb - self.t_bulk)
            q_in = q_rad + q_cond + q_other
            dq = q_in - self.q_out
            dt = dq/heat_cap*period
            self.t_bulk += dt
            time.sleep(period)

    def T_amb(self, t):
        return (self.amb_base + self.amb_amp*np.sin(2*np.pi/self.amb_period*t) +
                self.amb_noise * np.sin(2*np.pi/5*t))

    def T_bulk(self):
        return self.t_bulk + self.ro_noise*(0.5*random.random())

    def shit_happens(self, t):
        amp, mu, sig = 15, 15*60/2, 120
        return amp*np.exp(-(t-mu)**2/(2*sig**2))


class TestSensorHandler(socketserver.BaseRequestHandler):
    """
    Software-only sensor for testing purposes
    Message start token: *
    Message end token: \r\n

    Read request format: READ:<name>
    Read return format: OK;<value>
    Command format: SET:<param>=<value>
    """
    read_pattern = re.compile(b'^\\*READ:(?P<ch>one|two)\r\n$')
    set_pattern = re.compile(b'^\\*SET:(?P<param>[a-z]+)=(?P<value>' + pattern + b')\r\n$')

    def handle(self):
        try:
            msg = self.request.recv(1024)
            print('Received %s at %s' % (msg, datetime.datetime.now().isoformat(sep=' ')))
            if not msg:
                return
            sleep_for = 0.006*random.random()
            print('Processing time: %.3g' % sleep_for)
            time.sleep(sleep_for)
            payload = b''
            m = self.read_pattern.search(msg)
            if m:
                if m.group('ch') == b'one':
                    payload = b'OK;%.3g' % (5*random.random())
                elif m.group('ch') == b'two':
                    payload = b'OK;%.3g' % random.randint(1, 6)
                elif m.group('ch') == b't_pid':
                    payload = b'OK;%.3f' % self.fbt.T_bulk()
                else:
                    payload = b'ERR;01'
            else:
                m = self.set_pattern.search(msg)
                if not m:
                    payload = b'ERR;00'
                else:
                    try:
                        float(m.group('value'))
                    except ValueError:
                        payload = b'ERR;11'
                    else:
                        payload = b'OK;'
                        if m.group('param') == 'noise':
                            self.fbt.ro_noise = float(m.group('value'))
                        elif m.group('param') == 'qout':
                            self.fbt.q_out = float(m.group('value'))
                        elif m.group('param') == 'ambbase':
                            self.fbt.amb_base = float(m.group('value'))
                        elif m.group('param') == 'ambamp':
                            self.fbt.amb_amp = float(m.group('value'))
                        elif m.group('param') == 'ambperiod':
                            self.fbt.amb_period = float(m.group('value'))
                        elif m.group('param') == 'ambnoise':
                            self.fbt.amb_noise = float(m.group('value'))
                        else:
                            payload = b'ERR;12'
            print('Sending %s' % payload.decode())
            self.request.sendall(payload + b'\r\n')
            sleep_for = 0.05*random.random()
            print('Cleanup time: %.3g' % sleep_for)
            time.sleep(sleep_for)
            print()
        except:
            pass

    def dice(self):
        return random.randint(1, self.sides)

def main():
    #fbt = FeedbackTester()
    #t = threading.Thread(target=fbt.Simulate)
    with socketserver.TCPServer(('localhost', 5000), TestSensorHandler) as server:
        #server.fbt = fbt
        #t.start()
        server.serve_forever()
    #fbt.run = False

if __name__ == '__main__':
    main()
