import Doberman

__all__ = 'PipelineMonitor'.split()

class PipelineMonitor(Doberman.Monitor):
    """
    A subclass to handle a pipeline or pipelines. All 'alarm' pipelines are handled by one PipelineMonitor,
    while each 'control' pipeline will be handled by its own monitor to simplify the frequent restarting
    that is likely to occur.
    """

    def setup(self):
        self.pipelines = {}
        if self.name == 'pl_alarm':
            for name in self.db.get_alarm_pipelines():
                self.start_pipeline(name)
        else:
            self.start_pipeline(self.name)

    def start_pipeline(self, name):
        if (doc := self.db.get_pipeline(name)) is None:
            self.logger.error(f'No pipeline named {name} found')
            return -1
        p = Doberman.Pipeline(db=self.db, logger=self.logger, name=name)
        try:
            p.build(doc)
        except Exception as e:
            self.logger.error(f'Could not build pipeline {name}, check debug logs')
            return -1
        self.register(obj=p.process_cycle, name=name, period=doc['period'])
        self.pipelines[p.name] = p

    def stop_pipeline(self, name):
        self.stop_thread(name)
        del self.pipelines[name]

    def handle_commands(self):
        while (doc := self.db.find_command(self.name)) is not None:
            self.logger.debug(f'Found command: {doc["command"]}')
            try:
                command = doc['command']
                if command == 'pipelinectl_start':
                    _, name = command.split(' ')
                    self.start_pipeline(name)
                elif command == 'pipelinectl_stop':
                    _, name = command.split(' ')
                    self.stop_pipeline(name)
                elif command == 'pipelinectl_restart':
                    _, name = command.split(' ')
                    self.stop_pipeline(name)
                    self.start_pipeline(name)
                elif command == 'pipelinectl_silent':
                    _, name = command.split(' ')
                    self.db.set_pipeline_value(name, [('status', 'silent')])
                elif command == 'pipelinectl_active':
                    _, name = command.split(' ')
                    self.db.set_pipeline_value(name, [('status', 'active')])
                elif command == 'stop':
                    self.sh.event.set()
                    return
            except Exception as e:
                self.logger.error(f'Received malformed command: {doc["command"]}')