#!/usr/bin/env python3
"""Recover the persistent referee services and publish bounded operational updates."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

SERVICES = ('postgres', 'redis', 'litellm', 'bot', 'web', 'worker', 'harvester', 'mock-duels')


def recovery_action(state, last_attempt, now):
    if now - last_attempt < 300:
        return None
    if state is None:
        return 'create'
    if state.get('Status') in ('exited', 'created', 'dead'):
        return 'start'
    if state.get('Running') and state.get('Health', {}).get('Status') == 'unhealthy':
        return 'restart'
    return None


def inspect_service(service):
    result = subprocess.run(['docker', 'inspect', f'referee-{service}-1'],
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        # Distinguish a missing container from an unavailable daemon.
        subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'],
                       check=True, capture_output=True, timeout=15)
        return None
    return json.loads(result.stdout)[0]['State']


def recover(root, service, action):
    if action == 'create':
        cmd = ['docker', 'compose', '--profile', 'harvest', 'up', '-d',
               '--no-deps', '--no-build', '--pull', 'never', service]
    else:
        cmd = ['docker', action, f'referee-{service}-1']
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=25)
    # Do not echo compose output: a configuration error can include credentials.
    return result.returncode == 0


def notify(content):
    url = os.getenv('DISCORD_WEBHOOK_URL', '').strip()
    if not url:
        return False
    request = urllib.request.Request(url, data=json.dumps({
        'content': content[:1900], 'allowed_mentions': {'parse': []}
    }).encode(), headers={'Content-Type': 'application/json',
                         'User-Agent': 'NerdReferee-ServiceSupervisor/1.0'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return response.status in (200, 204)
    except Exception as exc:
        print(json.dumps({'notification_error': type(exc).__name__}), flush=True)
        return False


def check(root, state, *, dry_run=False):
    now = time.time()
    statuses, actions = {}, []
    attempts = state.setdefault('attempts', {})
    for service in SERVICES:
        observed = inspect_service(service)
        action = recovery_action(observed, attempts.get(service, 0), now)
        if action:
            success = None
            if not dry_run:
                attempts[service] = now
                success = recover(root, service, action)
                observed = inspect_service(service)
            actions.append({'service': service, 'action': action, 'success': success})
        statuses[service] = ((observed or {}).get('Status') or 'missing')
        if (observed or {}).get('Health', {}).get('Status') == 'unhealthy':
            statuses[service] = 'unhealthy'
    free_gb = round(shutil.disk_usage(root).free / 1024**3, 1)
    report = {'services': statuses, 'actions': actions, 'disk_free_gb': free_gb}
    print(json.dumps(report), flush=True)
    if dry_run:
        return report
    changed = statuses != state.get('notified_services')
    elapsed = now - state.get('last_notification', 0)
    if elapsed >= 3600 or ((changed or actions) and elapsed >= 300):
        running = sum(value == 'running' for value in statuses.values())
        message = (f'**Nerd Referee — service update**\n'
                   f'{running}/{len(SERVICES)} services running; {free_gb} GB disk space available.\n'
                   + ', '.join(f'{name}: {status}' for name, status in statuses.items()))
        if actions:
            message += '\nRecovery: ' + ', '.join(
                f"{item['service']} {item['action']} {'succeeded' if item['success'] else 'failed'}"
                for item in actions)
        if notify(message):
            state['last_notification'] = now
            state['notified_services'] = statuses
    state['last_check'] = now
    state['report'] = report
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/opt/referee')
    parser.add_argument('--state-dir', default='/var/lib/nerd-referee-supervisor')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    root = Path(args.root)
    if (root / '.maintenance').exists():
        print('Referee maintenance enabled: recovery and notifications paused.')
        return
    state_dir = Path(args.state_dir)
    state_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
    with (state_dir / 'supervisor.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        path = state_dir / 'state.json'
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
        except (ValueError, OSError):
            state = {}
        check(root, state, dry_run=args.dry_run)
        if not args.dry_run:
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(state, indent=2))
            temp.replace(path)


if __name__ == '__main__':
    main()
