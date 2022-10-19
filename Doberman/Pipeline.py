import Doberman
import time
import threading
import json
import zmq
import collections

__all__ = 'Pipeline SyncPipeline'.split()


class Pipeline(threading.Thread):
    """
    A generic data-processing pipeline digraph for simple or complex
    automatable tasks
    """

    def __init__(self, **kwargs):
        threading.Thread.__init__(self)
        self.db = kwargs['db']
        self.logger = kwargs['logger']
        self.name = kwargs['name']
        self.monitor = kwargs['monitor']
        self.cycles = 0
        self.last_error = -1
        self.event = threading.Event()
        self.subpipelines = []
        self.silenced_at_level = 0  # to support disjoint alarm pipelines
        self.required_inputs = set()  # this needs to be in this class even though it's only used in Sync
        self.ctx = kwargs.get('context') or zmq.Context.instance()
        self.command_socket = self.ctx.socket(zmq.REQ)
        host, ports = self.db.get_comms_info('command')
        self.command_socket.connect(f'tcp://{host}:{ports["send"]}')
        host, ports = self.db.get_comms_info('data')
        self.data_socket = self.ctx.socket(zmq.PUB)
        self.data_socket.connect(f'tcp://{host}:{ports["send"]}')
        self.depends_on = []

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
        self.event.set()
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

    def run(self):
        while not self.event.is_set():
            interval = self.process_cycle()
            self.event.wait(interval)

    def process_cycle(self):
        """
        This function gets Registered with the owning PipelineMonitor for Async
        pipelines, or called by run() for sync pipelines
        """
        doc = self.db.get_pipeline(self.name)
        sensor_docs = {n: self.db.get_sensor_setting(n) for n in self.depends_on}
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
                        drift = 0.1  # extra few ms to help with misalignment
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
                timing[node.name] = (t_end - t_start) * 1000
        self.cycles += 1
        self.db.set_pipeline_value(self.name,
                                   [('heartbeat', Doberman.utils.dtnow()),
                                    ('cycles', self.cycles),
                                    ('error', self.last_error),
                                    ('rate', sum(timing.values()))])
        drift = max(drift, 0.001)  # min 1ms of drift
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
                        '_upstream': existing_upstream,  # we _ the key because of the update line below
                    }
                    node_kwargs.update(kwargs)
                    try:
                        n = getattr(Doberman, node_type)(**node_kwargs)
                    except AttributeError as e:
                        raise ValueError(f'Node type "{node_type}" not implemented for node {kwargs["name"]}. Maybe you missed suffix "Node".')
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
                        if (
                        doc := self.db.get_sensor_setting(name=kwargs.get('output_var', kwargs['input_var']))) is None:
                            raise ValueError(f'Invalid output_var for {n.name}: {kwargs.get("output_var")}')
                        for field in fields:
                            setup_kwargs[field] = doc.get(field)
                    setup_kwargs['influx_cfg'] = influx_cfg
                    setup_kwargs['write_to_influx'] = self.db.write_to_influx
                    setup_kwargs['send_to_pipelines'] = self.db.send_value_to_pipelines
                    setup_kwargs['log_alarm'] = getattr(self.monitor, 'log_alarm', None)
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
        self.reconfigure(config['node_config'],
                         {n: self.db.get_sensor_setting(n) for n in self.depends_on})
        for pl in self.subpipelines:
            for node in pl:
                if isinstance(node, Doberman.BufferNode) and not isinstance(node, Doberman.MergeNode):
                    num_buffer_nodes += 1
                    longest_buffer = max(longest_buffer, n.buffer.length)

        self.startup_cycles = num_buffer_nodes + longest_buffer  # I think?
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
                        break  # break because i is no longer valid

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
                    for config_item in node.sensor_config_needed:
                        this_node_config[config_item] = rd[config_item]
                node.load_config(this_node_config)

    def silence_for(self, duration, level=0):
        """
        Silence this pipeline for a set amount of time
        """
        doc = {
            'to': self.monitor.name,
            'from': self.name,
            'time': time.time() + duration,
            'command': f'pipelinectl_active {self.name}'
        }
        self.db.set_pipeline_value(self.name, [('status', 'silent'), ('silent_until', time.time() + duration)])
        self.command_socket.send_string(json.dumps(doc))
        _ = self.command_socket.recv_string()
        self.silenced_at_level = level

    def send_command(self, command, to):
        """
        Send a command to the HV
        """
        self.command_socket.send_string(json.dumps({
            'to': to, 'time': time.time(),
            'from': self.name, 'command': command}))
        _ = self.command_socket.recv_string()


class SyncPipeline(Pipeline):
    """
    A subclass to handle synchronous operation where input comes from
    the data communication bus rather than via the database. self.run
    sits around waiting for data to come in, and only runs once a set
    minimum number of nodes have received new values.
    """

    def build(self, config):
        super().build(config)
        self.listens_for = collections.defaultdict(list)
        for pl in self.subpipelines:
            for node in pl:
                if isinstance(node, Doberman.SensorSourceNode):
                    self.listens_for[node.input_var].append(node)

    def run(self):
        socket = self.ctx.socket(zmq.SUB)
        host, ports = self.db.get_comms_info('data')
        socket.connect(f'tcp://{host}:{ports["recv"]}')
        for name in self.depends_on:
            socket.setsockopt_string(zmq.SUBSCRIBE, name)
        poller = zmq.Poller()
        poller.register(socket, zmq.POLLIN)
        has_new = set()
        while not self.event.is_set():
            socks = dict(poller.poll(timeout=1000))
            if socks.get(socket) == zmq.POLLIN:
                try:
                    msg = None
                    msg = socket.recv_string()
                    n, t, v = msg.split(' ')
                    t = float(t)
                    v = float(v) if '.' in v else int(v)
                    has_new.add(n)
                    for node in self.listens_for[n]:
                        node.receive_from_upstream({n: v, 'time': t})
                except Exception as e:
                    self.logger.debug(f'{type(e)}: {msg}')
                else:
                    if has_new >= self.required_inputs:
                        self.process_cycle()
                        has_new.clear()
