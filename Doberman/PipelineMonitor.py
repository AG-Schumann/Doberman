import Doberman
import collections

__all__ = 'PipelineMonitor'.split()


class PipelineMonitor(Doberman.Monitor):
    """
    A subclass to handle a pipeline or pipelines. Pipelines come in three main flavors: they either process or send alarms,
    convert "raw" values into "processed" values, or control something in the system. Each flavor is handled by one
    dedicated PipelineMonitor.
    """

    def setup(self):
        self.listeners = collections.defaultdict(dict)
        self.pipelines = {}
        flavor = self.name.split('_')[1]  # pl_flavor
        if flavor not in 'alarm control convert'.split():
            raise ValueError(f'Unknown pipeline monitor {self.name}, allowed are "pl_alarm", "pl_convert", "pl_control"')
        for name in self.db.get_pipelines(flavor):
            self.start_pipeline(name)
        if self.name == 'pl_control':
            # hard-code the test routine. It runs through one cycle then stops itself
            self.start_pipeline('test_pipeline')

    def shutdown(self):
        self.logger.debug(f'{self.name} shutting down')
        for p in list(self.pipelines.keys()):
            self.stop_pipeline(p)

    def start_pipeline(self, name):
        if (doc := self.db.get_pipeline(name)) is None:
            self.logger.error(f'No pipeline named {name} found')
            return -1
        try:
            p = Doberman.Pipeline.create(doc, db=self.db,
                    logger=Doberman.utils.get_child_logger(name, self.logger),
                    name=name, monitor=self)
            p.build(doc)
        except Exception as e:
            self.logger.error(f'{type(e)}: {e}')
            self.logger.error(f'Could not build pipeline {name}, check debug logs')
            return -1
        self.register(obj=p, name=name)
        self.pipelines[p.name] = p
        self.db.set_pipeline_value(name, [('status', 'active')])
        return 0

    def stop_pipeline(self, name):
        self.logger.debug(f'Stopping {name}')
        self.pipelines[name].stop()
        self.stop_thread(name)
        del self.pipelines[name]

    def register_listener(self, node):
        """
        Register a node to listen for named sensor inputs
        """
        self.logger.debug(f'{node.name} listens for {node.input_var}')
        self.listeners[node.input_var][node.hash] = node

    def unregister_listener(self, node):
        """
        Remove a node from the listeners list
        """
        self.listeners[node.input_var].pop(node.hash, None)

    def process_command(self, command):
        try:
            if command.startswith('sensor_value'):
                _, name, ts, value = command.split()
                ts = float(ts)
                if value == 'None':
                    value = None
                elif '.' in value:
                    value = float(value)
                else:
                    value = int(value)
                for listener in self.listeners[name].values():
                    listener.receive_from_upstream({'time': ts, name: value})
            elif command.startswith('pipelinectl_start'):
                _, name = command.split(' ')
                self.start_pipeline(name)
            elif command.startswith('pipelinectl_stop'):
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.stop_pipeline(name)
            elif command.startswith('pipelinectl_restart'):
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.stop_pipeline(name)
                    self.start_pipeline(name)
            elif command.startswith('pipelinectl_silent'):
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.logger.debug(f'Silencing {name}')
                    self.db.set_pipeline_value(name, [('status', 'silent')])
            elif command.startswith('pipelinectl_active'):
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.logger.debug(f'Activating {name}')
                    self.db.set_pipeline_value(name, [('status', 'active')])
                    self.db.update_db('pipelines', {'name': name}, {'$unset': {'silent_until': 1}})
            elif command == 'stop':
                self.sh.event.set()
            else:
                self.logger.info(f'I don\'t understand command "{command}"')
        except Exception as e:
            self.logger.error(f'Received malformed command: {command}')
            self.logger.debug(f'{type(e)}: {e}')

