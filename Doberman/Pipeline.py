import Doberman
import time
import threading

__all__ = 'Pipeline SyncPipeline'.split()

class Pipeline(object):
    """
    A generic data-processing pipeline digraph for simple or complex
    automatable tasks
    """
    def __init__(self, **kwargs):
        self.db = kwargs['db']
        self.logger = kwargs['logger']
        self.name = kwargs['name']
        self.monitor = kwargs['monitor']
        self.cycles = 0
        self.last_error = -1
        self.subpipelines = []
        self.silenced_at_level = 0  # to support disjoint alarm pipelines
        self.required_inputs = set() # this needs to be in this class even though it's only used in Sync

    @staticmethod
    def create(config, **kwargs):
        """
        Creates a pipeline and returns it
        """
        for node in config['pipeline']:
            if node['type'] == 'SensorSourceNode':
                return SyncPipeline(**kwargs)
        return Pipeline(**kwargs)

    def stop(self):
        try:
            self.db.set_pipeline_value(self.name, [('status', 'inactive')])
            for pl in self.subpipelines:
                for node in pl:
                    try:
                        node.on_error_do_this()
                    except Exception:
                        pass
        except Exception as e:
            self.logger.debug(f'Caught a {type(e)} while stopping: {e}')

    def process_cycle(self):
        """
        This function gets Registered with the owning PipelineMonitor for Async
        pipelines, or called by run() for sync pipelines
        """
        doc = self.db.get_pipeline(self.name)
        sensor_docs = {n:self.db.get_sensor_setting(n) for n in self.depends_on}
        self.reconfigure(doc['node_config'], sensor_docs)
        status = 'silent' if self.cycles <= self.startup_cycles else doc['status']
        if status != 'silent':
            # reset
            self.silenced_at_level = 0
        timing = {}
        self.logger.debug(f'Pipeline {self.name} cycle {self.cycles}')
        drift = 0
        for pl in self.subpipelines:
            for node in pl:
                t_start = time.time()
                try:
                    node._process_base(status)
                except Exception as e:
                    self.last_error = self.cycles
                    msg = f'Pipeline {self.name} node {node.name} threw {type(e)}: {e}'
                    if isinstance(node, Doberman.SourceNode):
                        drift = 0.1 # extra few ms to help with misalignment
                    if self.cycles <= self.startup_cycles:
                        # we expect errors during startup as buffers get filled
                        self.logger.debug(msg)
                    else:
                        self.logger.warning(msg)
                    for n in pl:
                        try:
                            n.on_error_do_this()
                        except Exception:
                            pass
                    # probably shouldn't finish the cycle if something errored
                    # but we should allow other subpipelines to run
                    break
                t_end = time.time()
                timing[node.name] = (t_end-t_start)*1000
        total_timing = ', '.join(f'{k}: {v:.1f}' for k,v in timing.items())
        #self.logger.debug(f'Processing time: total {sum(timing.values()):.1f} ms, individual {total_timing}')
        self.cycles += 1
        self.db.set_pipeline_value(self.name,
                [('heartbeat', Doberman.utils.dtnow()),
                    ('cycles', self.cycles),
                    ('error', self.last_error),
                    ('rate', sum(timing.values()))])
        drift = max(drift, 0.001) # min 1ms of drift
        return max(d['readout_interval'] for d in sensor_docs.values()) + drift

    def build(self, config):
        """
        Generates the graph based on the input config, which looks like this:
        [
            {
                "name": <name>,
                "type: <node type>,
                "upstream": [upstream node names],
                **kwargs
            },
        ]
        'type' is the type of Node ('Node', 'MergeNode', etc), [node names] is a list of names of the immediate neighbor nodes,
        and kwargs is whatever that node needs for instantiation
        We generate nodes in such an order that we can just loop over them in the order of their construction
        and guarantee that everything that this node depends on has already run this loop
        """
        pipeline_config = config['pipeline']
        self.logger.debug(f'Loading graph config, {len(pipeline_config)} nodes total')
        num_buffer_nodes = 0
        longest_buffer = 0
        influx_cfg = self.db.get_experiment_config('influx')
        alarm_cfg = self.db.get_experiment_config('alarm')
        self.depends_on = config['depends_on']
        graph = {}
        while len(graph) != len(pipeline_config):
            start_len = len(graph)
            for kwargs in pipeline_config:
                if kwargs['name'] in graph:
                    continue
                upstream = kwargs.get('upstream', [])
                existing_upstream = [graph[u] for u in upstream if u in graph]
                if len(upstream) == 0 or len(upstream) == len(existing_upstream):
                    self.logger.debug(f'{kwargs["name"]} ready for creation')
                    # all this node's requirements are created
                    node_type = kwargs.pop('type')
                    node_kwargs = {
                            'pipeline': self,
                            'logger': self.logger,
                            '_upstream': existing_upstream, # we _ the key because of the update line below
                            }
                    node_kwargs.update(kwargs)
                    try:
                        n = getattr(Doberman, node_type)(**node_kwargs)
                    except Exception as e:
                        self.logger.debug(f'Caught a {type(e)} while building {kwargs["name"]}: {e}')
                        self.logger.debug(f'Args: {node_kwargs}')
                        raise
                    setup_kwargs = kwargs
                    fields = 'device topic subsystem description units alarm_level'.split()
                    if isinstance(n, (Doberman.SourceNode, Doberman.AlarmNode)):
                        if (doc := self.db.get_sensor_setting(name=kwargs['input_var'])) is None:
                            raise ValueError(f'Invalid input_var for {n.name}: {kwargs["input_var"]}')
                        for field in fields:
                            setup_kwargs[field] = doc.get(field)
                    elif isinstance(n, (Doberman.InfluxSinkNode)):
                        if (doc := self.db.get_sensor_setting(name=kwargs.get('output_var', kwargs['input_var']))) is None:
                            raise ValueError(f'Invalid output_var for {n.name}: {kwargs.get("output_var")}')
                        for field in fields:
                            setup_kwargs[field] = doc.get(field)
                    setup_kwargs['influx_cfg'] = influx_cfg
                    setup_kwargs['write_to_influx'] = self.db.write_to_influx
                    setup_kwargs['send_to_pipelines'] = self.db.send_value_to_pipelines
                    setup_kwargs['log_alarm'] = getattr(self.monitor, 'log_alarm', None)
                    setup_kwargs['log_command'] = self.db.log_command
                    for k in 'escalation_config silence_duration'.split():
                        setup_kwargs[k] = alarm_cfg[k]
                    setup_kwargs['get_pipeline_stats'] = self.db.get_pipeline_stats
                    setup_kwargs['cv'] = getattr(self, 'cv', None)
                    try:
                        n.setup(**setup_kwargs)
                    except Exception as e:
                        self.logger.debug(f'Caught a {type(e)} while setting up {n.name}: {e}')
                        self.logger.debug(f'Args: {setup_kwargs}')
                        raise
                    graph[n.name] = n

            if (nodes_built := (len(graph) - start_len)) == 0:
                # we didn't make any nodes this loop, we're probably stuck
                created = list(graph.keys())
                all_nodes = set(d['name'] for d in pipeline_config)
                self.logger.debug(f'Created {created}')
                self.logger.debug(f'Didn\'t create {list(all_nodes - set(created))}')
                raise ValueError('Can\'t construct graph! Check config and logs')
            self.logger.debug(f'Created {nodes_built} nodes this iter, {len(graph)}/{len(pipeline_config)} total')
        for kwargs in pipeline_config:
            for u in kwargs.get('upstream', []):
                graph[u].downstream_nodes.append(graph[kwargs['name']])

        self.calculate_jointedness(graph)

        # we do the reconfigure step here so we can estimate startup cycles
        self.reconfigure(config['node_config'], {n: self.db.get_sensor_setting(n) for n in self.depends_on})
        for pl in self.subpipelines:
            for node in pl:
                if isinstance(node, Doberman.BufferNode) and not isinstance(node, Doberman.MergeNode):
                    num_buffer_nodes += 1
                    longest_buffer = max(longest_buffer, n.buffer.length)

        self.startup_cycles = num_buffer_nodes + longest_buffer # I think?
        self.logger.debug(f'I estimate we will need {self.startup_cycles} cycles to start')

    def calculate_jointedness(self, graph):
        """
        Takes in the graph as created above and figures out how many
        disjoint sections it has. These sections get separated out into subpipelines
        """
        while len(graph):
            self.logger.debug(f'{len(graph)} nodes to check')
            nodes_to_check = set([list(graph.keys())[0]])
            nodes_checked = set()
            nodes = []
            pl = {}
            # first, find connected sets of nodes
            while len(nodes_to_check) > 0:
                name = nodes_to_check.pop()
                for u in graph[name].upstream_nodes:
                    if u.name not in nodes_checked:
                        nodes_to_check.add(u.name)
                for d in graph[name].downstream_nodes:
                    if d.name not in nodes_checked:
                        nodes_to_check.add(d.name)
                nodes.append(graph.pop(name))
                nodes_checked.add(name)

            # now, reorder them
            while len(nodes) > 0:
                for i, node in enumerate(nodes):
                    if len(node.upstream_nodes) == 0 or all(u.name in pl for u in node.upstream_nodes):
                        pl[node.name] = nodes.pop(i)
                        break # break because i is no longer valid

            self.logger.debug(f'Found subpipeline: {set(pl.keys())}')
            self.subpipelines.append(list(pl.values()))

    def reconfigure(self, doc, sensor_docs):
        """
        "doc" is the node_config subdoc from the general config, sensor_docs is
        a dict of sensor documents this pipeline uses
        """
        for pl in self.subpipelines:
            for node in pl:
                this_node_config = dict(doc.get('general', {}).items())
                this_node_config.update(doc.get(node.name, {}))
                if isinstance(node, Doberman.AlarmNode):
                    rd = sensor_docs[node.input_var]
                    this_node_config.update(
                            alarm_thresholds=rd['alarm_thresholds'],
                            readout_interval=rd['readout_interval'],
                            alarm_recurrence=rd['alarm_recurrence'])
                    if isinstance(node, Doberman.SimpleAlarmNode):
                        this_node_config.update(length=rd['alarm_recurrence'])
                node.load_config(this_node_config)

    def silence_for(self, duration, level=0):
        """
        Silence this pipeline for a set amount of time
        """
        self.db.set_pipeline_value(self.name, [('status', 'silent'), ('silent_until', time.time()+duration)])
        self.db.log_command(f'pipelinectl_active {self.name}', to=self.monitor.name,
                issuer=self.name, delay=duration)
        self.silenced_at_level = level

class SyncPipeline(threading.Thread, Pipeline):
    """
    A subclass to handle synchronous operation where input comes directly from
    the sensors rather than via the database
    """
    def __init__(self, **kwargs):
        threading.Thread.__init__(self)
        Pipeline.__init__(self, **kwargs)
        self.cv = threading.Condition()
        self.event = threading.Event()
        self.has_new = set()

    def run(self):
        predicate = lambda: (len(self.has_new) > 0 and self.has_new >= self.required_inputs) or self.event.is_set()
        while not self.event.is_set():
            with self.cv:
                self.cv.wait_for(predicate)
            self.process_cycle()
            self.has_new.clear()

    def stop(self):
        self.event.set()
        with self.cv:
            self.cv.notify()
        return super().stop()

