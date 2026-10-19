# Motor Telemetry Simulator

Physics-based DC motor simulation, synthetic telemetry generation, and anomaly detection in Python.

## Project Overview

This project explores model-based fault detection for a two-motor robotic system. It simulates DC motor electrical and mechanical behavior, generates synthetic telemetry, and evaluates rule-based overload detection algorithms.

The long-term goal is to connect the diagnostic system to real embedded hardware and validate its behavior using physical measurements.

## Technical Approach

The simulator models motor current, angular velocity, electromagnetic torque, friction, mechanical load, and battery voltage sag.

It includes motor parameter variation, measurement noise, individual and simultaneous motor overloads, and reference motor models used to identify deviations from expected behavior.

The simulation uses forward Euler numerical integration with a 2 ms time step.

## Experiment 8.5 — A/B Detector Comparison

Two overload detectors were evaluated on the same simulated measurement sequences.

| Detector | Detected events | Detection rate |
|---|---|---|
| A — Baseline | 60/70 | 85.7% |
| B — Tuned | 70/70 | 100% |

Detector B was selected using a tuning dataset and evaluated using a separate set of random seeds.

These results apply only to the synthetic validation scenarios tested.

## Limitations

Motor parameters are engineering estimates, not experimentally calibrated values. The system has not yet been validated against physical motors.

Real-world performance may be affected by battery behavior, motor drivers, mechanical characteristics, sensor accuracy, environmental conditions, and previously unseen failure modes.

## Running the Experiment

Requires Python 3 and uses only the Python standard library.

Run `python experiment_08_5_detector_comparison.py` from the repository directory.

## Future Development

Planned work includes modular software architecture, automated testing, improved documentation, physical motor calibration, and real-time telemetry integration with ESP32-based robotic systems.

## License

MIT License.
