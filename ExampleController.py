from BaseController import SerialController  # or LANController, if applicable
import re  # if you want to accept commands


class ExampleController(SerialController):
    """
    An example of how to make your own controller
    """
    accepted_commands = [
            "a pattern: a description of what this command does",
        ] # this object is used if you ask for help from the command line
    def __init__(self, opts):
        self._msg_start = ''  # whatever character(s) messages start with
        self._msg_end = '\r\n'  # same, for end
        self.commands = {'read' : 'command',
                         'also_read' : 'also_command',
                         'check_id' : 'check_id',
                         'set', 'set_value',
                         }
        super().__init__(opts)  # calls SerialController.__init__, which calls Controller.__init__
        # if you need any quantities from the config doc in the command dictionary, call init first

        self.command_patterns = [
                (re.compile('a pattern'), lambda x : self.commands['set'].format(**x.groupdict())),
                ]
        # this is a list of (regular expression, function) objects. The regular expression
        # matches the commmand issued via the command line, and the function takes as
        # argument a re.match object and returns the string to the sent to the controller

    def isThisMe(self, dev):
        """
        This function checks to see if the device 'dev' is, in fact, this controller.
        This is only necessary if you inherit from SerialController.
        """
        resp = self.SendRecv(self.commands['check_id'], dev)
        if resp['retcode'] or not ret['data']:
            return False
        if resp['data'] == self.some_uniquely_identifying_quantity:
            True

    def Readout(self):
        """
        Queries the controller for whatever readings you want. If you only read one value you
        don't need to make the values into arrays, that will be done upstream
        """
        vals = []
        status = []
        for coms in ['read','also_read']:
            resp = self.SendRecv(self.commands[com])
            if resp['retcode'] or not resp['data']:
                status.append(resp['retcode'])
                vals.append(-1)
            else:
                status.append(0)
                vals.append(float(resp['data']))
        return {'retcode' : status, 'data' : vals}

