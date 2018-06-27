from Doberman.Controller import SerialController  # or LANController, if applicable
import logging  # you need this


class ExampleController(SerialController):
    """
    An example of how to make your own controller
    """

    def __init__(self, opts):
        self.logger = logging.getLogger(__name__) # instantiated here so log messages include controller name
        self.__msg_start = ''  # whatever character(s) messages start with
        self.__msg_end = '\r\n'  # same, for end
        self.some_special_parameter = opts.additional_params['special_parameter']
        self.commands = {'read' : 'command',
                         'also_read' : 'also_command',
                         'check_id' : 'check_id',
                         }
        super().__init__(opts)  # calls SerialController.__init__, which calls Controller.__init__
        # quantities like the vendorID, ip address, etc are all pulled from opts further up.
        # You only need to pull device-specific quantities here

    def checkController(self):
        """
        This function makes sure you connected to the correct controller
        """
        resp = self.SendRecv(self.commands['check_id'])
        if resp['retval']:
            self.logger.error('An error')
            return -1
        if resp['data'] == self.some_uniquely_identifying_quantity:
            self.add_ttyUSB(self.ttyUSB)  # only for serial controllers
            return 0
        else:
            # connected to wrong controller
            self.logger.error('Connected to wrong controller')
            return -2
        return -3

    def Readout(self):
        """
        Queries the controller for whatever readings you want. If you only read one value you
        don't need to make the values into arrays, that will be done upstream
        """
        vals = []
        status = []
        for coms in ['read','also_read']:
            resp = self.SendRecv(self.commands[com])
            if resp['retval']:
                status.append(-1)
                vals.append(-1)
            else:
                status.append(0)
                vals.append(resp['data'])
        return {'retval' : status, 'data' : vals}
        resp = self.SendRecv(self.commands['also_read']


