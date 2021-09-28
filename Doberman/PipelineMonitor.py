import Doberman

__all__ = 'PipelineMonitor'.split()

class PipelineMonitor(Doberman.Monitor):
    """
    A subclass to handle a pipeline. Only one pipeline per pipeline monitor to make it easier to restart
    during development.
    """

    def setup(self):
        name = self.name.split('_', maxsplit=1)[1]
        if (doc := self.db.get_pipeline(name)) is None:
            self.logger.error(f'No pipeline named {name} found!')
            return -1
        p = Doberman.Pipeline(db=self.db, logger=self.logger, name=name)
        try:
            p.build(doc)
        except Exception as e:
            self.logger.error(f'Error building pipeline {name}: {e}')
            return -1
        self.register(obj=p.process_cycle, period=doc['period'], name=name)
        self.pipeline = p

    def handle_commands(self):
        while (doc := self.db.find_command(self.name)) is not None:
            self.logger.debug(f'Found command: {doc["command"]}')
            try:
                command = doc['command']
                if command == 'stop':
                    self.sh.event.set()
                    return
            except Exception as e:
                self.logger.error(f'Received malformed command: {doc["command"]}')

