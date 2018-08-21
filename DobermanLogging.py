import logging
import logging.handlers
import datetime
import os


class DobermanLogger(logging.Handler):
    """
    Custom logging interface for Doberman. Gives us the option to log to
    the database (with disk as backup).
    """
    def __init__(self, db):
        logging.Handler.__init__(self)
        self.db = db
        self.db_name = 'logging'
        self.collection_name = 'logs'
        backup_filename = datetime.date.today().isoformat()
        self.backup_logger = logging.handlers.TimedRotatingFileHandler(
                os.path.join(os.getcwd(), 'logs', backup_filename + '.log'),
                when='midnight', delay=True)
        self.stream = logging.StreamHandler()
        f = logging.Formatter('%(asctime)s | '
                '%(levelname)s | %(name)s | %(funcName)s | '
                '%(lineno)d | %(message)s')
        self.setFormatter(f)
        self.stream.setFormatter(f)

    def __del__(self):
        #self.db.close()  # doesn't own db instance
        return

    def emit(self, record):
        if record.levelno <= logging.INFO:
            self.stream.emit(record)
            return
        rec = dict(when     = datetime.datetime.fromtimestamp(record.created),
                msg         = record.msg,
                level       = record.levelno,
                name        = record.name,
                funcname    = record.funcName,
                lineno      = record.lineno)
        if self.db.insertIntoDatabase(self.db_name, self.collection_name, rec):
            self.backup_logger.emit(record)

