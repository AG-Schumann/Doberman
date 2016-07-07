#! /usr/bin/env python3.3

import MKS_MFCMaster


class MKS_MFCControl(object):
    """
    Connection function between MKS_MFC and slowControl
    Can not run on its own, use
    python TeledyneMaster.py -otps
    as a stand alone program instead
    """

    def __init__(self, opts):
        self.MKS_MFC_master = MKS_MFCMaster.MKS_MFCMaster(opts)

    def MKS_MFCcontrol(self):
        self.MKS_MFC_master.MKS_MFCmaster()

    def __exit__(self):
        self.MKS_MFC_master.__exit__()
