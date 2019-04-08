from cryocon_22c import cryocon_22c


class cryocon_26(cryocon_22c):
    def SetParameters(self):
        super().SetParameters()
        self.reading_commands = {zip(['tempA','tempB','tempC','tempD'],
                                     [f'input? {ch}:units k' for ch in 'abcd'])}
