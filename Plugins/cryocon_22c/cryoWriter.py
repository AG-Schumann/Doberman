#! /usr/bin/env python3.3

import datetime
import os 

class cryoWriter(object):
    """
    Class that holds the cryo controller logging and debugging. Creates a new file with the name: %Y-%m-%d_%H-%M-%S_%Keyword.log in the folder that was set. If the file already exists it tries to write the informations in the existing file.
    """
    def __init__(self, logger, keyword = None, **kwds):
        self.logger = logger

        self._logpath = 'log'
        self.__keyword = keyword
        if self.__keyword is None:
            self.__keyword = 'STD'

        if kwds.has_key('log_path'):
             self._logpath = str(kwds['log_path'])

        if not os.path.isdir(self._logpath):
            rights = 0o751
            #PYTHON 2 compatibility:
            #rights = 0751
            os.mkdir(self._logpath,rights)
        
        self.now = datetime.datetime.now()
        self.filename = os.path.join(self._logpath,"%s_%s_cryocon_22c.log" %(self.now.strftime('%Y-%m-%d_%H-%M-%S'),self.__keyword))
        
        ifn = 0
        while ifn < 10:
            ifn += 1
            if os.path.isfile(self.filename):
                newname = os.path.join(self._logpath,"%s_%s_%i.log" %(self.now.strftime('%Y-%m-%d_%H-%M-%S'),self.__keyword,ifn))
                self.logger.warning("File: %s exists already. Trying to write to %s..."%(self.filename, newname))
                self.filename = newname
            else:
                break
        self.__file = open(self.filename, 'w')

        self.__queue = []

        self.write(("# Cryo Controller logging file - generated %s. Logging mode is %s"%(self.now.strftime('%Y-%m-%d %H:%M:%S'),self.__keyword)))

    def write(self,message = None):
        """
        Writes a message to the file
        """
        towrite = []
        if len(self.__queue) != 0:
            towrite = self.__queue
        if not message is None:
            if not isinstance(message, str):
                self.logger.warning("Invalid format for the logging file.")
                return -1
            else:
                towrite = towrite + [message]
        for elem in towrite:
            self.__file.write(elem.rstrip()+'\n')
        self.__file.flush()
        return 0

    def close(self):
        """
        call this to properly close the file of the writer
        """
        if not self.__file.closed:
            self.__file.flush()
            self.__file.close()
        return

    def __del__(self):
        self.close()
        return
    
    def __exit__(self):
        self.close()
        return

if __name__ == '__main__':
    import logging
    import os
    logging.basicConfig()
    logger = logging.getLogger()
    logger.setLevel(10)
    crw = cryoWriter(logger)
    crw.write("test %s"%("test2"))
    crw.close()
