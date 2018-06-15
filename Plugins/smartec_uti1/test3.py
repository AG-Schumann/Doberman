#! /usr/bin/env python3.3
import time
import serial

# configure the serial connections (the parameters differs on the device you are connecting to)
ser = serial.Serial(
    port='/dev/ttyUSB5',
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS
)

ser.isOpen()

print('Enter your commands below.\r\nInsert "exit" to leave the application.')

input=1

print('test ...')
time.sleep(0.2)
#ser.write('9'.encode() + '\r\n')
ser.write('2'.encode('utf-8'))
time.sleep(0.2)
#ser.write('2 \r\n')

while 1 :
    # get keyboard input
    input = eval(input(">> "))
        # Python 3 users
        # input = input(">> ")
    if input == 'exit':
        ser.close()
        exit()
    else:
        # send the character to the device
        ser.write(input + '\r\n')
        out = ''
        # let's wait one second before reading output (let's give device time to answer)
        time.sleep(1)
        while ser.inWaiting() > 0:
            out += ser.read(1)

        if out != '':
            print((">>" + out))
