#! /usr/bin/env python3.3
import logging
import time


class iseriesCommand(object):

    """
    Class that holds the newport iseries i3200 controller commands
    """
    def __init__(self):
        pass


    def communicate(self, message): 
        """
        Note that this is a test function. iseriesSerial has its own communicate fuction
        Message format is ("*Z01\r\n")
        """
        print('I send %s and read the output'%str(message))
        return 0


    """
    Commands:
    """
    def hardReset(self):
        """
        After modifying any settings with use of W prefix commands, a Hard Reset command should be sent in order to load changes into Volatile memory.
        """
        message = 'Z02'	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getID(self):
        """
        Returns conntroller ID
        """
        message = 'R05'	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getAddress(self):
        """
        Returns conntroller ID
        """
        message = 'R21'	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def enableAlarm(self,alarmNumber):
        """
        Enables the alarm 1 or 2 
        """
        if str(alarmnumber) not in ['1','2']:
            logging.warning('Invalid alarm number. Alarm not enabled')
            return 0
        message = 'E0'+str(alarmnumber)	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def disableAlarm(self,alarmNumber):
        """
        Disables the alarm 1 or 2 
        """
        if str(alarmnumber) not in ['1','2']:
            logging.warning('Invalid alarm number. Alarm not disabled')
            return 0
        message = 'D0'+str(alarmnumber)	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getDataString(self):
        """
        Returns data as string
        """
        message = 'V01'	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getDisplayedValue(self):
        """
        Returns displayed value
        """
        message = 'X01'	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getPeakValue(self):
        """
        Returns the peak value
        """
        message = 'X02'	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getValleyValue(self):
        """
        Returns the valley value
        """
        message = 'X03'	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response
    def getCommunicationParameters(self):
        """
        Returns communication parameters 
        """
        message = 'R10'	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getSetpoint(self, SetpointNumber):
        """
        Returns the value of Setpoint 1 or 2
        """
        if str(SetpointNumber) not in ['1','2']:
            logging.warning('Invalid setpoint number.')
            return -1
        message = 'R0'+str(SetpointNumber)	
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getAlarmHigh(self, AlarmNumber):
        """
        Returns the high alarm level 1 or 2
        """
        if str(AlarmNumber) == '1':
            message = 'R13'
        elif str(AlarmNumber) == '2':
            message = 'R16'
        else:
            logging.warning('Invalid alarm number.')
            return -1
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getAlarmLow(self, AlarmNumber):
        """
        Returns the low alarm level 1 or 2
        """
        if str(AlarmNumber) == '1':
            message = 'R12'
        elif str(AlarmNumber) == '2':
            message = 'R15'
        else:
            logging.warning('Invalid alarm number.')
            return -1
        response = self.communicate(message)
        if response == -1:
            return -1
        return response


