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
            if self.start_pipeline(self.name):
                self.event.set()

    def shutdown(self):
        self.logger.debug(f'{self.name} shutting down')
        for p in list(self.pipelines.keys()):
            self.stop_pipeline(p)

    def start_pipeline(self, name):
        if (doc := self.db.get_pipeline(name)) is None:
            self.logger.error(f'No pipeline named {name} found')
            return -1
        p = Doberman.Pipeline(db=self.db, logger=self.logger, name=name)
        try:
            p.build(doc)
        except Exception as e:
            self.logger.error(f'{type(e)}: {e}')
            self.logger.error(f'Could not build pipeline {name}, check debug logs')
            return -1
        self.register(obj=p.process_cycle, name=name, period=1)
        self.pipelines[p.name] = p
        self.db.set_pipeline_value(name, [('status', 'active')])
        return 0

    def stop_pipeline(self, name):
        self.pipelines[name].stop()
        self.stop_thread(name)
        del self.pipelines[name]

    def process_command(self, command):
        self.logger.debug(f'Found command: {doc["command"]}')
        try:
            if command == 'pipelinectl_start':
                _, name = command.split(' ')
                self.start_pipeline(name)
            elif command == 'pipelinectl_stop':
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.stop_pipeline(name)
            elif command == 'pipelinectl_restart':
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.stop_pipeline(name)
                    self.start_pipeline(name)
            elif command == 'pipelinectl_silent':
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.db.set_pipeline_value(name, [('status', 'silent')])
            elif command == 'pipelinectl_active':
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.db.set_pipeline_value(name, [('status', 'active')])
            elif command == 'stop':
                self.sh.event.set()
                return
        except Exception as e:
            self.logger.error(f'Received malformed command: {doc["command"]}')
