#! /usr/bin/env python3.3
import logging
import time


class TeledyneCommand(object):

    """
    Class that holds the Teledyne flow controller THCD-100 commands
    """
    def __init__(self):
        self.__AddressLetter = 'a' #Addressletter can be changed manually on the controller (a-h), default = a

    def communicate(self, message): 
        """
        Note that this is a test function. TeledyneSerial has its own communicate fuction
        Message format is ("accc[?][arg]\r\n") 
        where a is the address letter, ccc the 3 letter (if not add spaces!) command, ? the query identification, arg is the comma separated parameter list
        """
        print(('I send %s and read the output'%str(message)))
        return 0


    """
    Commands:
    """
    def getAddressLetter(self):
        """
        Returns conntroller address letter (a-h) #
        """
        message = 'add?'	
        response = self.communicate(message)
        if response in [-1,-2]:
            return -1

        elif response[1] != 'ADDR: %s'%self.__AddressLetter:
            self.logger.debug("Invalide answer (%s). Message was %s"%(response[1],message))
            return -1
        else:
            return response[1].lstrip('ADDR: ')

    def readData(self):
        """
        Reads current data. Return format [data,status] status: 0=OK, 1=Overrange error
        """
        message = 'r  '	
        response = self.communicate(message)
        if response in [-1,-2]:
            return -1
        elif response[1][:6] == 'RANGE!':
            return response[6:11],1
        elif response[1][:5] != 'READ:':
            self.logger.debug("Invalide answer (%s). message was %s"%(response[1],message))
            return -1
        elif '-' in response[1][5:10]:
            return response[1][5:11],0
        else:
            return response[1][5:10],0

    def getSetpointMode(self):
        """
        gets the status of the setpoint mode: 0=Auto, 1=Open, 2=Closed
        """
        message = 'spm?'	
        response = self.communicate(message)
        if response in [-1,-2]:
            return -1
        elif response[1][:8] != 'SP MODE:':
            self.logger.debug("Invalide answer (%s). message was %s"%(response[1],message))
            return -1
        else:
            return response[1].lstrip('SP MODE:')

    def getUnit(self):
        """
        gets the displayed unit
        """
        message = 'uiu?'	
        response = self.communicate(message)
        if response in [-1,-2]:
            return -1
        elif response[1][:16] != 'INPUT UNITS STR:':
            self.logger.debug("Invalide answer (%s). message was %s"%(response[1],message))
            return -1
        else:
            return response[1][17:]

