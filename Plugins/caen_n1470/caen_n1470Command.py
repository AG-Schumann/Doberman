#! /usr/bin/env python3.3
import logging
import time


class caen_n1470Command(object):

    """
    Class that holds the newport caen_n1470 i3200 controller commands
    """
    def __init__(self):
        pass


    def communicate(self, message): 
        """
        Note that this is a test function. caen_n1470Serial has its own communicate fuction, adding automatically $BD:**, in front of a message
        Message format is ("$BD:**,CMD:***,CH*,PAR:***,VAL:***.**\r\n")
        Response from caen_n1470Serial is: Value itself; full response would be:
        #BD:**,CMD:OK,VAL:*** command Ok *** = value for command to individual Channel
#BD:**,CMD:OK,VAL:*;*;*;* command Ok *;*;*;* = values Ch0,1,2,3 for command to all Channels
so the * after VAL: only is returned 
        """
        print(('I send %s and read the output'%str(message)))
        return 0

    """
    Commands:
    """
    def getSN(self):
        """
        Returns modules SN
        """
        message = 'CMD:MON,PAR:BDSNUM'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getVset(self, channel):
        """
        Read out VSET value ( XXXX.X V )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:VSET')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getVMinset(self, channel):
        """
        Read out VSET minimum value ( 0 V)
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:VMIN')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getVMaxset(self, channel):
        """
        Read out VSET maximum value ( 8000.0 V )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:VMAX')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getV(self, channel):
        """
        Read out VMON value ( XXXX.X V )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:VMON')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getIset(self, channel):
        """
        Read out ISET value ( XXXX.XX muA )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:ISET')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getIMinset(self, channel):
        """
        Read out IMIN value ( XXXX.XX muA )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:IMIN')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getIMaxset(self, channel):
        """
        Read out IMAX value ( XXXX.XX muA )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:IMAX')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getI(self, channel):
        """
        Read out IMON value ( XXXX.XX muA )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:IMON')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getMaxVset(self, channel):
        """
        Read out MAXVSET value ( XXXX V )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:MAXVSET')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getMinVset(self, channel):
        """
        Read out MAXVSET minimum value ( 0 V )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:MVMIN')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getMinVset(self, channel):
        """
        Read out MAXVSET maximum value ( 0 V )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:MVMAX')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getIRange(self, channel):
        """
        Read out IMON RANGE value ( HIGH / LOW )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:IMRANGE')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getRup(self, channel):
        """
        Read out RAMP UP value ( XXX V/S )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:RUP')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getRupmin(self, channel):
        """
        Read out RAMP UP minimum value ( 1 V/S )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:UPMIN')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getRupmax(self, channel):
        """
        Read out RAMP UP maximum value ( 500 V/S )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:RUPMAX')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getRdwn(self, channel):
        """
        Read out RAMP DOWN value ( XXX V/S )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:RDW')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getRdwnmin(self, channel):
        """
        Read out RAMP DOWN minimum value ( 1 V/S )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:RDWMIN')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getRdwnmax(self, channel):
        """
        Read out RAMP DOWN maximum value (500 V/S)
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:RDWMAX')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getTrpTme(self, channel):
        """
        Read out TRIP time value ( XXXX.X S )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:TRIP')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getTrpTmeMin(self, channel):
        """
        Read out TRIP time minimum value ( 0 S )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:TRIPMIN')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getgetTrpTmeMax(self, channel):
        """
        Read out TRIP time maximum value ( 1000.0 S )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:TRIPMAX')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getPwrStatus(self, channel):
        """
        Read out POWER DOWN value ( RAMP / KILL )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:PDWN')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getPolarity(self, channel):
        """
        Read out POLARITY value ( '+' / '-' )
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:POL')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getChStatus(self, channel):
        """
        Read out Channel status value ( XXXXX )
        Bit Function
Bit 0 -> ON      1 : ON 0 : OFF
Bit 1 -> RUP     1 : Channel Ramp UP
Bit 2 -> RDW     1 : Channel Ramp DOWN
Bit 3 -> OVC     1 : IMON >= ISET
Bit 4 -> OVV     1 : VMON > VSET + 250 V
Bit 5 -> UNV     1 : VMON < VSET - 250 V
Bit 6 -> MAXV    1 : VOUT in MAXV protection
Bit 7 -> TRIP    1 : Ch OFF via TRIP (Imon >= Iset during TRIP)
Bit 8 -> OVP     1 : Power Max
                        Power Out > 9.3W for VOUT <= 3KV
                        Power Out > 8.2W for VOUT > 3KV
Bit 9 -> OVT     1: TEMP > 105C
Bit 10 -> DIS    1 : Ch disabled (REMOTE Mode and Switch on OFF position)
Bit 11 -> KILL   1 : Ch in KILL via front panel
Bit 12 -> ILK    1 : Ch in INTERLOCK via front panel
Bit 13 -> NOCAL  1 : Calibration Error
Bit 14, 15 -> N.C.
        """
        if not channel in [0,1,2,3]:
            return -2
        message = ('CMD:MON,CH:%s,PAR:STAT')%(str(channel))
        response = self.communicate(message)
        if response == -1:
            return -1
        response = [response[0],response[1],response[2],response[3],response[4]]
        return response

    def getChPresent(self):
        """
        Read out number of Channels present ( 4, 2, 1)
        """
        message = 'CMD:MON,PAR:BDNCH'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getFWRel(self):
        """
        $BD:xx,CMD:MON,PAR:BDFREL Read out Firmware Release ( XX.X )
        """
        message = 'CMD:MON,PAR:BDFREL'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getInterlockStatus(self):
        """
        Read out INTERLOCK status ( YES/NO )
        """
        message = 'CMD:MON,PAR:BDILK'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getInterlockMode(self):
        """
        Read out INTERLOCK mode ( OPEN/CLOSED )
        """
        message = 'CMD:MON,PAR:BDILKM'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getLocBusTermin(self):
        """
        Read out LOCAL BUS Termination status ( ON/OFF )
        """
        message = 'CMD:MON,PAR:BDTERM'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response


    def getCntrlMode(self):
        """
        Read out Control Mode (LOCAL / REMOTE )
        """
        message = 'CMD:MON,PAR:BDCTR'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response


    def getBoardAlarm(self):
        """
        Read out Board Alarm status value ( XXXXX )
        Bit 0 -> CH0      1 : Ch0 in Alarm status
        Bit 1 -> CH1      1 : Ch1 in Alarm status
        Bit 2 -> CH2      1 : Ch2 in Alarm status
        Bit 3 -> CH3      1 : Ch3 in Alarm status
        Bit 4 -> PWFAIL   1 : Board in POWER FAIL
        Bit 5 -> OVP      1 : Board in OVER POWER
        Bit 6 -> HVCKFAIL 1 : Internal HV Clock FAIL (!= 200+-10kHz)
        """
        message = 'CMD:MON,PAR:BDALARM'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response


