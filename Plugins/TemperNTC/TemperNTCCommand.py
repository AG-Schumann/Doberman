#! /usr/bin/env python3.3


class temperNTCGhost():
    """
    Class that holds a TemperNTC controller dummy. Dummy is used in case of no etablished connection, eg as a simulation or self check mode.
    Prototypes the communiction protocoll. Every new communication channel function should look like it.
    """
    def __init__(self):
        self.tcmds = dict()
        self.tcmds[(0xa1, 1, 0x300, 0x1, 256, 0)] = '999.9'
        self.tcmds[('\x01\x80\x33\x01\x00\x00\x00\x00')] = '888.8'
        self.__ltcmds = ''
        self.__answer = ''

    def write(self, message):
        """
        Sends the messages to the controller.
        """
        self.__ltcmds = str(message.rstrip())[:(str(message.rstrip()).find(' '))]
        if self.__ltcmds in self.tcmds:
            self.__answer = self.tcmds[__lcmd]
        else:
            self.__answer = ''
        return len(message)

    def read(self, size = 1):
        """
        reads the messages from the controller output. Size is a length indicator up where the output will be read.
        """
        res = self.__answer[:size]
        self.__answer = self.__answer[size:]
        return res

    def readline(self):
        """
        reads the complete output buffer of the controller.
        """
        res = self.__answer
        self.__answer = ''
        return res

    def open(self):
        """
        Opens the connection on the communication channel to the controller
        """
        return None

    def close(self):
        """
        Takes care for properly closing the connection to the controller.
        """
        return None


class temperNTCCommand(object):
    """
    Class that holds the temperNTC usb temperature sensor commands
    """
    def __init__(self, temperature_unit = 'K'):
        self.__device = temperNTCGhost()

    def sendMsg(self, message):
        """
        Send the message to the device, prototype. Shouldn't be used directly. Prefered way if command function is missing: add it in the code.
        """
        message = str(message).rstrip('\n').rstrip()
        self.__device.write((message+'\n').encode('utf-8'))
        return 0

    def read(self):
        """
        Get answer from the Controller. Returns a string
        """
        result = self.__device.readline().strip()+'\n'
        return result.rstrip()

    def getLocalTemp(self):
        message = 'INP '+ichannel+':ALAR:LOW?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getRemoteTemp(self):
        message = 'INP '+ichannel+':ALAR?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()
