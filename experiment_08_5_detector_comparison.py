"""PITUFO - EXPERIMENT 8.5 | A/B overload detector comparison.

Reuses the Experiment 08 motor model (estimated, NOT calibrated constants).
1. Generates simulated measurements using TUNING seeds (810000+...).
2. Selects detector B from candidate configurations using only TUNING data.
3. Compares baseline detector A and selected B on NEW seeds (910000+...).
4. Displays an educational ASCII report and asks before exporting CSV files.

Simulation results are not validation against physical motors.
Standard library only; designed to run in Coding Python on Android.
"""

import csv
import math
import os
import random
from datetime import datetime

# Inherited from Experiment 08; engineering estimates, NOT measurements.
OPEN_CIRCUIT_VOLTAGE, BATTERY_RESISTANCE, DRIVER_RESISTANCE = 12.0, 0.18, 0.565
MOTOR_RESISTANCE, MOTOR_INDUCTANCE, BACK_EMF_CONSTANT, TORQUE_CONSTANT = 5.5, 0.025, 0.80, 0.63
ROTOR_INERTIA, VISCOUS_FRICTION, DRY_FRICTION_TORQUE, BASE_LOAD_TORQUE = 0.018, 0.004, 0.025, 0.045
TIME_STEP = 0.002
DURATION_SECONDS, FAULT_START_SECOND, FAULT_END_SECOND = 18, 7, 11
TUNING_RUNS_PER_SCENARIO = 10
VALIDATION_RUNS_PER_SCENARIO = 10
EXPORT_MODE = 'ASK'  # Set to '0' to disable the export prompt.

SCENARIOS = [
    ('01_NORMAL', 'normal', ()),
    ('02_VARIABILITY', 'variability', ()),
    ('03_HIGH_NOISE', 'noise', ()),
    ('04_LOW_BATTERY', 'battery', ()),
    ('05_SHORT_LOAD', 'short', ()),
    ('06_MILD_OVERLOAD_M1', 'mild', (0,)),
    ('07_OVERLOAD_M1', 'strong', (0,)),
    ('08_OVERLOAD_M2', 'strong', (1,)),
    ('09_OVERLOAD_BOTH', 'strong', (0, 1)),
    ('10_NOISE_LOW_BATTERY_FAULT', 'combined', (0, 1)),
]

# (name, nominal RPM fraction threshold, current increase in A, sample count)
BASELINE_DETECTOR = ('A_BASELINE', 0.82, 0.14, 2)
CANDIDATE_DETECTORS = [
    ('B1_MILD', 0.86, 0.11, 2),
    ('B2_MODERATE', 0.88, 0.10, 2),
    ('B3_SENSITIVE', 0.90, 0.08, 2),
    ('B4_VERY_SENSITIVE', 0.92, 0.07, 2),
    ('B5_PERSISTENT', 0.90, 0.08, 3),
]


class DCMotor:
    """Average-voltage, one-direction DC motor approximation."""

    def __init__(
        self,
        resistance=MOTOR_RESISTANCE,
        back_emf=BACK_EMF_CONSTANT,
        torque_constant=TORQUE_CONSTANT,
        inertia=ROTOR_INERTIA,
        viscous_friction=VISCOUS_FRICTION,
        dry_friction=DRY_FRICTION_TORQUE,
    ):
        self.resistance = resistance
        self.back_emf = back_emf
        self.torque_constant = torque_constant
        self.inertia = inertia
        self.viscous_friction = viscous_friction
        self.dry_friction = dry_friction
        self.current = 0.0
        self.angular_velocity = 0.0

    def step(self, pwm, bus_voltage, load_torque):
        if pwm == 0:
            # Simplified coasting behavior; no regenerative current.
            self.current *= math.exp(-TIME_STEP / 0.004)
        else:
            applied_voltage = bus_voltage * pwm / 100.0
            current_derivative = (
                applied_voltage
                - (self.resistance + DRIVER_RESISTANCE) * self.current
                - self.back_emf * self.angular_velocity
            ) / MOTOR_INDUCTANCE
            self.current = max(0.0, self.current + current_derivative * TIME_STEP)

        electromagnetic_torque = self.torque_constant * self.current
        resisting_torque = (
            load_torque
            + self.viscous_friction * self.angular_velocity
            + self.dry_friction
        )
        self.angular_velocity = max(
            0.0,
            self.angular_velocity
            + (electromagnetic_torque - resisting_torque) * TIME_STEP / self.inertia,
        )

    def rpm(self):
        return self.angular_velocity * 60.0 / (2.0 * math.pi)


def create_motor_with_variation(rng, scenario_type):
    electrical_spread = 0.08 if scenario_type in ('variability', 'combined') else 0.03
    mechanical_spread = 0.15 if scenario_type in ('variability', 'combined') else 0.08

    def vary(value, spread):
        return value * rng.uniform(1 - spread, 1 + spread)

    return DCMotor(
        resistance=vary(MOTOR_RESISTANCE, electrical_spread),
        back_emf=vary(BACK_EMF_CONSTANT, electrical_spread),
        torque_constant=vary(TORQUE_CONSTANT, electrical_spread),
        inertia=vary(ROTOR_INERTIA, mechanical_spread),
        viscous_friction=vary(VISCOUS_FRICTION, mechanical_spread),
        dry_friction=vary(DRY_FRICTION_TORQUE, mechanical_spread),
    )


def generate_telemetry(name, scenario_type, affected_motors, seed):
    """Generate ONE measurement sequence shared by every detector."""
    rng = random.Random(seed)
    motors = [create_motor_with_variation(rng, scenario_type) for _ in range(2)]
    reference_motors = [DCMotor(), DCMotor()]
    rpm_noise = 4.0 if scenario_type in ('noise', 'combined') else 0.8
    current_noise = 0.035 if scenario_type in ('noise', 'combined') else 0.01
    supply_voltage = 10.6 if scenario_type in ('battery', 'combined') else OPEN_CIRCUIT_VOLTAGE
    battery_resistance = BATTERY_RESISTANCE * (
        1.30 if scenario_type in ('battery', 'combined') else 1.0
    )
    records = []

    for second in range(1, DURATION_SECONDS + 1):
        pwm = 0 if (second == 1 or second >= 17) else 75
        in_fault_window = FAULT_START_SECOND <= second <= FAULT_END_SECOND
        short_load = scenario_type == 'short' and second == FAULT_START_SECOND
        loads = []

        for motor_index in range(2):
            extra_load = 0.0
            if in_fault_window and motor_index in affected_motors:
                extra_load = 0.105 if scenario_type == 'mild' else 0.28
            if short_load and motor_index == 1:
                extra_load = 0.28
            loads.append(max(0.0, BASE_LOAD_TORQUE + rng.uniform(-0.003, 0.003) + extra_load))

        for _ in range(int(1.0 / TIME_STEP)):
            bus_voltage = max(
                8.5, supply_voltage - battery_resistance * sum(m.current for m in motors)
            )
            for motor_index in range(2):
                motors[motor_index].step(pwm, bus_voltage, loads[motor_index])
                reference_motors[motor_index].step(pwm, bus_voltage, BASE_LOAD_TORQUE)

        motor_rpm = []
        currents = []
        for motor_index in range(2):
            motor_rpm.append(max(
                0.0,
                motors[motor_index].rpm() + (rng.gauss(0, rpm_noise) if pwm else 0.0),
            ))
            currents.append(max(
                0.0,
                motors[motor_index].current + rng.gauss(0, current_noise),
            ))

        records.append({
            'time_s': second,
            'pwm_pct': pwm,
            'bus_voltage_v': bus_voltage,
            'motor_rpm': motor_rpm,
            'motor_current_a': currents,
            'reference_rpm': [m.rpm() for m in reference_motors],
            'reference_current_a': [m.current for m in reference_motors],
            'fault_injected': [
                bool(in_fault_window and k in affected_motors) for k in range(2)
            ],
            'short_load': bool(short_load),
        })

    return records


def evaluate_detector(records, configuration, affected_motors, scenario_type):
    """The detector never reads injected-fault labels; the evaluator does."""
    name, rpm_ratio, current_increase, required_samples = configuration
    consecutive_counts = [0, 0]
    detected_flags = [False, False]
    detection_times = [None, None]
    alerts_outside_injection = 0
    recovery_alerts = 0
    non_recovery_alerts = 0
    short_load_warnings = 0
    states = []

    for record in records:
        current_states = []
        for motor_index in range(2):
            anomaly_suspected = (
                record['pwm_pct'] >= 45
                and record['reference_rpm'][motor_index] >= 40
                and record['motor_rpm'][motor_index] < rpm_ratio * record['reference_rpm'][motor_index]
                and record['motor_current_a'][motor_index]
                    > record['reference_current_a'][motor_index] + current_increase
            )
            consecutive_counts[motor_index] = (
                consecutive_counts[motor_index] + 1 if anomaly_suspected else 0
            )
            if consecutive_counts[motor_index] >= required_samples:
                status = 'ALERT'
            elif consecutive_counts[motor_index] > 0:
                status = 'WARNING'
            else:
                status = 'NORMAL'
            current_states.append(status)

            # Ground-truth labels are used ONLY for scoring, never detection.
            if status == 'ALERT':
                if record['fault_injected'][motor_index]:
                    detected_flags[motor_index] = True
                    if detection_times[motor_index] is None:
                        detection_times[motor_index] = record['time_s']
                else:
                    alerts_outside_injection += 1
                    if (
                        motor_index in affected_motors
                        and FAULT_END_SECOND < record['time_s'] <= FAULT_END_SECOND + 2
                    ):
                        recovery_alerts += 1
                    else:
                        non_recovery_alerts += 1
            if scenario_type == 'short' and status == 'WARNING':
                short_load_warnings += 1
        states.append(current_states)

    expected = len(affected_motors)
    detected = sum(1 for k in affected_motors if detected_flags[k])
    latencies = [
        detection_times[k] - FAULT_START_SECOND
        for k in affected_motors
        if detection_times[k] is not None
    ]
    return {
        'expected': expected,
        'detected': detected,
        'missed': expected - detected,
        'outside_injection': alerts_outside_injection,
        'recovery_alerts': recovery_alerts,
        'non_recovery_alerts': non_recovery_alerts,
        'short_load_warnings': short_load_warnings,
        'total_latency': sum(latencies),
        'latency_count': len(latencies),
        'states': states,
    }


def add_metrics(accumulator, metrics):
    for field in (
        'expected', 'detected', 'missed', 'outside_injection',
        'recovery_alerts', 'non_recovery_alerts', 'short_load_warnings',
        'total_latency', 'latency_count',
    ):
        accumulator[field] += metrics[field]


def empty_metrics():
    return {key: 0 for key in (
        'expected', 'detected', 'missed', 'outside_injection',
        'recovery_alerts', 'non_recovery_alerts', 'short_load_warnings',
        'total_latency', 'latency_count',
    )}


def build_dataset(base_seed, repeats):
    """Run the Experiment 08 motor model without recalibrating parameters."""
    cases = []
    for scenario_index, (name, scenario_type, affected_motors) in enumerate(SCENARIOS):
        for repetition in range(repeats):
            seed = base_seed + scenario_index * 1000 + repetition
            samples = generate_telemetry(name, scenario_type, affected_motors, seed)
            cases.append((name, scenario_type, affected_motors, seed, samples))
    return cases


def evaluate_batch(cases, configuration):
    totals = empty_metrics()
    by_scenario = {}
    by_case = []
    for name, scenario_type, affected_motors, seed, samples in cases:
        metrics = evaluate_detector(samples, configuration, affected_motors, scenario_type)
        add_metrics(totals, metrics)
        if name not in by_scenario:
            by_scenario[name] = empty_metrics()
        add_metrics(by_scenario[name], metrics)
        by_case.append((name, scenario_type, affected_motors, seed, metrics))
    return totals, by_scenario, by_case


def detector_score(totals):
    # Fixed penalties chosen BEFORE evaluating the validation set.
    # Recovery-period alerts are evaluated separately.
    return (
        50 * totals['detected']
        - 100 * totals['non_recovery_alerts']
        - 15 * totals['recovery_alerts']
        - 2 * totals['short_load_warnings']
    )


def percentage(numerator, denominator):
    return (100.0 * numerator / denominator) if denominator else 0.0


def progress_bar(pct, width=20):
    filled = max(0, min(width, int(round(pct / 100 * width))))
    return '[' + '#' * filled + '.' * (width - filled) + ']'


def print_detection_summary(name, baseline, candidate):
    print('\n' + '=' * 55)
    print('VALIDATION: ' + name)
    for label, metrics in (('A', baseline), ('B', candidate)):
        sensitivity = percentage(metrics['detected'], metrics['expected'])
        print('%s %s %5.1f%% (%d/%d)' % (
            label, progress_bar(sensitivity), sensitivity,
            metrics['detected'], metrics['expected'],
        ))
    print('Outside injection = confirmed alert samples,')
    print('NOT necessarily false alarms.')


def print_scenario_table(baseline, candidate):
    print('\nBY SCENARIO (validation with NEW seeds)')
    print('Scenario                   | A | B | alerts outside A/B')
    print('-' * 65)
    for name, _, affected_motors in SCENARIOS:
        first, second = baseline[name], candidate[name]
        print('%-27s | %2d/%2d | %2d/%2d | %2d / %2d' % (
            name, first['detected'], first['expected'],
            second['detected'], second['expected'],
            first['outside_injection'], second['outside_injection'],
        ))


def print_educational_example(cases, baseline_config, selected_config):
    # Mild-overload demonstration uses a held-out validation seed.
    example = next(case for case in cases if case[1] == 'mild')
    name, scenario_type, affected_motors, seed, samples = example
    states_a = evaluate_detector(samples, baseline_config, affected_motors, scenario_type)['states']
    states_b = evaluate_detector(samples, selected_config, affected_motors, scenario_type)['states']
    print('\n' + '=' * 55)
    print('LEARNING EXAMPLE: MILD OVERLOAD, IDENTICAL DATA FOR A AND B')
    print('Seed:', seed, '| * = extra load, shown ONLY for validation')
    print('t  M1 RPM  Ref RPM  M1 A  Ref A | detector A  detector B')
    for index, record in enumerate(samples):
        if record['time_s'] in (5, 6, 7, 8, 9, 11, 12):
            print('%2d%s %6.1f  %6.1f  %5.3f  %5.3f | %-11s %-11s' % (
                record['time_s'], '*' if record['fault_injected'][0] else ' ',
                record['motor_rpm'][0], record['reference_rpm'][0],
                record['motor_current_a'][0], record['reference_current_a'][0],
                states_a[index][0], states_b[index][0],
            ))
    return example, states_a, states_b


def ask_export_option():
    if EXPORT_MODE != 'ASK':
        return EXPORT_MODE if EXPORT_MODE in ('1', '2', '3') else '0'
    print('\nOPTIONAL EXPORT: 0=No files (default)')
    print('1=Summary CSV | 2=Detailed example CSV | 3=Both')
    try:
        answer = input('Save files? [0/1/2/3]: ').strip()
    except (EOFError, OSError, RuntimeError):
        print('Interactive input unavailable; no files will be saved.')
        return '0'
    return answer if answer in ('1', '2', '3') else '0'


def export_csv(rows, prefix):
    if not rows:
        return
    download_directory = '/storage/emulated/0/Download'
    filename = '%s_%s.csv' % (prefix, datetime.now().strftime('%Y%m%d_%H%M%S'))
    try:
        path = os.path.join(download_directory, filename)
        with open(path, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print('CSV SAVED:', path)
    except OSError as error:
        print('Could not save CSV to Downloads:', error)
        print('No copy was written to the app private directory.')


def main():
    print('PITUFO - EXPERIMENT 8.5 | A/B DETECTOR COMPARISON')
    print('Motor model inherited from Experiment 08; NO calibrated parameters')
    print('Generating the TUNING dataset...', flush=True)
    tuning_cases = build_dataset(810000, TUNING_RUNS_PER_SCENARIO)

    print('\nTUNING (only these seeds select detector B)')
    options = []
    for configuration in CANDIDATE_DETECTORS:
        metrics, _, _ = evaluate_batch(tuning_cases, configuration)
        score = detector_score(metrics)
        options.append((score, configuration, metrics))
        print('%-18s %2d/%2d detected, %2d outside-normal, '
              '%2d recovery, score=%d' % (
                  configuration[0], metrics['detected'], metrics['expected'],
                  metrics['non_recovery_alerts'], metrics['recovery_alerts'], score,
              ))
    # On ties, keep the more conservative option (earlier candidate).
    selected_config = max(options, key=lambda item: item[0])[1]
    print('SELECTED:', selected_config[0],
          '| RPM threshold=%.2f | current delta=%.2f A | samples=%d' % (
              selected_config[1], selected_config[2], selected_config[3],
          ))

    print('\nGenerating the INDEPENDENT VALIDATION dataset...', flush=True)
    validation_cases = build_dataset(910000, VALIDATION_RUNS_PER_SCENARIO)
    baseline_metrics, scenarios_a, cases_a = evaluate_batch(validation_cases, BASELINE_DETECTOR)
    improved_metrics, scenarios_b, cases_b = evaluate_batch(validation_cases, selected_config)
    print_detection_summary('TOTAL', baseline_metrics, improved_metrics)
    print_detection_summary(
        'MILD OVERLOAD ONLY',
        scenarios_a['06_MILD_OVERLOAD_M1'],
        scenarios_b['06_MILD_OVERLOAD_M1'],
    )
    print_scenario_table(scenarios_a, scenarios_b)

    print('\nVALIDATION METRICS')
    for label, metrics in (('A (baseline)', baseline_metrics), ('B (tuned)', improved_metrics)):
        mean_latency = (
            float(metrics['total_latency']) / metrics['latency_count']
            if metrics['latency_count'] else None
        )
        print('%s: detected %d/%d | missed %d | outside-normal %d | '
              'recovery %d | latency %s s' % (
                  label, metrics['detected'], metrics['expected'], metrics['missed'],
                  metrics['non_recovery_alerts'], metrics['recovery_alerts'],
                  ('%.2f' % mean_latency) if mean_latency is not None else 'N/A',
              ))

    example, states_a, states_b = print_educational_example(
        validation_cases, BASELINE_DETECTOR, selected_config,
    )
    print('\nIMPORTANT: Data are synthetic; there is NO physical validation.')
    print('Greater sensitivity may increase false alarms.')
    print('This is a fair comparison: identical PWM, sensor noise, and motor data for A/B.')

    export_option = ask_export_option()
    if export_option in ('1', '3'):
        summary_rows = []
        for case_a, case_b in zip(cases_a, cases_b):
            name, scenario_type, affected_motors, seed, baseline_case = case_a
            candidate_case = case_b[4]
            summary_rows.append({
                'scenario': name,
                'seed': seed,
                'expected_events': baseline_case['expected'],
                'A_detected': baseline_case['detected'],
                'B_detected': candidate_case['detected'],
                'A_missed': baseline_case['missed'],
                'B_missed': candidate_case['missed'],
                'A_non_recovery_alert_samples': baseline_case['non_recovery_alerts'],
                'B_non_recovery_alert_samples': candidate_case['non_recovery_alerts'],
                'A_recovery_alert_samples': baseline_case['recovery_alerts'],
                'B_recovery_alert_samples': candidate_case['recovery_alerts'],
                'selected_B_detector': selected_config[0],
            })
        export_csv(summary_rows, 'pitufo_experiment085_summary')

    if export_option in ('2', '3'):
        name, scenario_type, affected_motors, seed, records = example
        detail_rows = []
        for index, record in enumerate(records):
            detail_rows.append({
                'scenario': name,
                'seed': seed,
                'time_s': record['time_s'],
                'pwm_pct': record['pwm_pct'],
                'bus_voltage_v': round(record['bus_voltage_v'], 3),
                'motor1_rpm': round(record['motor_rpm'][0], 2),
                'motor1_reference_rpm': round(record['reference_rpm'][0], 2),
                'motor1_current_a': round(record['motor_current_a'][0], 3),
                'motor1_reference_current_a': round(record['reference_current_a'][0], 3),
                'motor1_fault_injected': int(record['fault_injected'][0]),
                'detector_A_state': states_a[index][0],
                'detector_B_state': states_b[index][0],
            })
        export_csv(detail_rows, 'pitufo_experiment085_example')

    print('\nEXPERIMENT 8.5 COMPLETED', flush=True)


if __name__ == '__main__':
    main()
