# Persistent Nerd Referee services

The production checkout is /opt/referee in Proxmox LXC 106. Source is mounted into the bot, web, worker, harvester, and mock-duel services. Preserve the source mount and PYTHONPATH when deploying; image tags alone do not identify the running application code.

## Startup and recovery

The eight persistent services are postgres, redis, litellm, bot, web, worker, harvester, and mock-duels. Compose configures restart: always and limits each JSON log to three 10 MB files. PostgreSQL and Redis use persistent volumes; do not remove those volumes to restart the stack.

Deploy current configuration:

```sh
docker compose --profile harvest up -d --no-build --pull never postgres redis litellm bot web worker harvester mock-duels
install -m 0644 deploy/systemd/referee-supervisor.service /etc/systemd/system/
install -m 0644 deploy/systemd/referee-supervisor.timer /etc/systemd/system/
install -m 0644 deploy/systemd/battlebot-proactive.service /etc/systemd/system/
install -m 0644 deploy/systemd/battlebot-proactive.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now docker referee-supervisor.timer battlebot-proactive.timer
```

Enable Proxmox LXC startup on its host with `pct set 106 -onboot 1`. This setting was applied September 21, 2026. No host reboot was performed to test it.

The supervisor checks every minute after boot, starts stopped services, recreates missing containers from current Compose configuration, and restarts containers that have a failing Docker health check. It waits at least five minutes between recovery attempts for the same service. Docker itself handles process-crash restarts. A running process is not proof that its profile output is valid or its model response is grounded; those have separate acceptance checks.

Supervisor state is in /var/lib/nerd-referee-supervisor/state.json. Run `python3 services/referee_supervisor.py --dry-run` to inspect recovery decisions without starting containers or sending messages.

For deliberate maintenance, create `/opt/referee/.maintenance` before stopping services. Remove it when maintenance is complete. The supervisor will resume recovery on its next tick. Never commit this local sentinel.

## Updates and announcements

The supervisor sends an operational status update hourly to DISCORD_WEBHOOK_URL and sends changes/recovery results with a five-minute notification cooldown. It disables mention parsing in these messages. Missing credentials or failed delivery are not reported as successful sends.

The existing battlebot-proactive.timer runs the existing fighter-promotion and fight-summary announcer hourly, respecting its stored cooldown/deduplication state. The duplicate referee-proactive.timer was disabled. Keep only one announcer schedule active.

Set DISCORD_WEBHOOK_URL in the ignored .env file. Compose reads the value from the environment; do not embed webhooks or bot tokens in committed files. Notification state and runtime logs remain local.

## Validation and backups

The recovery implementation has six focused unit tests in tests/test_referee_supervisor.py. On September 21 a controlled stop of the mock-duel container was used to exercise recovery. Inspect the supervisor state and current Docker state to verify the outcome.

Before the operations deployment, current source, configuration, and profiles were archived under backups/operations-20260921/source-profiles-before.tgz. This archive is local and may contain credentials in the old Compose override; it must not be published. An older oversized harvester log is preserved separately in backups/log-recovery-20260921.

Source and selected fighter library/roster files belong in Git. Runtime harvest cursors, generated reports, historical review archives, caches, credentials, and backups do not need publication to deploy the application. Existing uncommitted files are preserved when excluded from a deployment commit.

The September 21 controlled recovery check succeeded: the supervisor restarted the manually stopped mock-duel service. All eight service states were running, the worker logged an idle repair pass without errors, and the web health endpoint responded. The first supervisor webhook returned success. Existing fight-quality review findings remain separate from this operational deployment.
