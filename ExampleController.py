from BaseController import SerialController  # or LANController, if applicable
import re  # if you want to accept commands
from utils import number_regex  # a regex that matches numbers (ints and floats)


class ExampleController(SerialController):
    """
    An example of how to make your own controller
    """
    # this object is used if you ask for help from the command line
    accepted_commands = [
            "a pattern: a description of what this command does",
        ]
    def SetParameters(self):
        # Values from the database configuration document are loaded before this
        # function is called. The hardware connection has not been opened yet.
        self._msg_start = ''  # whatever character(s) messages start with
        self._msg_end = '\r\n'  # same, for end
        self.commands = {'read' : 'command',
                         'also_read' : 'also_command',
                         'check_id' : 'check_id',
                         'set', 'set_value',
                         'prepare', 'some_command'
                         }

        # this object is a list of the commands for the various readings this
        # sensor provides.
        self.reading_commands = [self.commands['read'], self.commands['also_read']]

        # helpful regexes for output handling
        self.read_pattern = re.compile(bytes('OK;(?P<value>%s)' % number_regex, 'utf-8'))
        self.error_pattern = re.compile(b'ERR;')

        # this is a list of (regular expression, function) objects. The regular expression
        # matches the commmand issued via the command line, and the function takes as
        # argument a re.match object and returns the string to be sent to the controller
        self.command_patterns = [
                (re.compile('a pattern'), lambda x : self.commands['set'].format(**x.groupdict())),
                ]

    def Setup(self):
        # This function is called after the connection to the hardware is opened
        self.SendRecv(self.commands['prepare'])

    def isThisMe(self, dev):
        # This function checks to see if the device 'dev' is, in fact, this controller.
        # This is only necessary if you inherit from SerialController.
        resp = self.SendRecv(self.commands['check_id'], dev)
        if resp['retcode'] or not ret['data']:
            return False
        if resp['data'] == self.some_uniquely_identifying_quantity:
            True

    def ProcessOneReading(self, index, data):
        # Processes data returned from the sensor. `data` is of type bytes
        if self.error_pattern.search(data):
            return -1
        m = self.read_pattern.search(data)
        if not m:
            return -2
        return float(m.group('value'))

