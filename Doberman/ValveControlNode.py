import Doberman


class ValveControlNode(Doberman.ControlNode):
    """
    A logic node to control a nitrogen level valve, based on a levelmeter and a control valve,
    with optional inhibits from a vacuum or a scale
    """
    def process(self, package):
        liquid_level = package['liquid_level']
        fill_rate = package['liquid_level_rate']
        valve_status = package['valve_state']

        low_level = self.config['liquid_level_low']
        high_level = self.config['liquid_level_high']
        min_fill_rate = self.config['min_fill_rate']
        max_fill_time = self.config['max_fill_time']
        max_iso_vac = self.config.get('max_iso_vac', -1)
        min_scale = self.config.get('min_scale', -1)
        vac_is_good = max_iso_vac == -1 or package.get('iso_vac_pressure', 0) < max_iso_vac
        scale_is_good = min_scale == -1 or package.get('scale_weight', 0) < min_scale

        if liquid_level < low_level:
            if valve_status == 0:
                # valve is closed, level is too low
                if vac_is_good and scale_is_good:
                    # open the valve
                    self.set_output(1)
                    self.valve_opened = package['time']
                    self.logger.info('Scheduling valve opening')
                else:
                    self.logger.info('Would love to open the valve but either the scale or vac is out of range')
            else:
                # valve is open, check to see for how long
                if hasattr(self, 'valve_opened'):
                    if (dt := (package['time']-self.valve_opened)) > some_value:
                        # filling too slowly! Something fishy
                        # TODO something reasonable
                        pass
                    else:
                        # probably still waiting for the pipes to chill
                        pass
                else:
                    # we don't have a self.valve_opened, valve was probably opened by something else
                    # TODO how to handle?
                    pass

        elif low_level < liquid_level < high_level:
            if valve_status == 1:
                if hasattr(self, 'valve_opened'):
                    if (dt := (package['time']-self.valve_opened)) > max_fill_time:
                        # filling too long!
                        # TODO something reasonable
                        self.logger.fatal(f'Valve has been open for {dt/60:.1f} minutes without reaching full, something wrong?')
                    else:
                        if fill_rate < min_fill_rate and dt > some_value:
                            # filling too slowly! Something fishy
                            # TODO something reasonable
                            pass
                        else:
                            fill_pct = (liquid_level - low_level)/(high_level - low_level)
                            self.logger.debug(f'Valve has been open for {int(dt//60)}m{int(dt%60)}s, filling at {fill_rate:.1f} ({fill_pct:.1f}%)')
                else:
                    # we don't have a self.valve_opened, valve was probably opened by something else
                    # TODO how to handle?
                    pass
            else:
                # valve is closed, we're in "normal" conditions
                pass

        else:
            # liquid level > high
            if valve_status == 1:
                # reached FULL
                self.set_output(0)
                self.logger.info('Scheduling valve closing')
            else:
                # valve is closed
                pass