#! /usr/bin/env python3.3
import logging
import time


class MKS_MFCCommand(object):

    """
    Class that holds the MKS_MFC commands
    """

    def __init__(self):
        pass

    def communicate(self, message):
        """
        Note that this is a test function.
        MKS_MFCSerial has its own communicate fuction
        """
        print('I send %s and read the output' % str(message))
        return 0

    """
    Commands:
    """

    def getAddress(self):
        """
        Gets the controller address. Between 000 and 254.
        """
        message = 'CA?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getUnits(self):
        """
        Reads the units used ccm (standard cubic centimeters per minute)
        or slm (standard liters per minute).
        """
        message = 'U?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getFlowRate(self):
        """
        Gets the current flow rat in the units used (sccm or slm).
        """
        message = 'FX?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getFlowRatePercent(self):
        """
        Gets the current flow rat in percent of full scale.
        """
        message = 'F?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getStatus(self):
        """
        Reads the current status.
        C = Valve closed
        CR = Calibration recommended
        E = System error
        H = High alarm condition
        HH = High-high alarm condition
        IP = Insufficient gas inlet pressure
        L = Low alarm condition
        LL = Low-low alarm condition
        M = Memory (EEPROM) failure
        O = OK, no errors to report
        OC = Unexpected change in operating
        conditions
        P = Purge
        T = Over temperature
        U = Uncalibrated
        V = Valve drive level alarm condition
        """
        message = 'T?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response.split(",")

    def getInternalTemperature(self):
        """
        Measures the interneal temperature in degrees Celsius.
        Calibration was done at 273.0 K (Kelvin!)
        """
        message = 'TA?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getDeviceType(self):
        """
        Returns device type. MFC or MFM.
        """
        message = 'DT?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def getSetpointValue(self):
        """
        Reads the current setpoint value in current units.
        """
        message = 'SX?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def changeSetpointValue(self, setpoint):
        """
        Changes the setpoint to the given value in current units
        """
        message = 'SX!%f' % float(setpoint)
        response = self.communicate(message)
        if response == -1:
            return -1
        return setpoint

    def getSetpointPercent(self):
        """
        Reads the current setpoint in percent of the full range.
        """
        message = 'S?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def changeSetpointPercent(self, setpoint):
        """
        Changes the setpoint to the given value in percent of the full range
        """
        message = 'S!%f' % float(setpoint)
        response = self.communicate(message)
        if response == -1:
            return -1
        return setpoint

    def getSoftstartRate(self):
        """
        Reads the current softstart rate (# of steps to open valve)
        Range:
        1: Open velve as fast as possible (1 step)
        200: Open valve in 200 equal steps (about 6.4 seconds)
        """
        message = 'SS?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response

    def changeSoftstartRate(self, rate):
        """
        Changes the current softstart rate (# of steps to open valve)
        Range:
        1: Open velve as fast as possible (1 step)
        200: Open valve in 200 equal steps (about 6.4 seconds)
        """
        if rate not in range(1, 200):
            self.logger.warning("Invalid softstart rate, must be in (1, 200).")
            return -1
        message = 'SS!%f' % rate
        response = self.communicate(message)
        if response == -1:
            return -1
        return rate

    def getValveLevel(self):
        """
        Returns control signal that causes the valve in the MFC to move.
        0-100 [%]
        The valve may be closed at levels greater than zero and may be
        fully open at levels less than 100%.
        """
        message = 'VD?'
        response = self.communicate(message)
        if response == -1:
            return -1
        return response
