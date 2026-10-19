# Motor Telemetry Simulator

A Python project for simulating DC motor behavior and experimenting with overload detection.

I started this project to better understand how motor current, RPM, mechanical load, and supply voltage interact in a robotic system.

The current version simulates two DC motors using electrical and mechanical equations, with forward Euler integration. It also includes battery voltage sag, sensor noise, motor parameter variation, and injected mechanical overloads.

## Overload detection

Instead of detecting faults using fixed RPM limits, the program compares simulated motor measurements against a reference motor model.

An overload is suspected when the motor runs significantly slower than expected while drawing more current.

Experiment 8.5 compares two detector configurations using the same simulated telemetry.

| Detector | Detected events |
|---|---|
| Baseline (A) | 60/70 (85.7%) |
| Tuned (B) | 70/70 (100%) |

The tuned detector was selected using one set of simulation seeds and tested using a separate validation set.

**These results are from simulation only.** The motor parameters are estimates, and the detector has not been tested with physical motors.

## Running the experiment

Requires Python 3. No external libraries are needed.

```bash
python experiment_08_5_detector_comparison.py
```

## Current limitations and next steps

The simulation is currently contained in a single Python file. My next step is to separate the motor model, telemetry generation, and detection logic into independent modules.

I also plan to compare simulated telemetry against measurements from real DC motors before using the detector in an embedded robotic system.

## License

MIT.
