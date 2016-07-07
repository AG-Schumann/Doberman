#! /usr/bin/env python3.3
import logging
import time
import serial

class pressureCommand(object):

    """
    Class that holds the pressure gauge controller TPG 61 commands
    """
    def __init__(self):
        self.__ETX = chr(3)  # \x03
        self.__CR = chr(13)
        self.__LF = chr(10)
        self.__ENQ = chr(5)  # \x05
        self.__ACK = chr(6)  # \x06
        self.__NAK = chr(21)  # \x15

        self.__pressure_unit = ['mbar/bar','Torr','Pascal']
        self.__gauge_control = ['No Control','Automatic','Manual','Selfcontrol/Hot start']
        self.__on_off = ['OFF','ON']
        self.__on_off_auto = ['OFF','ON','AUTO']
        self.__measurement_status=['OK','Underrange','Overrange','Sensor Error','Sensor Off','No Sensor','ID Error']
        self.__transmission_rate = ['9600','19200','38400'] #baud
        self.__manual_automatic = ['Manual','Automatic']

    """
    protocol for communicate with TPG 61

    write(message<CR>[<LF>]):
        if read()==<NAK>:
            logging.error('No access to this function')
            return 0
        elif read()=!<ACK><CR><LF>:
            logging.error('Can not send message')
        else: 
            return
    read():
        write(<ENQ>)
        readline()
    """

    def sendMsg(self, message): 
        """
        Note that this is a test function. pressureSerial has its own sendMsg
        """
        message = str(message)+self.__CR+self.__LF
        self.__device.write(message)
        response = self.__device.readline()
        response = response.rstrip(self.__LF).rstrip(self.__CR)
        if response == self.__NAK:
            logging.warning('Negative acknowledgement for sending a message.')
            return -1
        elif response != self.__ACK:
            logging.error('Can not communicate with device. Unknown response.')
            return -1
        else:
            return 0

    def read(self):
        """
        Note that this is a test function. pressureSerial has its own read
        """
        self.__device.write(self.__ENQ)
        response = self.__device.readline()
        return response.rstrip(self.__LF).rstrip(self.__CR)


    """
    Commands:
    """

    def getPressureData(self, gauge='PR1'):
        """
        PR1 for gauge1, PR2 for gauge2 (Note that the TPG 61 can only connect to one gauge)
        Returns: Status of gauge, Measurement value
        """
        if gauge not in ['PR1','PR2']:
            logging.warning('Invalid gauge number. Set to PR1 (gauge 1) by default')
            gauge = 'PR1'
        message = str(gauge) 		
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        return response

    def getContinuousPressureData(self,mode):
        """
        mode: 0 =100 ms ,  1 = 1 s (default) , 2 = 1 min
        Caution: The device will be unable to communicate during the time defined by mode
        """
        if mode not in [0,1,2]:			 
            mode ='1'
            logging.warning('Mode for continuous pressure data set to 1 (1 s) by default')  
        message = 'COM,'+str(mode)	
        if self.sendMsg(message) != 0:
            return -1
        response=self.read()
       
        if response == self.__ACK or self.__NAK:      # first fix of error, that ENQ is answered by ACK/NAK or that the data is send too early (without sendig __ACK) TODO: Improve that for all functions 
            response = ['Communication error','']
            logging.warning('Negative acknowledgement for sending a message ENQ.')
        else:
            response=response.split(',')
            response[0] = str(self.__measurement_status[int(response[0])])
        return response

    def getGaugeTyp(self):
        """
        Returns the typ of the attached gauge. Gauge 2 will always be noSEn
        """
        message = 'TID' 		
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        if response[0]=='noSEn':
            logging.warning('No sensor attached')
        elif response[0]=='noid':
            logging.warning('Sensor not identified')
        return response[0]

    def getErrorStatus(self):
        """
        Retruns the error status of the controller
        0000 = No error, 1000 = error (Controller error), 0100 = NO HWR (No hardware)
        0010 = PAR (indmissible parameter), 0001 = SYN (Syntax error)
        """
        message = 'ERR'		
        if self.sendMsg(message) != 0:
            return -1
        ErrorMessage = self.read()  
        if ErrorMessage=='0000':
            ErrorMessage = 'No Error'		 
            logging.info('No Error reported')	
        elif ErrorMessage=='1000':
            ErrorMessage = 'Controller Error'			 
            logging.error('Controller error reported')
        elif ErrorMessage=='0100':
            ErrorMessage = 'No hardware found'			 
            logging.error('No hardware found') 	
        elif ErrorMessage=='0010':		
            ErrorMessage = 'Indmissible parameter Error'		
            logging.error('Indmissible parameter error') 	 	
        elif ErrorMessage=='0001':	
            ErrorMessage = 'Syntax Error'			
            logging.error('Syntax error') 		
        return ErrorMessage		


    def resetGauge(self):
        """ 
        Cancels currently active error and goes back to measurement mode.
        Returns a List of all present errors. (error 8 is missing intentionally)
        """
        message = 'RES' 		#
        if self.sendMsg(message) != 0:
            return -1
        ErrorString = str(self.read())
        ErrorList = ErrorString.split(",")
        if '0' in ErrorList:
            logging.info('No error')
        else:
            if '1' in ErrorList:
                logging.info('Watchdog has responded to error(s)')
            if '2' in ErrorList:
                logging.error('Task fail error')
            if '3' in ErrorList:
                logging.error('EPROM error')
            if '4' in ErrorList:
                logging.error('RAM error')
            if '5' in ErrorList:
                logging.error('EEPROM error')
            if '6' in ErrorList:
                logging.error('Display error')
            if '7' in ErrorList:
                logging.error('A/D converter error')
            if '9' in ErrorList:
                logging.error('Gauge 1 error')
            if '10' in ErrorList:
                logging.error('Gauge 1 identification error')
            if '11' in ErrorList:
                logging.error('Gauge 2 error')   
            if '12' in ErrorList:
                logging.error('Gauge 2 identification error')   
        return ErrorList

    def setFilterValue(self, filtervalue1):
        """
        Sets filter time constant (measurement value filter)
        Set and return: 0 = fast, 1= medium (default), 2 = slow
        """	
        if filtervalue1 not in [0,1,2]:		
            filtervalue1 = 1
            logging.warning('Filter Value set to 1 (medium) by default')
        message = 'FIL,'+str(filtervalue1)+',1'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getFilterValue(self):	
        """
        Reads filter time constant (measurement value filter)
        Returns: 0 = fast, 1= medium (default), 2 = slow
        """
        message = 'FIL'
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def setCalibrationfactor(self, axis, calibrationfactor):	
        """
        Sets and Returns the calibrationfactor.
        Factor used to calibrate gauge for other gases than N2
        """
        if axis not in ['log','lin']:
            axis = 'lin'
            logging.warning('Wrong/no axis type for calibrationfactor. Set to linear')
        if axis == 'lin' and calibrationfactor < 0.5:
            calibrationfactor = 1
            logging.warning('Calibrationfactor too low. Set to 1')
        elif axis == 'lin' and calibrationfactor > 2:
            calibrationfactor = 1
            logging.warning('Calibrationfactor too high. Set to 1')
        elif axis == 'log' and calibrationfactor < 0.1:
            calibrationfactor = 1
            logging.warning('Calibrationfactor too low. Set to 1')
        elif axis == 'log' and calibrationfactor > 9.99:
            calibrationfactor = 1
            logging.warning('Calibrationfactor too high. Set to 1')
        message = 'CAL,'+"%0.3f"%calibrationfactor+',1.000'
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        return response[0]

    def getCalibrationfactor(self):
        """
        Returns the calibrationfactor.
        Factor used to calibrate gauge for other gases than N2
        """	
        message = 'CAL'
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        return response[0]

    def setOffsetCorrection(self, offsetCorrection):
        """
        Sets and Returns the offset correction (for linear gauges only)
        0 = off (default), 1 = on, 2 = auto (offset measurement)
        """
        if offsetCorrection not in [0,1,2]:		
            offsetCorrection = 0
            logging.warning('Offset Correction set to 0 (off) by default')
        message = 'OFC,'+str(offsetCorrection)+',0'
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        return self.__on_off_auto[int(response[0])]

    def getOffsetCorrection(self):
        """
        Returns the offset correction (for linear gauges only)
        0 = off (default), 1 = on, 2 = auto (offset measurement)
        """
        message = 'OFC'
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        return self.__on_off_auto[int(response[0])]

    def setUnderrangeControl(self, underrangeControl):	
        """
        Sets and Returns the setting of the underrange control
        0 = off (default), 1 = on, 
        """
        if underrangeControl not in [0,1]:	
            underrangeControl = 0
            logging.warning('Underrange Control set to 0 (off) by default')
        message = 'PUC,'+str(underrangeControl)+',0'
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        return self.__on_off[int(response[0])]

    def getUnderrangeControl(self):
        """
        Sets and Returns the setting of the underrange control
        0 = off (default), 1 = on, 
        """		
        message = 'PUC'
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        return self.__on_off[int(response[0])]

    def setGaugeControl(self, gaugeActivation, gaugeDeactivation, ONthreshold, OFFthreshold):	
        """
        Sets gauge control settings. Returns: [status for activation, status for deactivation, ON threshold, OFF threshold]
        status: 0 = no control, 1 = automatic (de)activation, 2 = manual (de)activation (defaut), 3 = external (de)activation, 4 = selfcontrol/hot start
        """	
        if gaugeActivation not in [0,1,2,3,4]:		
            gaugeActivation = 2
        if gaugeDeactivation not in [0,1,2,3,4]:
            gaugeDeactivation = 2
        if gaugeActivation == 1 or gaugeDeactivation == 1:
            if ONthreshold < 0 or OFFthreshold < 0 or ONthreshold > OFFthreshold:
                gaugeDeactivation = 2
                gaugeActivation = 2
                logging.warning('Invalid Threshold limits for gauge control. Gauge set to manual activation and deactivation.')
        message = 'SC1,'+str(gaugeActivation)+','+str(gaugeDeactivation)+','"%.2e"%ONthreshold+','"%.2e"%OFFthreshold
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        response[0]=self.__gauge_control[int(response[0])]
        response[1]=self.__gauge_control[int(response[1])]
        return response

    def getGaugeControl(self):
        """
        Returns: [status for activation, status for deactivation, ON threshold, OFF threshold]
        status: 0 = no control, 1 = automatic (de)activation, 2 = manual (de)activation (defaut), 3 = external (de)activation, 4 = selfcontrol/hot start
        """		
        message = 'SC1'
        if self.sendMsg(message) != 0:
            return -1
        response=self.read().split(',')
        response[0]=self.__gauge_control[int(response[0])]
        response[1]=self.__gauge_control[int(response[1])]
        return response
  
    def setPressureUnit(self, pressureUnit):	
        """
        Sets and retruns pressure unit: 0 = mbar/bar (default), 1 = Torr, 2 = Pascal
        """
        if pressureUnit not in [0,1,2]:		
            pressureUnit = 0
            logging.warning('Pressure Unit set to 0 (mbar/bar) by default')
        message = 'UNI,'+str(pressureUnit)
        if self.sendMsg(message) != 0:
            return -1
        return self.__pressure_unit[int(self.read())]

    def getPressureUnit(self):	
        """
        Retruns pressure unit: 0 = mbar/bar (default), 1 = Torr, 2 = Pascal
        """
        message = 'UNI'
        if self.sendMsg(message) != 0:
            return -1
        return  self.__pressure_unit[int(self.read())]

    def setTransmissionRate(self, transmissionRate):
        """
        Sets and retruns transmission rate: 0 = 9600 baud (default), 1 = 19200 baud, 2 = 38400 baud
        """        	
        if transmissionRate not in [0,1,2]:		
            transmissionRate = 0
            logging.warning('Transmission rate set to 0 (9600 baud) by default')
        if transmissionRate != 0:
            logging.warning('Transmission rate changed. Make sure serial connection still works.')
        message = 'BAU,'+str(transmissionRate)
        if self.sendMsg(message) != 0:
            return -1
        return self.__transmission_rate[int(self.read())]

    def getTransmissionRate(self):
        """
        Retruns transmission rate: 0 = 9600 baud (default), 1 = 19200 baud, 2 = 38400 baud
        """  	
        message = 'BAU'
        if self.sendMsg(message) != 0:
            return -1
        return self.__transmission_rate[int(self.read())]

    def saveParameter(self, saveParameter):	
        if saveParameter not in [0,1]:		#0 = save default parameters, 1 = save user parameters
            logging.warning('Parameter not saved. Use (0) to save default parameters and (1) to save user parameters')
            return 0
        message = 'SAV,'+str(saveParameter)
        if self.sendMsg(message) != 0:
            return -1
        return self.read()

    def getSwitchingFunction(self, functionnumber = 'All'):	
        if functionnumber not in [1,2,3,4,'All']:
            functionnumber = 'All'
            logging.warning('Invalid function number, all Switching functions are returned')        
        if functionnumber == 'All':
            SwFunction=[]
            for ii in range(1,5):
                message = 'SP'+str(ii)
                if self.sendMsg(message) != 0:
                    return -1
                SwFunction.append(self.read())
            return SwFunction
        else:
            message = 'SP'+str(functionnumber)
            if self.sendMsg(message) != 0:
                    return -1
            return self.read()

    def setSwitchingFunction(self, functionnumber, measChannel, lowerThreshold, upperThreshold):	
        if functionnumber not in [1,2,3,4]:		
            logging.warning('Switching function not changed: Invalid or no function number')
            return 0
	if lowerThreshold < 0 or upperThreshold < 0 or lowerThreshold >= upperThreshold:	
            logging.warning('Switching function not changed: invalid threshold')
            return 0        
        if measChannel not in [0,1]: #0 = channel 1 (default), 1 = schannel 2
            measChannel = 0
            logging.warning('Measuring channel in switching function set to 0 (channel 1) by default') 
        message = 'BA'+str(functionnumber)+','+str(measChannel)+','+str(lowerThreshold)+','+str(upperThreshold)
        if self.sendMsg(message) != 0:
            return -1
        return self.read()     

    def getSwFunctionStatus(self):	
        message = 'SPS'
        if self.sendMsg(message) != 0:
            return -1
        return self.read().split(',') 

    def setWatchdogControl(self,WatchdogControl): 
        """
        Activates or deactivates the watchdog control for automatic error acknowledgement
        0 = manual error acknowledgement, 1 = automatic error acknowledgement
        """        
        if WatchdogControl not in [0,1]:	
            logging.warning('Watchdog control not changed. Set 0 for manual error acknowledgement, 1 for automatic')
            return 0
        message = 'WDT,'+str(WatchdogControl)
        if self.sendMsg(message) != 0:
            return -1
        return self.__manual_automatic[int(self.read())]

    def getWatchdogControl(self):
        """
        returns the error acknowledgement: 0 = manual  1 = automatic 
        """         
        message = 'WDT'
        if self.sendMsg(message) != 0:
            return -1
        return self.__manual_automatic[int(self.read())]
