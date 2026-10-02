"""Standard-library tests; no provider credentials, Docker or network needed."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/install-server-proxy.py'
spec = importlib.util.spec_from_file_location('server_proxy', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def profile():
    return {'inbounds': [{'listen': '0.0.0.0', 'port': 1}], 'dns': {'servers': ['8.8.8.8']},
            'outbounds': [{'tag': 'proxy', 'protocol': 'vless', 'settings': {'vnext': [
                {'address': 'example.org', 'port': 8443, 'users': [
                    {'id': '00000000-0000-4000-8000-000000000001', 'encryption': 'none',
                     'flow': 'xtls-rprx-vision', 'level': 8}]}]},
                'streamSettings': {'network': 'tcp', 'security': 'tls', 'tlsSettings': {
                    'serverName': 'example.net', 'fingerprint': 'firefox', 'alpn': ['h2']}}},
                {'tag': 'direct', 'protocol': 'freedom'}]}


class ConfigurationTests(unittest.TestCase):
    def test_provider_fields_preserved_without_mutating_source(self):
        original = profile()
        before = copy.deepcopy(original)
        out = mod.build_config(original)['outbounds'][1]
        self.assertEqual(out['settings'], original['outbounds'][0]['settings'])
        self.assertEqual(out['streamSettings'], original['outbounds'][0]['streamSettings'])
        self.assertEqual(original, before)

    def test_private_listener_and_default_deny_only_telegram_443(self):
        result = mod.build_config(profile())
        self.assertEqual(len(result['inbounds']), 1)
        self.assertEqual(result['inbounds'][0]['listen'], '127.0.0.1')
        self.assertEqual(result['inbounds'][0]['port'], 18081)
        self.assertFalse(result['inbounds'][0]['settings']['udp'])
        self.assertEqual(result['outbounds'][0]['protocol'], 'blackhole')
        self.assertNotIn('freedom', [x['protocol'] for x in result['outbounds']])
        rule = result['routing']['rules'][0]
        self.assertEqual(rule['domain'], ['full:api.telegram.org'])
        self.assertEqual(rule['port'], '443')
        self.assertNotIn('dns', result)

    def test_insecure_tls_rejected(self):
        p = profile()
        p['outbounds'][0]['streamSettings']['tlsSettings']['allowInsecure'] = True
        with self.assertRaises(ValueError): mod.build_config(p)

    def test_unexpected_transport_rejected(self):
        for field, value in [('network', 'ws'), ('security', 'reality')]:
            p = profile()
            p['outbounds'][0]['streamSettings'][field] = value
            with self.assertRaises(ValueError): mod.build_config(p)

    def test_missing_or_ambiguous_profile_rejected(self):
        for p in [{}, {'outbounds': profile()['outbounds'] * 2}]:
            with self.assertRaises(ValueError): mod.build_config(p)

    def test_chained_proxy_rejected(self):
        p = profile()
        p['outbounds'][0]['proxySettings'] = {'tag': 'direct'}
        with self.assertRaises(ValueError): mod.build_config(p)

    def test_bad_identifier_not_echoed(self):
        p = profile()
        p['outbounds'][0]['settings']['vnext'][0]['users'][0]['id'] = 'PRIVATE_BAD_VALUE'
        with self.assertRaises(ValueError) as caught: mod.build_config(p)
        self.assertNotIn('PRIVATE_BAD_VALUE', str(caught.exception))

    def test_checksum_requires_exactly_one_matching_sha256(self):
        data = b'unit-test-binary'
        digest = hashlib.sha256(data).hexdigest()
        for label in ('SHA256', 'SHA2-256', 'SHA256 (Xray-linux-64.zip)'):
            mod.verify_digest(data, label + '= ' + digest)
        for bad in ['SHA256= ' + '0'*64, 'SHA512= ' + digest, '',
                    ('SHA256= ' + digest + '\n') * 2]:
            with self.assertRaises(ValueError): mod.verify_digest(data, bad)

    def test_private_atomic_write(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'config.json'
            mod.write_file(file, 'PRIVATE')
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(file.read_text(), 'PRIVATE')


class CutoverTests(unittest.TestCase):
    def test_worker_restarted_even_when_relay_probe_fails(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(mod, 'compose') as compose, \
                patch.object(mod, 'ctl'), patch.object(mod, 'probe', side_effect=RuntimeError('offline')), \
                patch.object(mod, 'DROP', Path(temp) / 'override.conf'):
            with self.assertRaises(RuntimeError): mod.switch_relay('new')
            self.assertEqual(compose.call_args_list[0].args, ('stop', '--timeout', '30', 'telegram-worker'))
            self.assertEqual(compose.call_args_list[-1].args, ('start', 'telegram-worker'))

    def test_rollback_restores_server_if_windows_verification_fails_after_switch(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'override.conf'
            file.write_text(mod.MARKER)
            with patch.object(mod, 'DROP', file), patch.object(mod, 'probe'), \
                    patch.object(mod, 'switch_relay', side_effect=RuntimeError('failed')), \
                    patch.object(mod, 'restore_relay') as restore, patch.object(mod, 'ctl') as ctl:
                with self.assertRaises(RuntimeError): mod.rollback()
                restore.assert_called_once_with(mod.MARKER.encode())
                ctl.assert_not_called()

    def test_rollback_does_not_switch_without_working_windows_proxy(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'override.conf'
            file.write_text(mod.MARKER)
            with patch.object(mod, 'DROP', file), patch.object(mod, 'probe', side_effect=RuntimeError('offline')), \
                    patch.object(mod, 'switch_relay') as switch:
                with self.assertRaises(RuntimeError): mod.rollback()
                switch.assert_not_called()

    def test_restore_attempts_worker_start_even_if_systemd_fails(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(mod, 'DROP', Path(temp)/'override.conf'), \
                patch.object(mod, 'ctl', side_effect=RuntimeError('systemd')), \
                patch.object(mod, 'compose') as compose:
            with self.assertRaisesRegex(RuntimeError, 'откат не завершён'): mod.restore_relay(None)
            compose.assert_called_once_with('start', 'telegram-worker')

    def test_install_failure_restores_preexisting_config(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            unit, config, drop, binary = (root / n for n in ('native.service', 'config.json', 'relay.conf', 'bin/xray'))
            config.write_text('old-private-config')
            unit.write_text(mod.MARKER)
            source = root / 'input.json'
            source.write_text(__import__('json').dumps(profile()))
            source.chmod(0o600)
            # First-stage failures must happen before any relay mutation.
            with patch.object(mod, 'CONFIG', config), patch.object(mod, 'UNIT', unit), \
                    patch.object(mod, 'DROP', drop), patch.object(mod, 'BIN', binary), \
                    patch.object(mod, 'relay_text', return_value='override'), \
                    patch.object(mod, 'ctl', return_value=subprocess.CompletedProcess([], 3)), \
                    patch.object(mod, 'get_binary', side_effect=RuntimeError('download failed')), \
                    patch.object(mod, 'switch_relay') as switch:
                with self.assertRaisesRegex(RuntimeError, 'download failed'): mod.install(source)
                switch.assert_not_called()
                self.assertEqual(config.read_text(), 'old-private-config')

    def test_failed_cutover_removes_dropin_and_restores_previous_files(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            unit, config, drop, binary = (root / n for n in ('native.service', 'config.json', 'relay.conf', 'bin/xray'))
            source, executable, relay = root/'input.json', root/'test-binary', root/'original-relay'
            source.write_text(__import__('json').dumps(profile()))
            source.chmod(0o600)
            executable.write_bytes(b'test')
            relay.write_text('Original Windows relay')
            config.write_text('Previous private config')
            unit.write_text(mod.MARKER)
            def fail_cutover(contents):
                drop.write_text(contents)
                raise RuntimeError('getMe unavailable')
            with patch.object(mod, 'CONFIG', config), patch.object(mod, 'UNIT', unit), \
                    patch.object(mod, 'DROP', drop), patch.object(mod, 'BIN', binary), \
                    patch.object(mod, 'BACKUPS', root), patch.object(mod, 'RELAY_FILE', relay), \
                    patch.object(mod, 'relay_text', return_value='override'), \
                    patch.object(mod, 'ctl', return_value=subprocess.CompletedProcess([], 3)), \
                    patch.object(mod, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                    patch.object(mod, 'get_binary', return_value=executable), \
                    patch.object(mod, 'wait_port'), patch.object(mod, 'probe'), \
                    patch.object(mod, 'compose') as compose, \
                    patch.object(mod, 'switch_relay', side_effect=fail_cutover):
                with self.assertRaisesRegex(RuntimeError, 'getMe unavailable'): mod.install(source)
                self.assertFalse(drop.exists())
                self.assertEqual(config.read_text(), 'Previous private config')
                self.assertEqual(unit.read_text(), mod.MARKER)
                compose.assert_called_with('start', 'telegram-worker')


if __name__ == '__main__':
    unittest.main()
