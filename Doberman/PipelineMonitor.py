import Doberman


class PipelineMonitor(Doberman.Monitor):
    """
    A subclass to handle pipelines. THERE SHOULD ONLY BE ONE
    """

    def setup(self):
        self.pipelines = {}

    def shutdown(self):
        pass

    def start_pipeline(self, name):
        doc = self.db.get_pipeline(name)
        if doc is None:
            self.logger.error(f'No pipeline named {name} found!')
            return -1
        p = Doberman.Pipeline(db=self.db, logger=self.logger, name=name)
        try:
            p.build(doc)
        except Exception as e:
            self.logger.error(f'Error building pipeline {name}: {e}')
            return -1
        self.pipelines[name] = p
        self.register(obj=p.process_cycle, period=doc['period'], name=name)

    def stop_pipeline(self, name):
        self.stop_thread(name)
        del self.pipelines[name]

    def handle_commands(self):
        while (doc := self.db.find_command(self.name)) is not None:
            self.logger.debug(f'Found command "{doc[\'command\']"')
            try:
                if ' ' in doc['command']:
                    command, target = doc['command'].split()
                    if command == 'pipelinectl_start':
                        self.start_pipeline(target)
                    elif command == 'pipelinectl_stop':
                        self.stop_pipeline(target)
                    elif command == 'pipelinectl_restart':
                        self.stop_pipeline(target)
                        self.start_pipeline(target)
                    else:
                        self.logger.error(f'Bad command: {doc["command"]}')
                else:
                    command = doc['command']
                    if command == 'stop':
                        self.sh.event.set()
                        return
            except Exception as e:
                self.logger.error(f'Received malformed command: {doc["command"]}')
                continue

