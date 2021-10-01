import random
import datetime
import socket
import threading
import math

def rand():
    '''
    Most of the time we want something evenly distributed about 0. This returns [-1,1]
    '''
    return 2*random.random()-1

class TestSensorBackend(object):

    def __init__(self):
        self.event = threading.Event()

    def run(self):
        self.t_in = 180 # K, to start
        k_rad = 0.001 * 5.67e-8  # kW/K^4, with Boltzmann constant
        k_cond = 0.003  # kW/K
        mass = 10  # kg?
        heat_capacity = 1.2 # kJ/kg/K
        whoops_prob = 1e-7
        self.q_out = 1 # kW
        self.q_add = 0
        shitstorm_end = datetime.datetime.utcnow()
        then = datetime.datetime.utcnow()

        period = 0.001 # ~1 kHz simulation speed

        while not self.event.is_set():
            now = datetime.datetime.utcnow()
            dt = (now - then).total_seconds()
            then = now
            if random.random() < whoops_prob:
                shitstorm_end = now + datetime.timedelta(seconds = 1000*random.random())
                print('Oh shit ' + now.isoformat() + ' ' + shitstorm_end.isoformat())
            t_out = self.outside_temp(now)
            q_in = k_cond*(t_out - self.t_in) + k_rad*(t_out**4 - self.t_in**4) + self.q_add
            if now < shitstorm_end:
                q_in += 0.3*rand()
            q_out = self.q_out
            dq = (q_in - q_out) * dt

            dt = dq/(mass * heat_capacity)
            self.t_in += dt
            #print(f'Tout {t_out:.1f} Qin {q_in:.2f} Qout {q_out:.2f} dq {dq:.2f} t_in {self.t_in:.2f} dt {dt:.3g}')
            self.event.wait(period)

    def observe(self, quantity):
        """
        Peek into what the system is currently doing. Returns a string-cast value with some noise
        added on top for good measure
        """
        if quantity == 't_in':
            noise = 0.01 * rand()  # 10 mK
            return f'{self.t_in + noise:.3f}'
        if quantity == 'q_add':
            noise = 1 + 0.01 * rand()  # 1%
            return f'{self.q_add * noise:.2f}'
        if quantity == 't_amb':
            noise = 0.2 * rand() # 0.2 K
            now = datetime.datetime.utcnow()
            return f'{self.outside_temp(now) + noise:.1f}'

    def outside_temp(self, when):
        temp_base = 290
        temp_variation = 8
        t_period = 86400
        return temp_base + temp_variation * math.sin(when.timestamp()/t_period)


def main():
    HOST, PORT = 'localhost', 9999
    obj = TestSensorBackend()
    t = threading.Thread(target=obj.run)
    t.start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(100)
        sock.bind((HOST, PORT))
        sock.listen()
        try:
            while True:
                conn, addr = sock.accept()
                with conn:
                    data = conn.recv(1024).strip().decode()
                    if 'READ' in data:
                        # format READ:t_in or something
                        if (ch := data.split(':')[1]) in ['t_in', 't_amb', 'q_add']:
                            output = f'OK;{obj.observe(ch)}'
                        else:
                            output = f'FAIL;bad_ch'
                    elif 'SET' in data:
                        # format SET:q_out=3 or something
                        data = data.split(':')[1]
                        ch, val = data.split('=')
                        if ch == 'q_add':
                            setattr(obj, ch, float(val))
                            output = f'OK;{ch}={val}'
                        else:
                            output = f'FAIL;bad_ch'
                    else:
                        output = f'FAIL;bad_cmd'
                    conn.send(output.encode())
        except:
            pass
    obj.event.set()
    t.join()

if __name__ == '__main__':
    main()
