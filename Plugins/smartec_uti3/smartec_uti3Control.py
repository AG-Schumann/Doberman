#! /usr/bin/env python3.3

import smartec_uti3Master

class smartec_uti3Control(object):
    """
    Connection function between utiMaster and slowControl
    Can not run on its own, use python utiMaster.py -otps as a stand alone program instead
    """
    def __init__(self, opts):
        logger = opts.logger
        self.smartec_uti_master = smartec_uti3Master.smartec_uti3Master(opts, logger)

    def smartec_uti3control(self):
        self.smartec_uti_master.utimaster()

    def __exit__(self):
        self.smartec_uti_master.__exit__()
