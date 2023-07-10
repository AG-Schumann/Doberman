import Doberman


class ControlNode(Doberman.Node):
    """
    Another empty base class to handle different database access
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.control_target = kwargs['control_target']
        self.control_value = kwargs['control_value']

    def set_output(self, value, _force=False):
        self.logger.debug(f'Setting {self.control_target} {self.control_value} to {value}')
        if not self.is_silent and not _force:
            self.pipeline.send_command(
                    command=f'set {self.control_value} {value}',
                    to=self.control_target)

    def on_error_do_this(self):
        if (v := self.config.get('default_output')) is not None:
            self.set_output(v, _force=True)


class DigitalControlNode(ControlNode):
    """
    A generalized node to handle digital output. The logic is assumed to be
    upstream.
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.one_input = kwargs.get('one_input', False)

    def process(self, package):
        if self.one_input:
            self.set_output(package[self.input_var])
        else:
            if package[self.input_var[0]]:
                self.logger.info(f'{self.name}: opening')
                self.set_output(1)
            elif package[self.input_var[1]]:
                self.logger.info(f'{self.name}: closing')
                self.set_output(0)


class AnalogControlNode(ControlNode):
    """
    A generalized node to handle analog output. The logic is assumed to be
    upstream
    """
    def process(self, package):
        val = package[self.input_var]
        if (min_output := self.config.get('min_output')) is not None:
            val = max(val, min_output)
        if (max_output := self.config.get('max_output')) is not None:
            val = min(val, max_output)
        self.set_output(val)


class PipelineControlNode(Doberman.Node):
    """
    Sometimes you want one pipeline to control another.
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.actions = kwargs['actions']

    def process(self, package):
        for condition, actions in self.actions.items():
            if package.get(condition, False):
               for action in actions:
                   self.control_pipeline(*action)

        if package.get('condition_test', False):
            # this one is mainly for testing
            self.control_pipeline('stop', self.pipeline.name)

    def control_pipeline(self, action, pipeline):
        if self.is_silent:
            return
        if pipeline.startswith('control'):
            target = 'pl_control'
        elif pipeline.startswith('alarm'):
            target = 'pl_alarm'
        elif pipeline.startswith('convert'):
            target = 'pl_convert'
        else:
            raise ValueError(f'Don\'t know what to do with pipeline {pipeline}')
        self.logger.debug(f"Sending {action} to {pipeline}")
        self.pipeline.send_command(command=f'pipelinectl_{action} {pipeline}',
                to=target)

