#! /usr/bin/env python3.3
import logging
import time


class smartec_uti3Command(object):

    """
    Class that holds the uti transducer commands
    """
    def __init__(self):
        pass


    """
    Commands:
    """
    def greet(self):
        """
        Establishes connection by sending '@'
        """
        message = '@'
        self.communicate(message)
        return

    def setSlow(self):
        """
        Switches to slow mode
        """
        message = 's'
        self.communicate(message)
        return

    def setFast(self):
        """
        Switches to fast mode
        """
        message = 'f'	
        self.communicate(message)
        return

    def setMode(self, mode):
        """
        Sets measurement mode between mode 0 and mode 4
        """
        self.communicate(mode)
        return

    def powerDown(self):
        """
        Powers down the uti transducer
        """
        message = 'p'
        self.communicate(message)
        return

    def measure(self, mode):
        """
        Starts a measurement cycle and calculates final value
        """
        message = 'm'
        self.sendMessage(message)
        return 
