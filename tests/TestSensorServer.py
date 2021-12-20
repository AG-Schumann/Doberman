import random
import time
import socket
import threading
import numpy as np
import sys

# constants
p_amb = 101325  # Pa
R = 8.314  # m^3 Pa/K/mol
nitrogen_molar_mass = 0.028  # kg/mol
air_molar_mass = 0.03  # kg/mol


def rand():
    """
    Most of the time we want something evenly distributed about 0. This returns [-1,1]
    """
    return 2 * random.random() - 1


def outside_temp(when=None):
    temp_base = 290  # K
    temp_variation = 4  # K
    t_period = 86400  # s
    t_phase = 2.135  # peak at 1600h
    return temp_base + temp_variation * np.sin((when or time.time()) / t_period - t_phase)


class Thermosiphon(object):
    def __init__(self, dewar):
        self.l_vap = 199.18e3  # J/kg
        self.rho_liq = 806.11  # kg/m^3
        self.T_liq = 78  # K
        self.A_cs = np.pi * 0.075 ** 2  # 15cm diameter nitrogen reservoir
        self.A_vent = np.pi * 0.01 ** 2  # 2cm diameter vent
        self.reservoir_length = 1.5  # m, height of LN2 storage
        self.m_liq = 1  # kg
        self.m_gas = (p_amb + 1) * self.A_cs * (self.reservoir_length - self.liquid_level()) / (
                    R * self.T_gas) * nitrogen_molar_mass
        self.liquid_in = 0  # kg/s
        self.gas_purge = 0  # kg/s
        self.p_active = 1.1 * 101325  # bar, active region
        self.q_leakage = 10  # W
        self.dewar = dewar

    def cooling_power(self):
        """ in kW """
        # logistic function because meh. TODO improve
        max_cooling_power = 800  # W, because this TS is more powerful
        p0 = 4 * 101325  # Pa, abs
        k = 1 / (4 * 101325)  # /Pa
        return max_cooling_power / (1 + np.exp(-k * (self.p_active - p0))) * (self.m_liq > 0.001) * (
                    self.p_active > p_amb * 1.05)

    def liquid_level(self):
        """ in m """
        return self.m_liq / (self.A_cs * self.rho_liq)

    def set_pressure(self, val):
        self.p_active = val

    def llm(self):
        """ in pF """
        min_cap = 20.56  # pF
        max_cap = 36.52  # pF
        min_level = 0.05  # m
        return np.interp(self.liquid_level(), [min_level, self.reservoir_length], [min_cap, max_cap])

    @property
    def T_gas(self):
        """ in K """
        return 0.5 * (self.T_liq + outside_temp())

    @property
    def V_gas(self):
        """ in m^3 """
        return self.A_cs * (self.reservoir_length - self.liquid_level())

    @property
    def p_gas(self):
        """ in Pa """
        return (self.m_gas / nitrogen_molar_mass) * R * self.T_gas / self.V_gas

    @property
    def rho_gas(self):
        """ kg/m^3 """
        return self.m_gas / self.V_gas

    def vent_rate(self, dt=None):
        """ kg/s
        For reasons of fluid dynamics, the math gets absurd if you vent to a non-zero sink pressure,
        so we approximate with a pure exponential rather than the exact solution which isn't analytical.
        If you don't think this is reasonable then feel free to improve it.
        """
        dp = self.p_gas - p_amb
        dmdt = 0 if dp < 0 else self.A_vent * np.sqrt(2 * dp * self.rho_gas)
        m_atm = p_amb * self.V_gas / (R * self.T_gas) * nitrogen_molar_mass
        if dt is None:
            return dmdt
        # if we have a value for dt then we can do the higher-order corrections
        return (self.m_gas - m_atm) * (1 - np.exp(-dmdt * dt))
        # second-order correction stuff that seemed useful at the time but I'll leave here for now
        # the exact expression is harder to work with because you can't solve it analytically
        # dmdt = self.Avent * np.sqrt(2*abs(dp) * self.rho_gas)
        # dpdt = 1/m * dmdt * R * self.T_gas / self.V_gas
        # drhodt = 1/self.V_gas * dmdt
        # d2mdt2 = 0.5 * self.Avent / np.sqrt(2*dp * self.rho_gas) * (2 * drhodt*dp + 2*self.rho_gas * dpdt)
        # return dmdt if dp > 0 else -dmdt

    def max_step(self):
        boiloff_rate = (self.cooling_power() + self.q_leakage) / self.l_vap
        dmdt_liquid = self.dewar.nitrogen_out - boiloff_rate
        dmdt_gas = boiloff_rate + self.gas_purge - self.vent_rate()
        ret = min(abs(0.01 * self.m_liq / dmdt_liquid), abs(0.01 * self.m_gas / dmdt_gas))
        # print(f'TS max step {ret:.3f}')
        return ret

    def step(self, dt, _print=False):
        """
        One step in the simulation
        """
        boiloff_rate = (self.cooling_power() + self.q_leakage) / self.l_vap
        dm_liquid = self.dewar.nitrogen_out - boiloff_rate * dt
        dm_gas = boiloff_rate * dt + self.gas_purge * dt - self.vent_rate(dt)
        if _print:
            print(
                f'TS {self.m_liq:.3f} kg | {dm_liquid / dt:.3g} kg/s | {self.m_gas:.3g} kg | '
                f'{dm_gas / dt:.3g} kg/s | {(self.p_gas - p_amb) / 100:.1f} mbar | '
                f'{self.cooling_power():.1f} W')
        self.m_liq = max(0, self.m_liq + dm_liquid)
        self.m_gas = max(0, self.m_gas + dm_gas)


class IsoVac(object):
    def __init__(self, ic):
        self.volume = 3.5  # m^3
        rho_air = 1.2  # kg/m3 at room temperature
        self.m_gas = self.volume * rho_air  # kg
        self.pump_perf = np.array([(1, 100), (0.3, 110), (0.04, 400), (0.01, 650), (0.005, 685), (0, 685)],
                                  dtype=[('p', np.float32), ('rate', np.float32)])
        self.gas_conductivity = np.array(
            [(0, 0), (1e-7, 1e-3), (1e-6, 1e-2), (1e-5, 0.1), (1e-4, 1), (1e-3, 10), (1e-2, 85), (0.1, 400), (1, 700),
             (2000, 700)], dtype=[('p', np.float32), ('Q', np.float32)])
        self.roughing_pump_rate = 3 # m^3/hr
        turbo_spinup_time = 5.5 * 60 # seconds
        self.turbo_hz = 0
        self.turbo_max_hz = 1500
        self.turbo_ramp_rate = self.turbo_max_hz/turbo_spinup_time
        self.turbo_pressure_threshold = 10 # mbar
        self.ic = ic

    def outgassing(self):
        rate = 1e-19  # kg/s/K**4
        return rate * (outside_temp() ** 4 + self.ic.temperature ** 4)

    def heat_transfer(self):
        scale = 1 / 120  # W/K
        p = self.pressure / 100  # mbar
        return np.interp(p, self.gas_conductivity['p'], self.gas_conductivity['Q']) * scale

    @property
    def pressure(self):
        """ mbar """
        return self.m_gas / air_molar_mass * R * self.temperature / self.volume

    @property
    def rho_gas(self):
        """ kg/m3 """
        return self.m_gas / self.volume

    @property
    def temperature(self):
        """ K """
        return 0.5 * (outside_temp() + self.ic.temperature)

    def pump_rate(self, dt=None):
        p = self.pressure / 100  # convert to mbar
        if p > self.turbo_pressure_threshold:
            # turbo isn't on, use RP
            # scale = 1hr/3600s * 1000l/1m^3 = 1/3.6
            liters_per_second = self.roughing_pump_rate / 3.6
        else:
            if dt is not None:
                # spin the turbo up a bit
                drpm = self.turbo_ramp_rate * dt
                # but only if necessary
                self.turbo_hz = max(self.turbo_max_hz, self.turbo_hz + dt*drpt)
            liters_per_second = np.interp(p, self.pump_perf['p'], self.pump_perf['rate']) * self.turbo_hz/self.turbo_max_hz
        return liters_per_second / 1000 * self.rho_gas

    def max_step(self):
        ret = 0.01 * self.m_gas / abs(self.outgassing() - self.pump_rate())
        # print(f'IV max step {ret:.3g}')
        return ret

    def step(self, dt, _print=False):
        dm_gas = (self.outgassing() - self.pump_rate(dt=dt)) * dt
        self.m_gas = max(0, self.m_gas + dm_gas)
        if _print:
            print(
                f'IV pressure {self.pressure / 100:.2g} mbar | rate {self.pump_rate():.2g} kg/s | {self.m_gas:.3g} kg | '
                f'{self.turbo_hz:.1f} Hz')


class InnerCryostat(object):
    def __init__(self):
        mass = np.array([1000, 2000])  # kg, top/bottom
        heat_cap = 1200  # J/kg/K
        self.thermal_mass = heat_cap * mass  # J/K
        self.temp = np.array([outside_temp(), outside_temp()])
        self.q_net = 0  # W

    @property
    def temperature(self):
        """ weighted sum of top and bottom """
        return (self.temp * self.thermal_mass).sum() / self.thermal_mass.sum()

    def max_step(self):
        ret = 0.01 * self.temperature * self.thermal_mass.sum() / max(abs(self.q_net), 1)
        return ret

    def step(self, dt, _print=False):
        K = 16.2 * (36 * np.pi * 0.01 ** 2) / 0.1  # thermal conductivity of steel, 36 M20 bolts of 10cm length
        q_top = (self.temp[1] - self.temp[0]) * K
        q_bot = self.q_net - q_top
        dq = np.array([q_top, q_bot])
        self.temp += dq * dt / self.thermal_mass
        if _print:
            print(f'IC {self.temp[0]:.1f}/{self.temp[1]:.1f} K | {self.q_net:.3g} W | {q_top:.3g} W')


class Dewar(object):
    def __init__(self):
        self.empty_mass = 120  # kg
        rho_liquid = 800  # kg/m3
        self.capacity = 0.200 * rho_liquid
        self.nitrogen = 0.200 * rho_liquid
        self.q_leakage = 1  # W
        self.valve = 0
        self.flow_rate = 0.025  # kg/s out
        self.nitrogen_out = 0

    @property
    def scale(self):
        return self.empty_mass + self.nitrogen

    def fill(self):
        self.nitrogen = self.capacity

    def valve_control(self, val):
        self.valve = val

    def max_step(self):
        l_vap = 200000  # J/kg
        min_nitrogen = 10  # kg? sure
        boiloff = self.q_leakage / l_vap
        out = (self.nitrogen > min_nitrogen) * (self.valve == 1) * self.flow_rate
        ret = abs(0.01 * self.nitrogen / (boiloff + out))
        # print(f'Dewar max dt {ret:.2f}')
        return ret

    def step(self, dt, _print=False):
        l_vap = 200000  # J/kg
        min_nitrogen = 10  # kg? sure
        boiloff = self.q_leakage * dt / l_vap
        self.nitrogen_out = (self.nitrogen > min_nitrogen) * (self.valve == 1) * self.flow_rate * dt
        if _print:
            print(f'Dewar scale {self.scale:.2g} kg | output {self.nitrogen_out:.2g} kg/s')
        self.nitrogen = max(0, self.nitrogen - self.nitrogen_out - boiloff)


class FastCooling(object):
    def __init__(self, dewar, iv, ic):
        self.dewar = dewar
        self.iv = iv
        self.ic = ic

    def thermal_contact(self):
        pass


class LabSimulator(object):

    def __init__(self, time_scale):
        self.event = threading.Event()
        self.time_scale = time_scale
        self.dewar = Dewar()
        self.ts = Thermosiphon(self.dewar)
        self.ic = InnerCryostat()
        self.iso_vac = IsoVac(self.ic)
        self.fc = FastCooling(self.dewar, self.iso_vac, self.ic)
        self.print_every_seconds = 10
        self.last_print = time.time()

    def step(self, dt):
        if (time.time() - self.last_print) > self.print_every_seconds:
            verbose = True
            self.last_print = time.time()
        else:
            verbose = False
        k_cond = 20  # 20 W at operating temp
        k_rad = 5.67e-9  # 40 W at operating temp

        t_out = outside_temp()

        q_cond = k_cond * (t_out - self.ic.temperature)
        q_conv = self.iso_vac.heat_transfer() * (t_out - self.ic.temperature)
        q_rad = k_rad * (t_out ** 4 - self.ic.temperature ** 4)
        q_in = q_cond + q_conv + q_rad
        q_out = self.ts.cooling_power()
        self.ic.q_net = q_in - q_out

        self.ts.step(dt, verbose)
        self.ic.step(dt, verbose)
        self.iso_vac.step(dt, verbose)
        self.dewar.step(dt, verbose)

    def run(self):

        dt = 0.001
        while not self.event.is_set():
            try:
                self.event.wait(dt)
                self.step(dt * self.time_scale)
            except Exception as e:
                print(f'Caught a {type(e)}: {e}')
                time.sleep(1)

    def observe(self, quantity):
        """
        Peek into what the system is currently doing. Returns a string-cast value with some noise
        added on top for good measure
        """
        if quantity == 'T_IC_01':
            noise = 0.1 * rand()  # 0.1 K
            return f'{self.ic.temp[1] + noise:.2f}'
        if quantity == 'T_IC_02':
            noise = 0.1 * rand()
            return f'{self.ic.temp[0] + noise:.2f}'
        if quantity == 'T_LB_01':
            noise = 0.2 * rand()  # 0.2 K
            return f'{outside_temp() + noise:.1f}'
        if quantity == "L_TS_01":
            noise = 2 * rand()  # pf
            return f'{self.ts.llm() + noise:.1f}'
        if quantity == 'S_TS_01':
            return f'{self.dewar.valve}'
        if quantity == 'P_OC_01':
            noise = 0.01 * rand() + 1  # 1%
            v = min(self.iso_vac.pressure, 1e4) # gauge doesn't work well below 100 mbar
            return f'{v / 100 * noise:.3g}'
        if quantity == 'M_LB_01':
            noise = rand()
            return f'{self.dewar.scale + noise:.1f}'
        return -1

    def take_input(self, quantity, value):
        try:
            if quantity == 'S_TS_01' and value in '01':
                return self.dewar.valve_control(int(value))
            if quantity == 'dewar_fill':
                return self.dewar.fill()
            if quantity == 'ts_pressure':
                return self.ts.set_pressure(float(val))
            else:
                print(f'Rejecting input: "{quantity}"')
        except Exception as e:
            print(f'Caught a {type(e)}: {e}')
            print(quantity, value)
        return -1


def main(lab):
    HOST, PORT = 'localhost', 9999
    t = threading.Thread(target=lab.run)
    t.start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(None)
        sock.bind((HOST, PORT))
        sock.listen()
        try:
            while True:
                conn, addr = sock.accept()
                with conn:
                    data = conn.recv(1024).strip().decode()
                    if 'READ' in data:
                        # format READ:t_in or something
                        ch = data.split(':')[1]
                        if (val := lab.observe(ch)) == -1:
                            output = f'FAIL:bad_ch'
                        else:
                            output = f'OK;{val}'
                    elif 'SET' in data:
                        # format SET:q_out=3 or something
                        data = data.split(':')[1]
                        ch, val = data.split('=')
                        if (result := lab.take_input(ch, val)) == -1:
                            output = f'FAIL;bad_ch'
                        else:
                            output = f'OK;{ch}={val}'
                    else:
                        output = f'FAIL;bad_cmd'
                    conn.send(output.encode())
        except:
            pass
    lab.event.set()
    t.join()


if __name__ == '__main__':
    scale = 1
    if len(sys.argv) > 1:
        scale = int(sys.argv[1])
    lab = LabSimulator(scale)
    main(lab)
