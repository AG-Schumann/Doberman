from cryocon_22c import cryocon_22c


class cryocon_26(cryocon_22c):
    def __init__(self, opts):
        super().__init__(opts)
        self.reading_commands = [f'input? {ch}:units k' for ch in 'abcd']
