#! /usr/bin/env python3.3


class cryoGhost():
    """
    Class that holds a cryo controller dummy. Dummy is used in case of no etablished connection, eg as a simulation or self check mode.
    Prototypes the communiction protocoll. Every new communication channel function should look like it.
    """
    def __init__(self):
        self.tcmds = dict()
        self.tcmds['INP'] = 'inpo'
        self.tcmds['INPUT'] = self.tcmds['INP']
        self.tcmds['LOOP'] = 'loopo'
        self.tcmds['SYST'] = 'systemo'
        self.tcmds['SYSTEM'] = self.tcmds['SYST']
        self.tcmds['CONF'] = 'systemo'
        self.tcmds['CONFIG'] = self.tcmds['CONF']
        self.lIcmds = dict()
        self.lIcmds['TEMP'] = 'tempo'
        self.lIcmds['TEMPERATURE'] = self.lIcmds['TEMP']
        self.lIcmds['UNIT'] = 'unito'
        self.lIcmds['UNITS'] = self.lIcmds['UNIT']
        self.lIcmds['VAR'] = 'varo'
        self.lIcmds['VARIANCE'] = self.lIcmds['VAR']
        self.lIcmds['SLOP'] = 'slopo'
        self.lIcmds['SLOPE'] = self.lIcmds['SLOP']
        self.lIcmds['ALAR'] = 'alaro'
        self.lIcmds['ALARM'] = self.lIcmds['ALAR']
        self.lIcmds['NAM'] = 'namo'
        self.lIcmds['NAME'] = self.lIcmds['NAM']
        self.lLcmds = dict()
        self.lLcmds['SETPT'] = 'setpto'
        self.lLcmds['RANG'] = 'rango'
        self.lLcmds['RANGE'] = self.lLcmds['RANG']
        self.lLcmds['RAT'] = 'rato'
        self.lLcmds['RATE'] = self.lLcmds['RAT']
        self.lScmds = dict()
        self.lScmds['BEEP'] = 'beepo'
        self.lScmds['ADRS'] = 'adrso'
        self.lScmds['LOCK'] = 'locko'
        self.lScmds['LOCKOUT'] = self.lScmds['LOCK']
        self.lCcmds = dict()
        self.lCcmds['SAVE'] = 'saveo'
        self.lCcmds['REST'] = 'resto'
        self.lCcmds['RESTORE'] = self.lCcmds['REST']
        self.__ltcmds = ''
        self.__lIcmd = ''
        self.__lLcmd = ''
        self.__lScmd = ''
        self.__lCcmd = ''
        self.__answer = ''

    def write(self, message):
        """
        Sends the messages to the controller.
        """
        self.__ltcmds = str(message.rstrip())[:(str(message.rstrip()).find(' '))]
        if self.__ltcmds in self.tcmds:
            self.__answer = self.tcmds[__lcmd]
            if (str(message.rstrip())[((str(message.rstrip()).find(' '))+3):]).find(' ') != -1:
                __llcmd = str(message.rstrip())[((str(message.rstrip()).find(' '))+3):(str(message.rstrip())[((str(message.rstrip()).find(' '))+3):]).find(' ')]
            elif (str(message.rstrip())[((str(message.rstrip()).find(' '))+3):]).find('?') != -1:
                __llcmd = str(message.rstrip())[((str(message.rstrip()).find(' '))+3):(str(message.rstrip())[((str(message.rstrip()).find(' '))+3):]).find('?')]
            elif (str(message.rstrip())[((str(message.rstrip()).find(' '))+3):]).find(';') != -1:
                __llcmd = str(message.rstrip())[((str(message.rstrip()).find(' '))+3):(str(message.rstrip())[((str(message.rstrip()).find(' '))+3):]).find(';')]

            if __llcmd in self.lIcmds:
                self.__answer += self.lIcmds[__llcmd]
            elif __llcmd in self.lScmds:
                self.__answer += self.lScmds[__llcmd]
            elif __llcmd in self.lLcmds:
                self.__answer += self.lLcmds[__llcmd]
            elif __llcmd in self.lCcmds:
                self.__answer += self.lCcmds[__llcmd]
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


class cryoCommand(object):
    """
    Class that holds the cryo con controller 26 commands
    """
    def __init__(self, InpChannel = 'A', OutChannel = '1'):
        self.__device = cryoGhost()
        self.__OutChannel = None
        self.__InpChannel = None
        self.SetInpChannel(InpChannel)
        self.SetOutChannel(OutChannel)

    def SetInpChannel(self,channel):
        """
        Set the input channel of the controller for the program: A, B, C or D. Program uses this as standard in all commands iff no input channel specified. 
        """
        if not str(channel) in ['A','B','C','D']:
            return -1
        self.__InpChannel = str(channel)

    def SetOutChannel(self,channel):
        """
        Set the standard output channel of the controller for the program: 1,2,3 or 4. Program uses this as standard in all commands iff no output channel specified.
        """
        if not str(channel) in ['1','2','3','4']:
            return -1
        self.__OutChannel = str(channel)

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

    def getAlarmHighVal(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':UNIT K;ALAR:HIGH?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getInputName(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':NAME?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getAlarmLowVal(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':ALAR:LOW?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getAlarmStatus(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':ALAR?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getAlarmHighStatus(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':ALAR:HIEN?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getInputName(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':NAME?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getInputVBias(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':VBI?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getAlarmLowStatus(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':ALAR:LOEN?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getSetPoint(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':SETPT?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()[:-1]

    def getTemp(self, ichannel = None, units = 'K'):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        if not units in ['K','C','F','S']:
            return -2
        message = 'INP? '+ichannel+':units '+units+'\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getMaxTemp(self, ichannel = None, units = 'K'):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        if not units in ['K','C','F','S']:
            return -2
        message = 'INP '+ichannel+':units '+units+';MAX?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getMinTemp(self, ichannel = None, units = 'K'):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        if not units in ['K','C','F','S']:
            return -2
        message = 'INP '+ichannel+':units '+units+';MAX?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getTempVariance(self, ichannel = None, units = 'K'):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        if not units in ['K','C','F','S']:
            return -2
        message = 'INP '+ichannel+':units '+units+';VAR?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getTempSlope(self, ichannel = None, units = 'K'):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        if not units in ['K','C','F','S']:
            return -2
        message = 'INP '+ichannel+':units '+units+';SLOP?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getTempOffset(self, ichannel = None, units = 'K'):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        if not units in ['K','C','F','S']:
            return -2
        message = 'INP '+ichannel+':units '+units+';OFFS?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getTempStatDuration(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':STATS:TIM?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getInputSensor(self, ichannel = None):
        if ichannel is None:
            ichannel = self.__InpChannel
        if not str(ichannel) in ['A','B','C','D']:
            return -2
        message = 'INP '+ichannel+':SENS?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopType(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':TYPE?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopMaxPWR(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        message = 'LOOP '+ochannel+':MAXPWR?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()
    
    def getLoopStatus(self):
        message = 'Control?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopSource(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':source?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopRampStatus(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':RAMP?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopRampRate(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':RAT?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopPowerManualOut(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':PMAN?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopPowerOut(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':OUTPWR?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopLoadRsistance(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if ochannel != '1':
            return -2
        message = 'LOOP '+ochannel+':LOAD?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopPower(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':HTRREAD?\n'
        if self.sendMsg(message) != 0:
            return -1
        return str.replace(self.read(),'%','',1)

    def getLoopHeatsinkTemp(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not ochannel in ['1','2']:
            return -2
        message = 'LOOP '+ochannel+':HTRHST?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopMaxSetpoint(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':MAXS?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopVoltOutp(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':VSENSE?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopAmpOutp(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':ISENSE?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getLoopLoadResSense(self, ochannel = None):
        if ochannel is None:
            ochannel = self.__OutChannel
        if not str(ochannel) in ['1','2','3','4']:
            return -2
        message = 'LOOP '+ochannel+':LSENSE?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getSensorName(self, sid):
        sensli = [str(x) for x in range(0,69)]
        if not str(sid) in sensli:
            return -2
        message = 'SENS '+str(sid)+':NAME?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getSensorType(self, sid):
        sensli = [str(x) for x in range(0,69)]
        if not str(sid) in sensli:
            return -2
        message = 'SENS '+str(sid)+':TYP?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getInstrumentReg(self):
        message = 'SYSTEM:ISR?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getInstrumentName(self):
        message = 'SYSTEM:NAME?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getInstrumentDate(self):
        message = 'SYSTEM:DATE?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getInstrumentTime(self):
        message = 'SYSTEM:TIME?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getEventReg(self):
        message = '*ESR?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getStatusReg(self):
        message = '*STB?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()
        
    def getDeviceIdent(self):
        message = '*IDN?\n'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()
