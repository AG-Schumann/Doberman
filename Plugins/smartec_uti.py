from Doberman.Controller import SerialController


class smartec_uti(SerialController):
    """
    Level meter controllers
    """

    def __init__(self, opts):
        additional_params = opts.additional_parameters.split(',')
        self.c_ref = int(additional_params[0])
        self.mode = int(additional_parameters[1])
        self.commands = {
                'greet' : '@',
                'setSlow' : 's',
                'setFast' : 'f',
                'setMode0' : '0',
                'setMode1' : '1',
                'setMode2' : '2',
                'setMode4' : '4',
                'measure' : 'm',
                'powerDown' : 'p', # if you use this, you need to plug-cycle the board
                }
        super().__init__(opts)

    def checkController(self):
        val = self.SendRecv(self.commands['greet'])
        val = self.SendRecv(self.commands['setSlow'])
        val = self.SendRecv(self.commands['setMode%i' % self.mode])
        if val['retcode']:
            self.logger.error('UTI not answering correctly')
            self.__connected = False
            return -1
        else:
            self.logger.info('Connected to %s correctly' % self.name)
            try:
                with open(self.ttypath, 'a+') as f:
                    f.write(" %i | %s" % (self.ttyUSB, self.name))
            except Exception as e:
                self.logger.warning('Could not add ttyusb to file! Error %s' % e)
            else:
                self.occupied_ttyUSB.append(self.ttyUSB)
            finally:
                return 0
        return -3

    def Readout(self):
        val = self.SendRecv(self.commands['measure'])
        if val['retcode']:
            return val
        try:
            values = val['data'].rstrip().split()
            values = list(map(lambda x : int(x,16), values))

            resp = []

            c_off = values[0]
            div = values[1] - values[0]
            self.logger.debug('UTI measured %s' % values)
            if div: # evals to (value[cde] - valuea)/(valueb - valuea)
                resp = [(v-c_off)/div*self.c_ref for v in values[2:]]
            else:
                resp = [-1]*len(values[2:])
            self.logger.debug('UTI evaluates to %s' % resp)

            val['data'] = resp
        except Exception as e:
            self.logger.error('LM error: %s' % e)
            val['retcode'] = -3
        return val
