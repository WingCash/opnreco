
from decimal import Decimal
from opnreport.testing import DBSessionFixture
import datetime
import os
import pyramid.testing
import responses
import unittest

zero = Decimal()


def setup_module():
    global dbsession_fixture
    dbsession_fixture = DBSessionFixture()


def teardown_module():
    dbsession_fixture.close()


class TestDownloadView(unittest.TestCase):

    def setUp(self):
        os.environ['opn_api_url'] = 'https://opn.example.com:9999'
        self.config = pyramid.testing.setUp()
        self.dbsession, self.close_session = dbsession_fixture.begin_session()

    def tearDown(self):
        self.close_session()
        pyramid.testing.tearDown()

    @property
    def _class(self):
        from ..syncview import SyncView
        return SyncView

    def _make(self, profile_id='11'):
        from opnreport.models.db import Profile

        profile = Profile(
            id=profile_id,
            title="Test Profile",
        )
        self.dbsession.add(profile)
        self.dbsession.flush()

        request = pyramid.testing.DummyRequest(
            dbsession=self.dbsession,
            profile=profile,
            access_token='example-token',
            remote_addr='127.0.0.1',
            user_agent='Test UA',
            wallet_info={'profile': {'accounts': [{
                'id': '1102',
                'redacted_account_num': 'XXX45',
                'rdfi_name': "Test Bank",
                'alias': 'myacct',
            }]}},
        )
        return self._class(request)

    @responses.activate
    def test_with_no_transfers(self):
        from opnreport.models import db

        responses.add(
            responses.POST,
            'https://opn.example.com:9999/wallet/history_sync',
            json={
                'results': [],
                'more': False,
                'first_sync_ts': None,
                'last_sync_ts': None,
            })
        obj = self._make()
        obj()

        downloads = self.dbsession.query(db.OPNDownload).all()
        self.assertEqual(1, len(downloads))
        self.assertEqual('11', downloads[0].profile_id)

        events = self.dbsession.query(db.ProfileLog).all()
        self.assertEqual(1, len(events))
        self.assertEqual('11', events[0].profile_id)

        records = self.dbsession.query(db.TransferRecord).all()
        self.assertEqual(0, len(records))

    @responses.activate
    def test_redeem_from_sender_perspective(self):
        from opnreport.models import db

        responses.add(
            responses.POST,
            'https://opn.example.com:9999/wallet/history_sync',
            json={
                'results': [{
                    'id': '500',
                    'workflow_type': 'redeem',
                    'start': '2018-08-01T04:05:06Z',
                    'timestamp': '2018-08-01T04:05:08Z',
                    'next_activity': 'completed',
                    'completed': True,
                    'canceled': False,
                    'sender_id': '11',
                    'sender_uid': 'wingcash:11',
                    'sender_info': {
                        'title': "Tester",
                    },
                    'recipient_id': '1102',
                    'recipient_uid': 'wingcash:1102',
                    'recipient_info': {
                        'title': "Acct",
                    },
                    'movements': [{
                        'number': 2,
                        'timestamp': '2018-01-02T05:06:07Z',
                        'action': 'deposit',
                        'from_id': '11',
                        'to_id': '1102',
                        'loops': [
                            {
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '1.00',
                                'issuer_id': '19',
                            },
                            {
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '0.25',
                                'issuer_id': '20',
                            },
                        ],
                    }],
                }],
                'more': False,
                'first_sync_ts': '2018-08-01T04:05:10Z',
                'last_sync_ts': '2018-08-01T04:05:11Z',
            })

        responses.add(
            responses.GET,
            'https://opn.example.com:9999/p/19',
            json={'title': "Super Bank"})

        responses.add(
            responses.GET,
            'https://opn.example.com:9999/p/1102',
            json={'title': "Tester's Super Bank Checking Account"})

        obj = self._make()
        obj()

        downloads = self.dbsession.query(db.OPNDownload).all()
        self.assertEqual(1, len(downloads))
        self.assertEqual('11', downloads[0].profile_id)

        events = self.dbsession.query(db.ProfileLog).all()
        self.assertEqual([
            'opn_sync',
            'add_mirror',
            'add_mirror',
            'update_mirror_target_title',
            'update_mirror_target_title',
            'update_mirror_target_is_dfi_account',
        ], [e.event_type for e in events])
        event = events[0]
        self.assertEqual('11', event.profile_id)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        records = self.dbsession.query(db.TransferRecord).all()
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual('redeem', record.workflow_type)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 6), record.start)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 8), record.timestamp)
        self.assertEqual(True, record.completed)
        self.assertEqual(False, record.canceled)
        self.assertEqual('11', record.sender_id)
        self.assertEqual('wingcash:11', record.sender_uid)
        self.assertEqual('Tester', record.sender_title)
        self.assertEqual('1102', record.recipient_id)
        self.assertEqual('wingcash:1102', record.recipient_uid)
        self.assertEqual('Acct', record.recipient_title)

        mirrors = (
            self.dbsession.query(db.Mirror)
            .order_by(db.Mirror.target_id).all())
        self.assertEqual(2, len(mirrors))
        mirror = mirrors[0]
        self.assertEqual('11', mirror.profile_id)
        self.assertEqual('1102', mirror.target_id)
        self.assertEqual('0', mirror.loop_id)
        self.assertEqual('USD', mirror.currency)
        self.assertEqual('XXX45 at Test Bank (myacct)', mirror.target_title)
        self.assertEqual(None, mirror.loop_title)

        movements = (
            self.dbsession.query(db.Movement)
            .filter_by(mirror_id=mirror.id).all())
        self.assertEqual(1, len(movements))
        m = movements[0]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(2, m.number)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(datetime.datetime(2018, 1, 2, 5, 6, 7), m.ts)
        self.assertEqual(Decimal('-1.25'), m.wallet_delta)

        events = self.dbsession.query(db.MovementLog).all()
        self.assertEqual(2, len(events))
        event = events[0]
        self.assertEqual('download', event.event_type)

        recos = self.dbsession.query(db.Reco).all()
        self.assertEqual(0, len(recos))

    @responses.activate
    def test_redeem_from_issuer_perspective(self):
        from opnreport.models import db

        responses.add(
            responses.POST,
            'https://opn.example.com:9999/wallet/history_sync',
            json={
                'results': [{
                    'id': '500',
                    'workflow_type': 'redeem',
                    'start': '2018-08-01T04:05:06Z',
                    'timestamp': '2018-08-01T04:05:08Z',
                    'next_activity': 'completed',
                    'completed': True,
                    'canceled': False,
                    'sender_id': '11',
                    'sender_uid': 'wingcash:11',
                    'sender_info': {
                        'title': "Tester",
                    },
                    'recipient_id': '1102',
                    'recipient_uid': 'wingcash:1102',
                    'recipient_info': {
                        'title': "Acct",
                    },
                    'movements': [{
                        'number': 1,
                        'timestamp': '2018-08-02T05:06:07Z',
                        'action': 'deposit',
                        'from_id': '1102',
                        'to_id': '19',
                        'loops': [{
                            'currency': 'USD',
                            'loop_id': '0',
                            'amount': '1.00',
                            'issuer_id': '19',
                        }],
                    }],
                }],
                'more': False,
                'first_sync_ts': '2018-08-01T04:05:10Z',
                'last_sync_ts': '2018-08-01T04:05:11Z',
            })
        obj = self._make(profile_id='19')
        obj()

        downloads = self.dbsession.query(db.OPNDownload).all()
        self.assertEqual(1, len(downloads))
        self.assertEqual('19', downloads[0].profile_id)

        events = self.dbsession.query(db.ProfileLog).all()
        self.assertEqual(3, len(events))
        event = events[0]
        self.assertEqual('19', event.profile_id)
        self.assertEqual('opn_sync', event.event_type)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        records = self.dbsession.query(db.TransferRecord).all()
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual('redeem', record.workflow_type)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 6), record.start)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 8), record.timestamp)
        self.assertEqual(True, record.completed)
        self.assertEqual(False, record.canceled)
        self.assertEqual('11', record.sender_id)
        self.assertEqual('wingcash:11', record.sender_uid)
        self.assertEqual('Tester', record.sender_title)
        self.assertEqual('1102', record.recipient_id)
        self.assertEqual('wingcash:1102', record.recipient_uid)
        self.assertEqual('Acct', record.recipient_title)

        mirrors = self.dbsession.query(db.Mirror).all()
        self.assertEqual(1, len(mirrors))
        mirror = mirrors[0]
        self.assertEqual('19', mirror.profile_id)
        self.assertEqual('c', mirror.target_id)
        self.assertEqual('0', mirror.loop_id)
        self.assertEqual('USD', mirror.currency)
        self.assertEqual('Test Profile', mirror.target_title)
        self.assertEqual(None, mirror.loop_title)

        movements = self.dbsession.query(db.Movement).all()
        self.assertEqual(1, len(movements))
        m = movements[0]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('1.00'), m.vault_delta)

        events = self.dbsession.query(db.MovementLog).all()
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertEqual('download', event.event_type)

        recos = self.dbsession.query(db.Reco).all()
        self.assertEqual(0, len(recos))

    @responses.activate
    def test_grant_from_recipient_perspective(self):
        from opnreport.models import db

        responses.add(
            responses.POST,
            'https://opn.example.com:9999/wallet/history_sync',
            json={
                'results': [{
                    'id': '501',
                    'workflow_type': 'grant',
                    'start': '2018-08-01T04:05:06Z',
                    'timestamp': '2018-08-01T04:05:08Z',
                    'next_activity': 'completed',
                    'completed': True,
                    'canceled': False,
                    'sender_id': '19',
                    'sender_uid': 'wingcash:19',
                    'sender_info': {
                        'title': "Issuer",
                    },
                    'recipient_id': '11',
                    'recipient_uid': 'wingcash:11',
                    'recipient_info': {
                        'title': "Some Tester",
                    },
                    'movements': [
                        {
                            # Issued $1.00
                            'number': 2,
                            'timestamp': '2018-08-02T05:06:07Z',
                            'action': 'grant',
                            'from_id': '19',
                            'to_id': '11',
                            'loops': [{
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '1.00',
                                'issuer_id': '19',
                            }],
                        }, {
                            # Issued $0.25
                            'number': 3,
                            'timestamp': '2018-08-02T05:06:09Z',
                            'action': 'grant',
                            'from_id': '19',
                            'to_id': '11',
                            'loops': [{
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '0.25',
                                'issuer_id': '19',
                            }],
                        },
                    ],
                }],
                'more': False,
                'first_sync_ts': '2018-08-01T04:05:10Z',
                'last_sync_ts': '2018-08-01T04:05:11Z',
            })

        responses.add(
            responses.GET,
            'https://opn.example.com:9999/p/19',
            json={'title': "Super Bank"})

        responses.add(
            responses.GET,
            'https://opn.example.com:9999/p/1102',
            json={'title': "Tester's Super Bank Checking Account"})

        obj = self._make(profile_id='11')
        obj()

        downloads = self.dbsession.query(db.OPNDownload).all()
        self.assertEqual(1, len(downloads))
        self.assertEqual('11', downloads[0].profile_id)

        events = self.dbsession.query(db.ProfileLog).all()
        self.assertEqual([
            'opn_sync',
            'add_mirror',
            'add_mirror',
            'update_mirror_target_title',
            'update_mirror_target_title',
        ], [e.event_type for e in events])
        event = events[0]
        self.assertEqual('11', event.profile_id)
        self.assertEqual('opn_sync', event.event_type)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        records = self.dbsession.query(db.TransferRecord).all()
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual('grant', record.workflow_type)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 6), record.start)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 8), record.timestamp)
        self.assertEqual(True, record.completed)
        self.assertEqual(False, record.canceled)
        self.assertEqual('19', record.sender_id)
        self.assertEqual('wingcash:19', record.sender_uid)
        self.assertEqual('Issuer', record.sender_title)
        self.assertEqual('11', record.recipient_id)
        self.assertEqual('wingcash:11', record.recipient_uid)
        self.assertEqual('Some Tester', record.recipient_title)

        mirrors = (
            self.dbsession.query(db.Mirror)
            .order_by(db.Mirror.target_id).all())
        self.assertEqual(2, len(mirrors))
        mirror = mirrors[0]
        self.assertEqual('11', mirror.profile_id)
        self.assertEqual('19', mirror.target_id)
        self.assertEqual('0', mirror.loop_id)
        self.assertEqual('USD', mirror.currency)

        movements = (
            self.dbsession.query(db.Movement)
            .filter_by(mirror_id=mirror.id)
            .order_by(db.Movement.number)
            .all())
        self.assertEqual(2, len(movements))
        m = movements[0]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('1.00'), m.wallet_delta)

        m = movements[1]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('0.25'), m.wallet_delta)

        events = self.dbsession.query(db.MovementLog).all()
        self.assertEqual(4, len(events))
        event = events[0]
        self.assertEqual('download', event.event_type)

    @responses.activate
    def test_grant_from_issuer_perspective(self):
        from opnreport.models import db

        responses.add(
            responses.POST,
            'https://opn.example.com:9999/wallet/history_sync',
            json={
                'results': [{
                    'id': '501',
                    'workflow_type': 'grant',
                    'start': '2018-08-01T04:05:06Z',
                    'timestamp': '2018-08-01T04:05:08Z',
                    'next_activity': 'completed',
                    'completed': True,
                    'canceled': False,
                    'sender_id': '19',
                    'sender_uid': 'wingcash:19',
                    'sender_info': {
                        'title': "Issuer",
                    },
                    'recipient_id': '11',
                    'recipient_uid': 'wingcash:11',
                    'recipient_info': {
                        'title': "Some Tester",
                    },
                    'movements': [
                        {
                            # Issuance movement to ignore
                            'number': 1,
                            'timestamp': '2018-08-02T05:06:06Z',
                            'action': 'issue',
                            'from_id': None,
                            'to_id': '19',
                            'loops': [{
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '1.25',
                                'issuer_id': '19',
                            }],
                        }, {
                            # Issued $1.00
                            'number': 2,
                            'timestamp': '2018-08-02T05:06:07Z',
                            'action': 'grant',
                            'from_id': '19',
                            'to_id': '11',
                            'loops': [{
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '1.00',
                                'issuer_id': '19',
                            }],
                        }, {
                            # Issued $0.25
                            'number': 3,
                            'timestamp': '2018-08-02T05:06:07Z',
                            'action': 'grant',
                            'from_id': '19',
                            'to_id': '11',
                            'loops': [{
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '0.25',
                                'issuer_id': '19',
                            }],
                        },
                    ],
                }],
                'more': False,
                'first_sync_ts': '2018-08-01T04:05:10Z',
                'last_sync_ts': '2018-08-01T04:05:11Z',
            })
        obj = self._make(profile_id='19')
        obj()

        downloads = self.dbsession.query(db.OPNDownload).all()
        self.assertEqual(1, len(downloads))
        self.assertEqual('19', downloads[0].profile_id)

        events = self.dbsession.query(db.ProfileLog).all()
        self.assertEqual(3, len(events))
        event = events[0]
        self.assertEqual('19', event.profile_id)
        self.assertEqual('opn_sync', event.event_type)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        records = self.dbsession.query(db.TransferRecord).all()
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual('grant', record.workflow_type)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 6), record.start)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 8), record.timestamp)
        self.assertEqual(True, record.completed)
        self.assertEqual(False, record.canceled)
        self.assertEqual('19', record.sender_id)
        self.assertEqual('wingcash:19', record.sender_uid)
        self.assertEqual('Issuer', record.sender_title)
        self.assertEqual('11', record.recipient_id)
        self.assertEqual('wingcash:11', record.recipient_uid)
        self.assertEqual('Some Tester', record.recipient_title)

        mirrors = self.dbsession.query(db.Mirror).all()
        self.assertEqual(1, len(mirrors))
        mirror = mirrors[0]
        self.assertEqual('19', mirror.profile_id)
        self.assertEqual('c', mirror.target_id)
        self.assertEqual('0', mirror.loop_id)
        self.assertEqual('USD', mirror.currency)

        movements = (
            self.dbsession.query(db.Movement)
            .order_by(db.Movement.number)
            .all())
        self.assertEqual(2, len(movements))
        m = movements[0]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('-1.00'), m.vault_delta)
        self.assertEqual(zero, m.wallet_delta)

        m = movements[1]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('-0.25'), m.vault_delta)
        self.assertEqual(zero, m.wallet_delta)

        events = self.dbsession.query(db.MovementLog).all()
        self.assertEqual(2, len(events))
        event = events[0]
        self.assertEqual('download', event.event_type)

    @responses.activate
    def test_p2p_with_exchange_from_issuer_perspective(self):
        from opnreport.models import db

        responses.add(
            responses.POST,
            'https://opn.example.com:9999/wallet/history_sync',
            json={
                'results': [{
                    'id': '501',
                    'workflow_type': 'profile_to_profile',
                    'start': '2018-08-01T04:05:06Z',
                    'timestamp': '2018-08-01T04:05:08Z',
                    'next_activity': 'completed',
                    'completed': True,
                    'canceled': False,
                    'sender_id': '11',
                    'sender_uid': 'wingcash:11',
                    'sender_info': {
                        'title': "Testy User",
                    },
                    'recipient_id': '12',
                    'recipient_uid': 'wingcash:12',
                    'recipient_info': {
                        'title': "Friend",
                    },
                    'movements': [
                        {
                            # Replaced $0.30 from multiple issuers
                            'number': 1,
                            'timestamp': '2018-08-02T05:06:07Z',
                            'action': 'split',
                            'from_id': '11',
                            'to_id': '19',
                            'loops': [{
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '.20',
                                'issuer_id': '19',
                            }, {
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '.10',
                                'issuer_id': '21',
                            }],
                        }, {
                            # Replaced with $0.25 + $0.05 from 1 issuer
                            'number': 2,
                            'timestamp': '2018-08-02T05:06:07Z',
                            'action': 'split',
                            'from_id': '19',
                            'to_id': '11',
                            'loops': [{
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '0.30',
                                'issuer_id': '19',
                            }],
                        }, {
                            # Send $0.25, profile to profile
                            'number': 3,
                            'timestamp': '2018-08-02T05:06:07Z',
                            'action': 'move',
                            'from_id': '11',
                            'to_id': '12',
                            'loops': [{
                                'currency': 'USD',
                                'loop_id': '0',
                                'amount': '0.25',
                                'issuer_id': '19',
                            }],
                        },
                    ],
                }],
                'more': False,
                'first_sync_ts': '2018-08-01T04:05:10Z',
                'last_sync_ts': '2018-08-01T04:05:11Z',
            })
        obj = self._make(profile_id='19')
        obj()

        downloads = self.dbsession.query(db.OPNDownload).all()
        self.assertEqual(1, len(downloads))
        self.assertEqual('19', downloads[0].profile_id)

        events = self.dbsession.query(db.ProfileLog).all()
        self.assertEqual([
            'opn_sync',
            'add_mirror',
            'add_mirror',
            'update_mirror_target_title',
            'update_mirror_target_title',
        ], [e.event_type for e in events])
        event = events[0]
        self.assertEqual('19', event.profile_id)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        records = self.dbsession.query(db.TransferRecord).all()
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual('profile_to_profile', record.workflow_type)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 6), record.start)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 8), record.timestamp)
        self.assertEqual(True, record.completed)
        self.assertEqual(False, record.canceled)
        self.assertEqual('11', record.sender_id)
        self.assertEqual('wingcash:11', record.sender_uid)
        self.assertEqual('Testy User', record.sender_title)
        self.assertEqual('12', record.recipient_id)
        self.assertEqual('wingcash:12', record.recipient_uid)
        self.assertEqual('Friend', record.recipient_title)

        mirrors = (
            self.dbsession.query(db.Mirror)
            .order_by(db.Mirror.target_id)
            .all())
        self.assertEqual(2, len(mirrors))
        mirror = mirrors[1]
        self.assertEqual('19', mirror.profile_id)
        self.assertEqual('c', mirror.target_id)
        self.assertEqual('0', mirror.loop_id)
        self.assertEqual('USD', mirror.currency)

        movements = (
            self.dbsession.query(db.Movement)
            .filter(db.Movement.mirror_id == mirror.id)
            .order_by(db.Movement.number)
            .all())
        self.assertEqual(2, len(movements))
        m = movements[0]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('0.20'), m.vault_delta)
        self.assertEqual(Decimal('0.10'), m.wallet_delta)

        m = movements[1]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('-0.30'), m.vault_delta)
        self.assertEqual(zero, m.wallet_delta)

        reco_ids = dict(  # {movement_id: reco_id}
            self.dbsession.query(
                db.MovementReco.movement_id,
                db.MovementReco.reco_id)
            .all())
        self.assertEqual(2, len(reco_ids))

        exchanges = (
            self.dbsession.query(db.Exchange)
            .all())
        self.assertEqual(1, len(exchanges))
        exchange = exchanges[0]
        self.assertEqual(mirror.id, exchange.mirror_id)
        self.assertEqual(Decimal('-0.10'), exchange.wallet_delta)
        self.assertEqual(Decimal('0.10'), exchange.vault_delta)
        self.assertEqual(reco_ids[movements[1].id], exchange.origin_reco_id)

        self.assertEqual(
            zero, sum(row.wallet_delta for row in movements + exchanges))
        self.assertEqual(
            zero, sum(row.vault_delta for row in movements + exchanges))

        events = self.dbsession.query(db.MovementLog).all()
        self.assertEqual(5, len(events))
        event = events[0]
        self.assertEqual('download', event.event_type)

    def test_redownload_with_updates(self):
        from opnreport.models import db

        def _make_transfer_result():
            return {
                'id': '500',
                'workflow_type': 'redeem',
                'start': '2018-08-01T04:05:06Z',
                'timestamp': '2018-08-01T04:05:08Z',
                'next_activity': 'someactivity',
                'completed': False,
                'canceled': False,
                'sender_id': '11',
                'sender_uid': 'wingcash:11',
                'sender_info': {
                    'title': "Tester",
                },
                'recipient_id': '1102',
                'recipient_uid': 'wingcash:1102',
                'recipient_info': {
                    'title': "Acct",
                },
                # No movements yet.
                'movements': [],
            }

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [_make_transfer_result()],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            obj = self._make(profile_id='19')
            obj()

        downloads = self.dbsession.query(db.OPNDownload).all()
        self.assertEqual(1, len(downloads))
        self.assertEqual('19', downloads[0].profile_id)

        events = self.dbsession.query(db.ProfileLog).all()
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertEqual('19', event.profile_id)
        self.assertEqual('opn_sync', event.event_type)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        records = self.dbsession.query(db.TransferRecord).all()
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual('redeem', record.workflow_type)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 6), record.start)
        self.assertEqual(
            datetime.datetime(2018, 8, 1, 4, 5, 8), record.timestamp)
        self.assertEqual(False, record.completed)
        self.assertEqual(False, record.canceled)
        self.assertEqual('11', record.sender_id)
        self.assertEqual('wingcash:11', record.sender_uid)
        self.assertEqual('Tester', record.sender_title)
        self.assertEqual('1102', record.recipient_id)
        self.assertEqual('wingcash:1102', record.recipient_uid)
        self.assertEqual('Acct', record.recipient_title)

        mirrors = self.dbsession.query(db.Mirror).all()
        self.assertEqual(0, len(mirrors))

        ms = self.dbsession.query(db.Movement).all()
        self.assertEqual(0, len(ms))

        recos = self.dbsession.query(db.Reco).all()
        self.assertEqual(0, len(recos))

        # Simulate the transfer completing the return of the cash
        # to the issuer and re-download.
        result1 = _make_transfer_result()
        result1['movements'] = [{
            'number': 1,
            'timestamp': '2018-08-02T05:06:06Z',
            'action': 'redeem',
            'from_id': '1102',
            'to_id': '19',
            'loops': [{
                'currency': 'USD',
                'loop_id': '0',
                'amount': '1.00',
                'issuer_id': '19',
            }],
        }]

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [result1],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            obj()

        events = (
            self.dbsession.query(db.ProfileLog)
            .order_by(db.ProfileLog.id).all())
        self.assertEqual(4, len(events))
        event = events[1]
        self.assertEqual('19', event.profile_id)
        self.assertEqual('opn_sync', event.event_type)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        records = self.dbsession.query(db.TransferRecord).all()
        self.assertEqual(1, len(records))
        self.assertFalse(records[0].canceled)

        mirrors = self.dbsession.query(db.Mirror).all()
        self.assertEqual(1, len(mirrors))
        mirror = mirrors[0]
        self.assertEqual('19', mirror.profile_id)
        self.assertEqual('c', mirror.target_id)
        self.assertEqual('0', mirror.loop_id)
        self.assertEqual('USD', mirror.currency)

        movements = (
            self.dbsession.query(db.Movement)
            .order_by(db.Movement.number)
            .all())
        self.assertEqual(1, len(movements))
        m = movements[0]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('1.00'), m.vault_delta)

        # Simulate a failed redemption: the issuer re-issues cash to
        # the profile. Re-download.
        result1 = _make_transfer_result()
        result1['canceled'] = True
        result1['next_activity'] = 'canceled'
        result1['movements'] = [
            # The redeem movement remains.
            {
                'number': 1,
                'timestamp': '2018-08-02T05:06:06Z',
                'action': 'redeem',
                'from_id': '1102',
                'to_id': '19',
                'loops': [{
                    'currency': 'USD',
                    'loop_id': '0',
                    'amount': '1.00',
                    'issuer_id': '19',
                }],
            },
            # The refund movement offsets the original movement.
            {
                'number': 2,
                'timestamp': '2018-08-02T05:06:07Z',
                'action': 'refund',
                'from_id': '19',
                'to_id': '1102',
                'loops': [{
                    'currency': 'USD',
                    'loop_id': '0',
                    'amount': '1.00',
                    'issuer_id': '19',
                }],
            },
        ]

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [result1],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            obj()

        events = (
            self.dbsession.query(db.ProfileLog)
            .order_by(db.ProfileLog.id).all())
        self.assertEqual(5, len(events))
        event = events[-1]
        self.assertEqual('19', event.profile_id)
        self.assertEqual('opn_sync', event.event_type)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        records = self.dbsession.query(db.TransferRecord).all()
        self.assertEqual(1, len(records))
        self.assertTrue(records[0].canceled)

        mirrors = self.dbsession.query(db.Mirror).all()
        self.assertEqual(1, len(mirrors))
        mirror = mirrors[0]
        self.assertEqual('19', mirror.profile_id)
        self.assertEqual('c', mirror.target_id)
        self.assertEqual('0', mirror.loop_id)
        self.assertEqual('USD', mirror.currency)

        movements = (
            self.dbsession.query(db.Movement)
            .order_by(db.Movement.number)
            .all())
        self.assertEqual(2, len(movements))
        m = movements[0]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('1.00'), m.vault_delta)

        m = movements[1]
        self.assertEqual(record.id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('-1.00'), m.vault_delta)

    def test_redownload_with_no_movements_and_no_updates(self):
        from opnreport.models import db

        def _make_transfer_result():
            return {
                'id': '500',
                'workflow_type': 'redeem',
                'start': '2018-08-01T04:05:06Z',
                'timestamp': '2018-08-01T04:05:08Z',
                'next_activity': 'send_to_dfi',
                'completed': False,
                'canceled': False,
                'sender_id': '11',
                'sender_uid': 'wingcash:11',
                'sender_info': {
                    'title': "Tester",
                },
                'recipient_id': '1102',
                'recipient_uid': 'wingcash:1102',
                'recipient_info': {
                    'title': "Acct",
                },
                # No movements yet.
                'movements': [],
            }

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [_make_transfer_result()],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            obj = self._make(profile_id='19')
            obj()

        mirrors = self.dbsession.query(db.Mirror).all()
        self.assertEqual(0, len(mirrors))

        movements = (
            self.dbsession.query(db.Movement)
            .order_by(db.Movement.number)
            .all())
        self.assertEqual(0, len(movements))

        result1 = _make_transfer_result()

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [result1],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            obj()

        movements = (
            self.dbsession.query(db.Movement)
            .order_by(db.Movement.number)
            .all())
        self.assertEqual(0, len(movements))

    def test_redownload_with_movements_but_no_updates(self):
        from opnreport.models import db

        def _make_transfer_result():
            return {
                'id': '500',
                'workflow_type': 'redeem',
                'start': '2018-08-01T04:05:06Z',
                'timestamp': '2018-08-01T04:05:08Z',
                'next_activity': 'send_to_dfi',
                'completed': False,
                'canceled': False,
                'sender_id': '11',
                'sender_uid': 'wingcash:11',
                'sender_info': {
                    'title': "Tester",
                },
                'recipient_id': '1102',
                'recipient_uid': 'wingcash:1102',
                'recipient_info': {
                    'title': "Acct",
                },
                'movements': [
                    {
                        'number': 1,
                        'timestamp': '2018-08-02T05:06:06Z',
                        'action': 'redeem',
                        'from_id': '1102',
                        'to_id': '19',
                        'loops': [{
                            'currency': 'USD',
                            'loop_id': '0',
                            'amount': '1.00',
                            'issuer_id': '19',
                        }],
                    },
                ],
            }

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [_make_transfer_result()],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            obj = self._make(profile_id='19')
            obj()

        mirrors = self.dbsession.query(db.Mirror).all()
        self.assertEqual(1, len(mirrors))
        mirror = mirrors[0]
        self.assertEqual('19', mirror.profile_id)
        self.assertEqual('c', mirror.target_id)
        self.assertEqual('0', mirror.loop_id)
        self.assertEqual('USD', mirror.currency)

        movements = (
            self.dbsession.query(db.Movement)
            .order_by(db.Movement.number)
            .all())
        self.assertEqual(1, len(movements))
        m = movements[0]
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('1.00'), m.vault_delta)

        result1 = _make_transfer_result()

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [result1],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            obj()

        mss = self.dbsession.query(db.Movement).all()
        self.assertEqual(1, len(mss))

    def test_sync_error(self):
        from opnreport.views.syncview import SyncError

        def _make_transfer_result():
            return {
                'id': '500',
                'workflow_type': 'redeem',
                'start': '2018-08-01T04:05:06Z',
                'timestamp': '2018-08-01T04:05:08Z',
                'next_activity': 'send_to_dfi',
                'completed': False,
                'canceled': False,
                'sender_id': '11',
                'sender_uid': 'wingcash:11',
                'sender_info': {
                    'title': "Tester",
                },
                'recipient_id': '1102',
                'recipient_uid': 'wingcash:1102',
                'recipient_info': {
                    'title': "Acct",
                },
                'movements': [
                    {
                        'number': 1,
                        'timestamp': '2018-08-02T05:06:06Z',
                        'action': 'redeem',
                        'from_id': '1102',
                        'to_id': '19',
                        'loops': [{
                            'currency': 'USD',
                            'loop_id': '0',
                            'amount': '1.00',
                            'issuer_id': '19',
                        }],
                    },
                ],
            }

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [_make_transfer_result()],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            obj = self._make(profile_id='19')
            obj()

        result1 = _make_transfer_result()
        result1['workflow_type'] = 'raspberry'

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [result1],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            with self.assertRaisesRegexp(
                    SyncError, r'Immutable attribute changed'):
                obj()

    def test_download_batches(self):
        from opnreport.models import db

        def _make_transfer_result():
            return {
                'id': '501',
                'workflow_type': 'grant',
                'start': '2018-08-01T04:05:06Z',
                'timestamp': '2018-08-01T04:05:08Z',
                'next_activity': 'someactivity',
                'completed': False,
                'canceled': False,
                'sender_id': '19',
                'sender_uid': 'wingcash:19',
                'sender_info': {
                    'title': "Issuer",
                },
                'recipient_id': '11',
                'recipient_uid': 'wingcash:11',
                'recipient_info': {
                    'title': "Tester",
                },
                'movements': [
                    {
                        'number': 1,
                        'timestamp': '2018-08-02T05:06:06Z',
                        'action': 'redeem',
                        'from_id': '19',
                        'to_id': '11',
                        'loops': [{
                            'currency': 'USD',
                            'loop_id': '0',
                            'amount': '1.00',
                            'issuer_id': '19',
                        }],
                    },
                ],
            }

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [_make_transfer_result()],
                    'more': True,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                    'remain': 1,
                })

            obj = self._make(profile_id='11')
            download_status = obj()
            self.assertGreaterEqual(download_status['progress_percent'], 0.0)
            self.assertLessEqual(download_status['progress_percent'], 100.0)
            self.assertEqual({
                'count': 1,
                'more': True,
                'progress_percent': 50,
                'last_sync_ts': '2018-08-01T04:05:11Z',
            }, download_status)

        downloads = self.dbsession.query(db.OPNDownload).all()
        self.assertEqual(1, len(downloads))
        self.assertEqual('11', downloads[0].profile_id)

        events = self.dbsession.query(db.ProfileLog).all()
        self.assertEqual([
            'opn_sync',
            'add_mirror',
            'add_mirror',
            'update_mirror_target_title',
            'update_mirror_target_title',
        ], [e.event_type for e in events])

        event = events[0]
        self.assertEqual('11', event.profile_id)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        mirror = (
            self.dbsession.query(db.Mirror).filter_by(
                target_id='19').one())

        mss = (
            self.dbsession.query(db.Movement)
            .filter_by(mirror_id=mirror.id)
            .all())
        self.assertEqual(1, len(mss))

        mvlog_entries = (
            self.dbsession.query(db.MovementLog)
            .filter_by(movement_id=mss[0].id)
            .all())
        self.assertEqual(1, len(mvlog_entries))

        # Download the last batch.

        with responses.RequestsMock() as rsps:
            transfer_result = _make_transfer_result()
            transfer_result['id'] = '502'
            rsps.add(
                responses.POST,
                'https://opn.example.com:9999/wallet/history_sync',
                json={
                    'results': [transfer_result],
                    'more': False,
                    'first_sync_ts': '2018-08-01T04:05:10Z',
                    'last_sync_ts': '2018-08-01T04:05:11Z',
                })
            download_status = obj()
            self.assertEqual({
                'count': 1,
                'more': False,
                'progress_percent': 100.0,
                'last_sync_ts': '2018-08-01T04:05:11Z',
            }, download_status)

        events = (
            self.dbsession.query(db.ProfileLog)
            .order_by(db.ProfileLog.id).all())
        self.assertEqual([
            'opn_sync',
            'add_mirror',
            'add_mirror',
            'update_mirror_target_title',
            'update_mirror_target_title',
            'opn_sync',
        ], [e.event_type for e in events])
        event = events[-1]
        self.assertEqual('11', event.profile_id)
        self.assertEqual(
            {'sync_ts', 'progress_percent', 'transfers'},
            set(event.memo.keys()))

        records = (
            self.dbsession.query(db.TransferRecord)
            .order_by(db.TransferRecord.id).all())
        self.assertEqual(2, len(records))
        record = records[-1]
        self.assertFalse(record.canceled)
        self.assertEqual('502', record.transfer_id)

        mirrors = (
            self.dbsession.query(db.Mirror)
            .order_by(db.Mirror.target_id).all())
        self.assertEqual(2, len(mirrors))
        mirror = mirrors[0]
        self.assertEqual('11', mirror.profile_id)
        self.assertEqual('19', mirror.target_id)
        self.assertEqual('0', mirror.loop_id)
        self.assertEqual('USD', mirror.currency)

        movements = (
            self.dbsession.query(db.Movement)
            .filter_by(mirror_id=mirror.id)
            .order_by(db.Movement.number)
            .all())
        self.assertEqual(2, len(movements))
        m = movements[0]
        self.assertEqual(records[0].id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('1.00'), m.wallet_delta)

        m = movements[1]
        self.assertEqual(records[1].id, m.transfer_record_id)
        self.assertEqual(mirror.id, m.mirror_id)
        self.assertEqual(Decimal('1.00'), m.wallet_delta)

        mvlogs = (
            self.dbsession.query(db.MovementLog)
            .order_by(db.MovementLog.id)
            .all())

        self.assertEqual(4, len(mvlogs))
        mvlog = mvlogs[0]
        self.assertEqual('download', mvlog.event_type)
        mvlog = mvlogs[1]
        self.assertEqual('download', mvlog.event_type)


class Test_find_internal_movements(unittest.TestCase):

    def _call(self, *args, **kw):
        from ..syncview import find_internal_movements
        return find_internal_movements(*args, **kw)

    def _make_movements(self, spec):
        res = []

        class DummyMovement:
            wallet_delta = zero
            vault_delta = zero

            def __repr__(self):
                return (
                    '<DummyMovement id=%s wallet_delta=%s vault_delta=%s>' % (
                        self.id, self.wallet_delta, self.vault_delta))

            def __eq__(self, other):
                # This makes it easy to test movement sequences.
                if isinstance(other, Decimal) and other == self.vault_delta:
                    return True
                if isinstance(other, DummyMovement):
                    return vars(other) == vars(self)
                return False

        for index, item in enumerate(spec):
            m = DummyMovement()
            m.id = 101 + index
            m.number = 1 + index
            m.mirror_id = 50
            m.action = 'testaction'

            if isinstance(item, dict):
                vars(m).update(item)
            else:
                delta = item
            m.vault_delta = Decimal(delta)

            res.append(m)

        return res

    def test_unbalanced_1(self):
        movements = self._make_movements(['4.1'])
        iseqs = self._call(movements, {})
        self.assertEqual([], iseqs)

    def test_unbalanced_2(self):
        movements = self._make_movements(['4.1', '5'])
        iseqs = self._call(movements, {})
        self.assertEqual([], iseqs)

    def test_unbalanced_3(self):
        movements = self._make_movements(['4.1', '-5', '0.9'])
        iseqs = self._call(movements, {})
        self.assertEqual([], iseqs)

    def test_simple_hill(self):
        movements = self._make_movements(['4.1', '0.9', -5, 2])
        iseqs = self._call(movements, {})
        self.assertEqual([
            [Decimal('4.1'), Decimal('0.9'), Decimal('-5.0')],
        ], iseqs)

    def test_simple_valley(self):
        movements = self._make_movements(['-4.1', '-0.9', 5, 2])
        iseqs = self._call(movements, {})
        self.assertEqual([
            [Decimal('-4.1'), Decimal('-0.9'), Decimal('5.0')],
        ], iseqs)

    def test_hill_after_move(self):
        movements = self._make_movements([2, '4.1', '0.9', -5])
        iseqs = self._call(movements, {})
        self.assertEqual([
            [Decimal('4.1'), Decimal('0.9'), Decimal('-5.0')],
        ], iseqs)

    def test_valley_and_hill_with_nothing_in_between(self):
        movements = self._make_movements(['-4.1', '-0.9', 5, 3, -3, 1])
        iseqs = self._call(movements, {})
        self.assertEqual([
            [Decimal('-4.1'), Decimal('-0.9'), Decimal('5.0')],
            [Decimal('3'), Decimal('-3')],
        ], iseqs)

    def test_hill_valley_hill(self):
        movements = self._make_movements([
            1, 3, -3, '-4.1', '-0.9', 5, 7, -6, -1])
        iseqs = self._call(movements, {})
        self.assertEqual([
            [Decimal('3'), Decimal('-3')],
            [Decimal('-4.1'), Decimal('-0.9'), Decimal('5.0')],
            [Decimal('7'), Decimal('-6'), Decimal('-1')],
        ], iseqs)

    def test_valley_and_hill_with_move_in_between(self):
        movements = self._make_movements(['-4.1', '-0.9', 5, 2, 3, -3, 1])
        iseqs = self._call(movements, {})
        self.assertEqual([
            [Decimal('-4.1'), Decimal('-0.9'), Decimal('5.0')],
            [Decimal('3'), Decimal('-3')],
        ], iseqs)

    def test_hill_with_non_internal_action(self):
        movements = self._make_movements([
            '4.1',
            {'delta': '0.9', 'action': 'move'},
            -5])
        iseqs = self._call(movements, {})
        self.assertEqual([], iseqs)

    def test_hill_with_manual_reco_followed_by_hill(self):
        movements = self._make_movements([
            '4.1', '0.9', 5,
            7, -3, -4])
        iseqs = self._call(movements, {2})
        self.assertEqual([
            [Decimal('7'), Decimal('-3'), Decimal('-4')],
        ], iseqs)

    def test_equal_hill_and_hill(self):
        movements = self._make_movements(['0.25', '-0.25', '0.25', '-0.25'])
        iseqs = self._call(movements, {})
        self.assertEqual([
            [Decimal('0.25'), Decimal('-0.25')],
            [Decimal('0.25'), Decimal('-0.25')],
        ], iseqs)
