# The scanner container ignores SIGTERM, so every stop takes 30 seconds and ends in SIGKILL

- **Area:** Scanner / container lifecycle
- **Refs:** `engine/main.py`, `Makefile` (`RUN_SCANNER`, `serve`), `host/mcp-connectors-scanner.service`

## Context

Found while validating the system unit. `systemctl stop` runs `podman stop -t 30`, and the container only ended
after the full 30 seconds, with exit code 137 (SIGKILL). The scanner is a Python process running as PID 1, and
PID 1 gets no default handler for SIGTERM: its signal mask shows SIGINT caught and SIGTERM not. The unit's stop
timeout is 60 seconds, so the stop still succeeds and nothing is lost, but a stop during a sweep is always a
hard kill. Results are saved per connector, so a killed sweep keeps what it finished and leaves the run row
without a finish time. Two fixes were considered: add `--init` to the `podman run` in the Makefile, which puts a
small init in front that forwards signals, or handle SIGTERM in `engine/main.py` by shutting the API server down
and letting the sweep stop at the next connector.

## Deferred because

It is outside the service work that found it, and the second fix changes engine behavior that needs its own test.
The first fix is one flag but needs checking that `catatonit` is present on every host that runs the container.

## Revisit when

The next change to `engine/main.py`, or if a stop during a sweep ever leaves a run that confuses the published
results.
