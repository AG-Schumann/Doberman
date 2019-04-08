import socket
import time
import random
import argparse
import re


class TestSensorLAN(object):
    """
    Software-only sensor for testing purposes
    Message start token: *
    Message end token: \r\n

    Read request format: READ:<name>
    Read return format: OK;<value>
    Command format: SET:<param>=<value>
    """
    def __init__(self):
        self.dev = socket.socket()
        self.dev.bind(('localhost',5000))
        self.dev.listen(1)
        self.sides = 6

    def sandwich(self):
        print('Ready')
        client, _ = self.dev.accept()
        with client:
            while True:
                try:
                    msg = client.recv(1024)
                    print('Received %s' % msg)
                    if not msg:
                        break
                    sleep_for = 0.006*random.random()
                    print('Processing time: %.3g' % sleep_for)
                    time.sleep(sleep_for)
                    payload = b''
                    if b'READ:' in msg:
                        req = msg.rstrip().split(b'READ:')[1]
                        if req == b'one':
                            payload = b'OK;' + 5*random.random()
                        elif req == b'two':
                            payload = self.dice()
                        else:
                            payload = b'ERR;01'
                    elif b'SET' in msg:
                        m = re.search(b'SET:(?P<param>[^=]+)=(?P<value>.+)\r\n', msg)
                        if not m:
                            payload = b'ERR;10'
                        else:
                            if m.group('param') == b'sides':
                                try:
                                    self.sides = int(m.group('value'))
                                except:
                                    payload = b'ERR;11'
                                else:
                                    payload = b'OK;'
                            else:
                                payload = b'ERR;12'
                    else:
                        payload = b'ERR;00'
                    client.sendall(
                    #client.close()
                    sleep_for = 0.05*random.random()
                    print('Cleanup time: %.3g' % sleep_for)
                    time.sleep(sleep_for)
                    print()
                except:
                    break

    def dice(self):
        return random.randint(1,self.sides)

def main():
    dev = TestSensorLAN()
    dev.sandwich()

if __name__ == '__main__':
    main()
