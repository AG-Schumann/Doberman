import logging
from DobermanLogging import DobermanLogger

logger = logging.getLogger('testing')
logger.addHandler(DobermanLogger(False))
logger.setLevel(10)
try:
    logger.debug('Debug')
    logger.info('Info')
    logger.warning('Warning')
    logger.error('Error')
    logger.critical('Fatal')
except Exception as e:
    print(e)

