# Executable checks

Run `python3 run_reproduction.py smoke --output ../paper-m-smoke` from the repository root.
The entry point executes the retained tests in components/S2:

- `work/ipm_phase2/weighted/test_weighted.py`: original flat compatibility and request/metric binding.
- `work/ipm_phase2/validation/validate_weighted.py`: independent finite-domain calculations and hostile input mutations.
- `work/ipm_phase2/validation/validate_bounds_cli.py`: row and bound equality plus native command-line roundtrips.
- `work/ipm_phase2/empirical/validate_enumerator.py`: C enumeration against independent Python scoring.
- `work/ipm_phase2/empirical/validate_scale_diagnostics.py`: same-completion scale diagnostics.

Full empirical checks are part of the `full` mode and need reconstructed original inputs.
The tests are run locally. No hosted CI or GitHub Actions workflow is provided.
