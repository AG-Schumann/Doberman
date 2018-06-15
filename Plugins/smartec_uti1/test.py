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

_input=1

print('test ...')
time.sleep(0.2)
ser.write('@'.encode('utf-8'))
time.sleep(0.2)
ser.write('2'.encode('utf-8'))
time.sleep(0.2)
ser.write('s'.encode('utf-8'))
time.sleep(0.2)

while 1 :
    # get keyboard input
    _input = input("<< ")
        # Python 3 users
        # input = input(">> ")
    if _input == 'exit':
        ser.close()
        exit()
    else:
        # send the character to the device
        _input_encoded = str(_input).encode('utf-8')
	print('encoding input to: ', _input_encoded)
        ser.write(_input_encoded)
        out = ''
        # let's wait one second before reading output (let's give device time to answer)
        time.sleep(1)

	converted_output = ''
	while ser.inWaiting() > 1:
	    out += ser.readline()
	    converted_output = out.decode('utf-8')
	if converted_output != '':
	    co = converted_output.split()
            coi = [int(i, 16) for i in co]
	    print(">> ", end=' ')
	    print(coi)

