import datetime
import os 
import Queue


class supervisionWriter(object):
    """
    Class that holds the supervision plugin logging and debugging. 
    If a queue is existing, it pushes the data there.
    Creates a new file with the name: %Y-%m-%d_%H-%M-%S_%Keyword.log in the folder that was set. If the file already exists it tries to write the informations in the existing file.
    """
    def __init__(self, logger, queue=None, keyword = None, **kwds):
        self.logger = logger
        self.queue = None
        if not queue is None:
            self.queue = queue

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
        self.filename = os.path.join(self._logpath,"%s_%s_supervision.log" %(self.now.strftime('%Y-%m-%d_%H-%M-%S'),self.__keyword))
        
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

        self.writeToFile(("# supervision plugin logging file - generated %s. Logging mode is %s"%(self.now.strftime('%Y-%m-%d %H:%M:%S'),self.__keyword)))


    def write(self, message, logtime=None):
        '''
        Writes the message down, eighter to the queue or alternatively to the logfile
        '''
        if not logtime is None:
            readout = str("| %s %s"%(str(logtime.strftime('%Y-%m-%d | %H:%M:%S')),str(message)))
        else:
            readout = str("|  | %s |"%(str(message)))
        if self.queue is None:
            self.logger.info("Logged string: %s"%readout)
            self.writeToFile(readout)
        else:
            self.pushToQueue(message, logtime)

    def pushToQueue(self, message, logtime):
        '''
        pushes data to queue.
        reformats it to form [name,logtime,data,status]
        '''
        data = message
        if str(data) == '-1':
            data = [-1]
            status = [-1]
        elif str(data) == '1':
            data = [1]
            status = [1]
        else:
            status = [-3]
            try:
                data=[float(data)]
            except Exception as e:
                self.logger.warning("Wrong format, %s"%e)
                data = [0]
                status = [-4]          
        self.queue.put(['supervision',logtime,data,status])
        self.logger.debug("Put dat to queue: ['supervision', %s, %s, %s]"%(str(logtime),str(data),str(status)))

    def writeToFile(self,message = None):
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
    crw = supervisionWriter(logger)
    crw.write("tested supervision %s"%("test2"))
    crw.close()
