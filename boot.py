# boot.py -- run on boot-up
"""
The boot half of the over-the-air update; lib/ota.py is the other half.

lib/ota.py downloads a release into ota/new/, verifies it, writes the journal
ota/state.json with phase "staged" and resets. Then on each boot:

- staged:   move the current files to ota/old/, the new ones into place,
            start the trial.
- trial:    count the boot and arm the watchdog, so a build that crashes
            before main.py starts its own still resets. main.py confirms a
            build that works (lib/ota.py confirm() deletes the journal).
            After MAX_TRIAL_BOOTS unconfirmed boots it is rolled back.
- rollback: put ota/old/ back, delete files the update added, remember the
            version as bad so it is not installed again.

Every step is safe to repeat, so a power cut anywhere is finished on the next
boot. This file is not part of an update (tools/release.py): whatever an
update breaks, this still runs. Changing it needs a USB deploy.
"""

import os
import ujson

STATE = 'ota/state.json'
NEW = 'ota/new/'
OLD = 'ota/old/'
MAX_TRIAL_BOOTS = 3
# Long enough for main.py's imports; initialize() then reconfigures the
# watchdog to watchdog_timeout_ms (WDT() on ESP32 reconfigures the running one).
TRIAL_WDT_MS = 120000


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _mkdirs(path):
    """Create the parent directories of a file path."""
    parts = path.split('/')[:-1]
    for i in range(1, len(parts) + 1):
        d = '/'.join(parts[:i])
        if not _exists(d):
            os.mkdir(d)


def _save(state):
    with open(STATE + '.tmp', 'w') as f:
        ujson.dump(state, f)
    os.rename(STATE + '.tmp', STATE)


def _apply(files):
    for path, existed in files:
        if not _exists(NEW + path):
            continue  # moved into place by an earlier, interrupted boot
        if existed and _exists(path) and not _exists(OLD + path):
            _mkdirs(OLD + path)
            os.rename(path, OLD + path)
        _mkdirs(path)
        os.rename(NEW + path, path)


def _rollback(files):
    for path, existed in files:
        if not existed:
            if _exists(path):
                os.remove(path)
        elif _exists(OLD + path):
            os.rename(OLD + path, path)


def run():
    try:
        with open(STATE) as f:
            state = ujson.load(f)
    except (OSError, ValueError):
        return
    phase = state.get('phase')

    if phase == 'staged':
        print('ota: installing', state['version'])
        _apply(state['files'])
        phase = state['phase'] = 'trial'
        state['boots'] = 0

    if phase == 'trial':
        state['boots'] = state.get('boots', 0) + 1
        if state['boots'] > MAX_TRIAL_BOOTS:
            phase = state['phase'] = 'rollback'
        _save(state)

    if phase == 'rollback':
        print('ota: {} did not confirm itself, rolling back'.format(state['version']))
        _rollback(state['files'])
        _save({'bad': state['version']})
    elif phase == 'trial':
        print('ota: trial boot {}/{} of {}'.format(state['boots'], MAX_TRIAL_BOOTS, state['version']))
        from machine import WDT
        WDT(timeout=TRIAL_WDT_MS)


try:
    run()
except Exception as e:
    print('ota: boot step failed:', e)
