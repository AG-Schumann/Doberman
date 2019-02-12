import socket
import signal
import time
import random
import argparse


class TestSensorLAN(object):
    def __init__(self):
        self.dev = socket.socket()
        self.dev.bind(('localhost',5000))
        self.dev.listen(1)
        self.interrupted = False
        signal.signal(signal.SIGINT, self.interrupt)
        signal.signal(signal.SIGTERM, self.interrupt)

    def interrupt(self, *args):
        print('Interrupted')
        self.interrupted = True

    def sandwich(self):
        while not self.interrupted:
            client, _ = self.dev.accept()
            msg = client.recv(1024)
            print('Received %s' % msg.decode())
            sleep_for = 0.0095*random.random()
            print('Processing time: %.3g' % sleep_for)
            time.sleep(sleep_for)
            if b'one' in msg:
                client.sendall(b'OK;%.3g\r\n' % 5*random.random())
            elif b'two' in msg:
                client.sendall(b'OK;%.3g\r\n' % random.randint(1,6))
            else:
                client.sendall(b'ERR;01\r\n')
            client.close()
            sleep_for = 0.1*random.random()
            print('Cleanup time: %.3g' % sleep_for)
            time.sleep(sleep_for)

def main():
    dev = TestSensorLAN()
    dev.sandwich()

if __name__ == '__main__':
    main()
