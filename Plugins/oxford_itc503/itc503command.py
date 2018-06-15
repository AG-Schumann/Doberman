#! /usr/bin/env python3.3


class itc503Ghost():
    """
    Class that holds a oxford itc 503 controller dummy. Dummy is used in case of no etablished connection, eg as a simulation or self check mode.
    Prototypes the communiction protocoll. Every new communication channel function should look like it.
    """
    def __init__(self):
        self.tcmds = dict()
        self.tcmds[''] = ''
        self.lIcmds = dict()
        self.lIcmds[''] = ''
        self.lLcmds = dict()
        self.lLcmds[''] = ''
        self.lMcmds = dict()
        self.lMcmds['C0'] = 'C'
        self.lMcmds['C1'] = 'C'
        self.lMcmds['C2'] = 'C'
        self.lScmds = dict()
        self.lScmds['V'] = 'V'
        self.lCcmds = dict()
        self.lCcmds[''] = ''
        self.__ltcmds = ''
        self.__lIcmd = ''
        self.__lLcmd = ''
        self.__lMcmd = ''
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
            elif __llcmd in self.lMcmds:
                self.__answer += self.lMcmds[__llcmd]
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


class itc503Command(object):
    """
    Class that holds the itc503 controller commands
    """
    def __init__(self, sensor = 1, **kwds):
        self.__device = itc503Ghost()
        self.__sensor = None
        self.set_sensor(sensor)

        self.__alarm = [(0.,100.),(0.,330.),(0.,330.),(0.,330.)]
        if 'heater_alarm_high' in list(kwds.keys()):
            self.__alarm[0][1] = float(kwds['heater_alarm_high'])
        if 'heater_alarm_low' in list(kwds.keys()):
            self.__alarm[0][0] = float(kwds['heater_alarm_low'])
        if 'temperature_alarm_1_high' in list(kwds.keys()):
            self.__alarm[1][1] = float(kwds['temperature_alarm_1_high'])
        if 'temperature_alarm_2_high' in list(kwds.keys()):
            self.__alarm[2][1] = float(kwds['temperature_alarm_2_high'])
        if 'temperature_alarm_3_high' in list(kwds.keys()):
            self.__alarm[3][1] = float(kwds['temperature_alarm_3_high'])
        if 'temperature_alarm_1_low' in list(kwds.keys()):
            self.__alarm[1][0] = float(kwds['temperature_alarm_1_low'])
        if 'temperature_alarm_2_low' in list(kwds.keys()):
            self.__alarm[2][0] = float(kwds['temperature_alarm_2_low'])
        if 'temperature_alarm_3_low' in list(kwds.keys()):
            self.__alarm[3][0] = float(kwds['temperature_alarm_3_low'])
    
    def set_temperature_alarm(self, sensor, alarmvalues):
        """
        Set the alarm values for the temperature sensors; 1,2,3
        """
        if not sensor in range(1,4):
            return -1
        if not isinstance(alarmvalues, tuple):
            return -1
        if float(alarmvalues[0]) > float(alarmvalues[1]):
            __tmp = alarmvalues[0]
            alarmvalues[0] = alarmvalues[1]
            alarmvalues[1] = __tmp
        self.__alarm[sensor] = (float(alarmvalues[0]), float(alarmvalues[1]))
        return 1
    
    def set_heater_alarm(self, alarmvalues):
        """
        Set the alarm values for the heater, in percent
        """
        if float(alarmvalues[0]) > float(alarmvalues[1]):
            __tmp = alarmvalues[0]
            alarmvalues[0] = alarmvalues[1]
            alarmvalues[1] = __tmp
        self.__alarm[0] = (float(alarmvalues[0]), float(alarmvalues[1]))
        return 1

    def set_sensor(self,sensor):
        """
        Set the sensor of the controller for the program: 0, 1 or 2. Program uses this as standard in all commands iff no sensor channel specified. 
        """
        if not int(sensor) in [0,1,2]:
            return -1
        self.__sensor = int(sensor)

    def sendMsg(self, message):
        """
        Send the message to the device, prototype. Shouldn't be used directly. Prefered way if command function is missing: add it in the code.
        """
        message = str(message).rstrip('\n').rstrip()
        self.__device.write((message+'\r\n').encode('utf-8'))
        return 0

    def read(self):
        """
        Get answer from the Controller. Returns a string
        """
        result = self.__device.readline().strip()+'\n'
        return result.rstrip()

    def set_control(self, control = 'LOCAL'):
        """
        Change the control setting: 'LOCAL_LOCK', 'REMOTE_LOCK', 'LOCAL_UNLOCK','REMOTE_UNLOCK';
        LOCAL  & LOCKED (Default State)
        REMOTE & LOCKED (Front Panel Disabled)
        LOCAL  & UNLOCKED
        REMOTE & UNLOCKED (Front Panel Active)
        """
        message = None
        if control == 'LOCAL_LOCK':
            message = 'C0'
        elif control == 'REMOTE_LOCK':
            message = 'C1'
        elif control == 'LOCAL_UNLOCK':
            message == 'C2'
        elif control == 'REMOTE_UNLOCK':
            message == 'C3'
        else:
            return -2
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def get_itc503version(self):
        """
        It returns a message indicating the instrument type and firmware version number.
        """
        if self.sendMsg('V') != 0:
            return -1
        return self.read()

    def set_communication_protocol(self,protocolit = 0):
        """ 0: Normal (Default Value)
            2: Sends <LF> after each <CR>
        """
        if not protocolit in [0,2]:
            return -2
        message = 'Q%s'%str(parameter)
        if self.sendMsg(message) != 0:
            return -1
        return self.read()


    def get_status(self):
        """
        returns the ITC 503 status:
        XnAnCnSnnHnLn
        where the digits "n" have the following meaning:
        Xn                           SYSTEM STATUS                  (Always zero currently)
        An                          AUTO/MAN STATUS            (n as for A COMMAND but see below)
        Cn                           LOC/REM/LOCK STATUS      (n as for C COMMAND)
        Snn                         SWEEP STATUS                    (nn=0-32 as follows)
        nn=0                                     SWEEP NOT RUNNING
        nn=2P-1                                SWEEPING to step P
        nn=2P                                   HOLDING  at step P
        Hn                          CONTROL SENSOR               (n as for H COMMAND)
        Ln                           AUTO-PID STATUS               (n as for L COMMAND)
        """
        if self.sendMsg('X') != 0:
            return -1
        return self.read()

    def get_auto_man_status(self):
        """
        return the run mode:
        HEATER MANUAL, GAS MANUAL: [false, false]
        HEATER AUTO, GAS MANUAL: [true, false]
        HEATER MANUAL, GAS AUTO: [false, true]
        HEATER AUTO, GAS AUTO: [true, true]
        """
        decode = self.get_status()
        if 'A0' in decode:
            return (False, False)
        elif 'A1' in decode:
            return (True, False)
        elif 'A2' in decode:
            return (False, True)
        elif 'A3' in decode:
            return (True, True)
        return -2

    def get_heater_sensor(self):
        """
        return the sensor controlling the heater: 1, 2 or 3
        """
        decode = self.get_status()
        if 'H1' in decode:
            return 1
        elif 'H2' in decode:
            return 2
        elif 'H3' in decode:
            return 3
        return -1

    def get_PID_status(self):
        """
        return the auto PID status: true for used, false for not used
        """
        decode = self.get_status()
        if 'L0' in decode:
            return False
        elif 'L1' in decode:
            return True
        return -1

    def set_auto_man_status(self, auto_man_status):
        """
        set the run mode: auto_man_status = 
        HEATER MANUAL, GAS MANUAL: [false, false]
        HEATER AUTO, GAS MANUAL: [true, false]
        HEATER MANUAL, GAS AUTO: [false, true]
        HEATER AUTO, GAS AUTO: [true, true]
        """
        if not isinstance(auto_man_status, list) and not isinstance(auto_man_status, tuple):
            return -2
        auto_man_status = (auto_man_status[0],auto_man_status[1])
        message = None        
        if auto_man_status == (True, True):
            message = 'A3'
        elif auto_man_status == (False, False):
            message = 'A0'
        elif auto_man_status == (True, False):
            message = 'A1'
        elif auto_man_status == (False, True):
            message = 'A2'
        else:
            return -2
        if self.sendMsg(message) != 0:
            return -1
        answer = self.read()
        if auto_man_status == (True, True) and answer == '?A3':
            return 0
        elif auto_man_status == (False, False) and answer == '?A0':
            return 0
        elif auto_man_status == (True, False) and answer == '?A1':
            return 0
        elif auto_man_status == (False, True) and answer == '?A2':
            return 0
        return -1

    def get_parameter(self, parameter):
        """
        returns the value stored with this parameter
        R0            SET TEMPERATURE
        R1            SENSOR 1 TEMPERATURE
        R2            SENSOR 2 TEMPERATURE
        R3            SENSOR 3 TEMPERATURE
        R4            TEMPERATURE ERROR (+ve when SET > MEASURED)
        R5            HEATER O/P (as % of current limit)
        R6            HEATER O/P (as Volts, approx.) 
        R7            GAS FLOW O/P (arbitrary units)
        R8            PROPORTIONAL BAND
        R9            INTEGRAL ACTION TIME
        R10          DERIVATIVE ACTION TIME
        R11          CHANNEL 1 FREQ/4
        R12          CHANNEL 2 FREQ/4
        R13          CHANNEL 3 FREQ/4
        """
        if not int(parameter) in range(0,14):
            return -2
        message = 'R%s'%str(parameter)
        if self.sendMsg(message) != 0:
            return -1
        param = self.read()
        try:
            param = param[1:]
        except TypeError:
            pass
        return param
    
    def get_temperature(self, sensor = None):
        """
        R0            SET TEMPERATURE
        R1            SENSOR 1 TEMPERATURE
        R2            SENSOR 2 TEMPERATURE
        R3            SENSOR 3 TEMPERATURE
        """
        if sensor is None:
            sensor = self.__sensor
        if not sensor in range(0,4):
            return -2
        try:
            temperature = float(self.get_parameter(sensor))
        except:
            temperature = -1
        return temperature
    
    def get_heater_load(self, percent = True):
        """
        percent 1: returns load in % else in V
        """
        if percent:
            hload = self.get_parameter(5)
        else:
            hload = self.get_parameter(6)
        try:
            hload = float(hload[1:])
        except:
            hload = -1
        return hload

    def get_alarm_status(self,channel):
        channel = int(channel)
        if channel in range(1,4):
            if self.get_temperature(channel) < self.__alarm[channel][0]:
                return -1
            elif self.get_temperature(channel) > self.__alarm[channel][1]:
                return -2
            else:
                return 0
        elif channel == 0:
            if self.get_heater_load() < self.__alarm[0][0]:
                return -1
            elif self.get_heater_load() > self.__alarm[0][1]:
                return -2
            else:
                return 0
        return -3
