
from colander import All
from colander import Boolean
from colander import Integer
from colander import Invalid
from colander import Length
from colander import OneOf
from colander import Regex
from colander import Schema
from colander import SchemaNode
from colander import Sequence
from colander import String as ColanderString
from decimal import Decimal
from opnreport.models.db import AccountEntry
from opnreport.models.db import Movement
from opnreport.models.db import OwnerLog
from opnreport.models.db import Reco
from opnreport.models.db import TransferRecord
from opnreport.models.site import API
from opnreport.param import get_request_file
from opnreport.param import parse_amount
from opnreport.viewcommon import get_loop_map
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy import and_
from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import String
import datetime
import dateutil.parser
import re

zero = Decimal()
null = None


def start_movement_query(dbsession, owner_id):
    return (
        dbsession.query(
            Movement.id,
            Movement.number,
            Movement.ts,
            Movement.loop_id,
            Movement.currency,
            Movement.vault_delta,
            Movement.wallet_delta,
            Movement.reco_id,
            TransferRecord.transfer_id)
        .join(
            TransferRecord,
            TransferRecord.id == Movement.transfer_record_id)
        .filter(
            Movement.owner_id == owner_id,
            # Note: movements of zero are not eligible for reconciliation.
            or_(Movement.vault_delta != zero, Movement.wallet_delta != zero),
        ))


def render_movement_rows(movement_rows):
    res = []
    for row in movement_rows:
        res.append({
            'id': str(row.id),
            'ts': row.ts,
            'loop_id': row.loop_id,
            'currency': row.currency,
            'vault_delta': row.vault_delta,
            'wallet_delta': row.wallet_delta,
            'transfer_id': row.transfer_id,
            'number': row.number,
        })
    return res


def render_account_entry_rows(account_entry_rows):
    res = []
    for row in account_entry_rows:
        res.append({
            'id': str(row.id),
            'entry_date': row.entry_date,
            'loop_id': row.loop_id,
            'currency': row.currency,
            'delta': row.delta,
            'desc': row.desc,
        })
    return res


@view_config(
    name='reco-complete',
    context=API,
    permission='use_app',
    renderer='json')
def reco_complete_view(context, request):
    return reco_view(context, request, complete=True)


@view_config(
    name='reco',
    context=API,
    permission='use_app',
    renderer='json')
def reco_view(context, request, complete=False):
    """Return the state of a reco or a movement proposed for a reco."""

    file, _peer, _loop = get_request_file(request)

    reco_id_input = request.params.get('reco_id')
    movement_id_input = request.params.get('movement_id')
    account_entry_id_input = request.params.get('account_entry_id')

    try:
        reco_id = int(reco_id_input) if reco_id_input else None
        movement_id = int(movement_id_input) if movement_id_input else None
        account_entry_id = (
            int(account_entry_id_input) if account_entry_id_input else None)
    except ValueError:
        raise HTTPBadRequest(json_body={
            'error': 'bad reco_id, movement_id, or account_entry_id'})

    dbsession = request.dbsession
    owner = request.owner
    owner_id = owner.id
    comment = ''
    reco_type = 'standard'

    if reco_id is not None:
        movement_rows = (
            start_movement_query(dbsession=dbsession, owner_id=owner_id)
            .filter(
                Movement.reco_id == reco_id,
            )
            .order_by(
                Movement.ts,
                TransferRecord.transfer_id,
                Movement.number,
                Movement.amount_index,
                Movement.peer_id,
                Movement.loop_id,
                Movement.currency,
                Movement.issuer_id,
            )
            .all())

        account_entry_rows = (
            dbsession.query(AccountEntry)
            .filter(
                AccountEntry.owner_id == owner_id,
                AccountEntry.reco_id == reco_id,
            )
            .order_by(
                AccountEntry.entry_date,
                AccountEntry.id,
            )
            .all())

        reco = (
            dbsession.query(Reco)
            .filter(
                Reco.owner_id == owner_id,
                Reco.id == reco_id)
            .first())

        if reco is not None:
            comment = reco.comment or ''
            reco_type = reco.reco_type

    elif movement_id is not None:
        account_entry_rows = ()
        movement_rows = (
            start_movement_query(dbsession=dbsession, owner_id=owner_id)
            .filter(
                Movement.id == movement_id,
            )
            .all())

    elif account_entry_id is not None:
        movement_rows = ()
        account_entry_rows = (
            dbsession.query(AccountEntry)
            .filter(
                AccountEntry.owner_id == owner_id,
                AccountEntry.id == account_entry_id,
            )
            .all())

    else:
        movement_rows = account_entry_rows = ()

    need_loop_ids = set()
    for row in movement_rows:
        need_loop_ids.add(row.loop_id)

    movements_json = render_movement_rows(movement_rows)
    account_entries_json = render_account_entry_rows(account_entry_rows)

    loops = get_loop_map(
        request=request,
        need_loop_ids=need_loop_ids,
        complete=complete)

    return {
        'reco_type': reco_type,
        'comment': comment,
        'movements': movements_json,
        'account_entries': account_entries_json,
        'loops': loops,
        'is_circ': file.peer_id == 'c',
    }


@view_config(
    name='reco-search-movement',
    context=API,
    permission='use_app',
    renderer='json')
def reco_search_movement_view(context, request, complete=False):
    """Search for movements that haven't been reconciled."""

    file, _peer, _loop = get_request_file(request)

    params = request.json
    amount_input = str(params.get('amount', ''))
    date_input = str(params.get('date', ''))
    transfer_input = str(params.get('transfer', ''))
    # tzoffset is the number of minutes as given by
    # 'new Date().getTimezoneOffset()' in Javascript.
    tzoffset_input = str(params.get('tzoffset'))
    seen_ids = set(int(x) for x in params.get('seen_ids', ()))
    reco_id_input = params.get('reco_id')

    if reco_id_input:
        reco_id = int(reco_id_input)
    else:
        reco_id = None

    dbsession = request.dbsession
    owner = request.owner
    owner_id = owner.id
    filters = []


    amount_parsed = parse_amount(amount_input)
    if amount_parsed is not None:
        amount_abs = abs(amount_parsed)
        vault_sign_filters = ()
        wallet_sign_filters = ()
        if amount_parsed.sign < 0:
            vault_sign_filters = ((Movement.vault_delta < 0),)
            wallet_sign_filters = ((Movement.wallet_delta < 0),)
        elif amount_parsed.sign > 0:
            vault_sign_filters = ((Movement.vault_delta > 0),)
            wallet_sign_filters = ((Movement.wallet_delta > 0),)

        if '.' in amount_parsed.str_value:
            # Exact amount.
            filters.append(or_(
                and_(
                    func.abs(Movement.vault_delta) == amount_abs,
                    *vault_sign_filters),
                and_(
                    func.abs(Movement.wallet_delta) == amount_abs,
                    *wallet_sign_filters),
            ))
        else:
            # The search omitted the subunit value.
            filters.append(or_(
                and_(
                    func.abs(Movement.vault_delta) >= amount_abs,
                    func.abs(Movement.vault_delta) < amount_abs + 1,
                    *vault_sign_filters),
                and_(
                    func.abs(Movement.wallet_delta) >= amount_abs,
                    func.abs(Movement.wallet_delta) < amount_abs + 1,
                    *wallet_sign_filters),
            ))

    match = re.search(r'[A-Z]+', amount_input, re.I)
    if match is not None:
        currency = match.group(0).upper()
        filters.append(
            Movement.currency.like(func.concat('%', currency, '%')))

    if date_input and tzoffset_input:
        try:
            parsed = dateutil.parser.parse(date_input)
            tzoffset = int(tzoffset_input)
        except Exception:
            pass
        else:
            if parsed is not None:
                ts = parsed + datetime.timedelta(seconds=tzoffset * 60)
                filters.append(Movement.ts >= ts)
                colon_count = sum((1 for c in date_input if c == ':'), 0)
                if colon_count >= 2:
                    # Query with second resolution
                    filters.append(
                        Movement.ts < ts + datetime.timedelta(seconds=1))
                elif colon_count >= 1:
                    # Query with minute resolution
                    filters.append(
                        Movement.ts < ts + datetime.timedelta(seconds=60))
                elif parsed.hour:
                    # Query with hour resolution
                    filters.append(
                        Movement.ts < ts + datetime.timedelta(seconds=3600))
                else:
                    # Query with day resolution
                    filters.append(
                        Movement.ts < ts + datetime.timedelta(days=1))

    match = re.search(r'[0-9\-]+', transfer_input)
    if match is not None:
        transfer_str = match.group(0).replace('-', '')
        if transfer_str:
            filters.append(
                cast(TransferRecord.transfer_id, String).like(
                    func.concat('%', transfer_str, '%')))

    if not filters:
        return []

    if seen_ids:
        filters.append(~Movement.id.in_(seen_ids))

    movement_rows = (
        start_movement_query(dbsession=dbsession, owner_id=owner_id)
        .filter(
            Movement.peer_id == file.peer_id,
            Movement.currency == file.currency,
            Movement.loop_id == file.loop_id,
            or_(
                Movement.reco_id == null,
                Movement.reco_id == reco_id,
            ),
            *filters
        )
        .order_by(
            Movement.ts,
            TransferRecord.transfer_id,
            Movement.number,
            Movement.amount_index,
            Movement.peer_id,
            Movement.loop_id,
            Movement.currency,
            Movement.issuer_id,
        )
        .limit(5)
        .all())

    movements_json = render_movement_rows(movement_rows)

    return movements_json


@view_config(
    name='reco-search-account-entries',
    context=API,
    permission='use_app',
    renderer='json')
def reco_search_account_entries(context, request, complete=False):
    """Search for account entries that haven't been reconciled."""

    file, _peer, _loop = get_request_file(request)

    params = request.json
    delta_input = str(params.get('delta', ''))
    entry_date_input = str(params.get('entry_date', ''))
    desc_input = str(params.get('desc', ''))
    seen_ids = set(int(x) for x in params.get('seen_ids', ()))
    reco_id_input = params.get('reco_id')

    if reco_id_input:
        reco_id = int(reco_id_input)
    else:
        reco_id = None

    dbsession = request.dbsession
    owner = request.owner
    owner_id = owner.id
    filters = []

    delta_parsed = parse_amount(delta_input)
    if delta_parsed is not None:
        delta_abs = abs(delta_parsed)

        sign_filters = ()
        if delta_parsed.sign < 0:
            sign_filters = ((AccountEntry.delta < 0),)
        elif delta_parsed.sign > 0:
            sign_filters = ((AccountEntry.delta > 0),)

        if '.' in delta_parsed.str_value:
            # Exact amount.
            filters.append(and_(
                func.abs(AccountEntry.delta) == delta_abs,
                *sign_filters))
        else:
            # The search omitted the subunit value.
            filters.append(and_(
                func.abs(AccountEntry.delta) >= delta_abs,
                func.abs(AccountEntry.delta) < delta_abs + 1,
                *sign_filters))

    match = re.search(r'[A-Z]+', delta_input, re.I)
    if match is not None:
        currency = match.group(0).upper()
        filters.append(
            AccountEntry.currency.like(func.concat('%', currency, '%')))

    if entry_date_input:
        try:
            parsed = dateutil.parser.parse(entry_date_input).date()
        except Exception:
            pass
        else:
            if parsed is not None:
                filters.append(AccountEntry.entry_date == parsed)

    if desc_input:
        filters.append(AccountEntry.desc.ilike(
            func.concat('%', desc_input, '%')))

    if not filters:
        return []

    if seen_ids:
        filters.append(~AccountEntry.id.in_(seen_ids))

    rows = (
        dbsession.query(AccountEntry)
        .filter(
            AccountEntry.owner_id == owner_id,
            AccountEntry.file_id == file.id,
            AccountEntry.currency == file.currency,
            AccountEntry.loop_id == file.loop_id,
            or_(
                AccountEntry.reco_id == null,
                AccountEntry.reco_id == reco_id,
            ),
            *filters
        )
        .order_by(
            AccountEntry.entry_date,
            AccountEntry.desc,
            AccountEntry.id,
        )
        .limit(5)
        .all())

    entries_json = render_account_entry_rows(rows)

    return entries_json


# Note: the schema below includes only the fields needed by reco-save.


class MovementSchema(Schema):
    id = SchemaNode(Integer())


# \u2212 = true minus sign
amount_re = re.compile(r'^[+\-\u2212]?[0-9.,]+$', re.UNICODE)


class AccountEntrySchema(Schema):
    # Validate these fields only lightly. The code will do its own
    # parsing and validation.
    id = SchemaNode(
        ColanderString(),
        validator=Regex(r'^(creating_)?[0-9]+$'))
    creating = SchemaNode(Boolean(), missing=False)
    delta = SchemaNode(
        ColanderString(),
        missing='',
        validator=All(
            Length(max=100),
            Regex(amount_re, msg="Invalid amount"),
        ))
    entry_date = SchemaNode(
        ColanderString(),
        missing='',
        validator=Length(max=100))
    desc = SchemaNode(
        ColanderString(),
        missing='',
        validator=Length(max=1000))


class RecoSchema(Schema):
    reco_type = SchemaNode(
        ColanderString(),
        validator=OneOf(('standard', 'wallet_only', 'account_only')))
    comment = SchemaNode(
        ColanderString(),
        missing='',
        validator=Length(max=10000))
    movements = SchemaNode(
        Sequence(),
        MovementSchema(),
        missing=(),
        validator=Length(max=100))
    account_entries = SchemaNode(
        Sequence(),
        AccountEntrySchema(),
        missing=(),
        validator=Length(max=100))


class RecoSaveSchema(Schema):
    reco_id = SchemaNode(Integer(), missing=None)
    reco = RecoSchema()


movement_matches_required = (
    ('currency', "currency", "currencies"),
    ('loop_id', "cash design", "cash designs"),
    ('transfer_record_id', "transfer", "transfers"),
    ('peer_id', "peer", "peers"),
)


@view_config(
    name='reco-save',
    context=API,
    permission='use_app',
    renderer='json')
class RecoSave:
    def __init__(self, context, request):
        self.request = request

    def __call__(self):
        """Save changes to a reco."""
        request = self.request
        file, _peer, _loop = get_request_file(request)
        try:
            self.params = params = RecoSaveSchema().deserialize(request.json)
        except Invalid as e:
            raise HTTPBadRequest(json_body={
                'error': 'invalid',
                'error_description': '; '.join(
                    "%s (%s)" % (v, k)
                    for (k, v) in sorted(e.asdict().items())),
            })

        self.file = file
        self.reco_id = params['reco_id']
        self.reco_type = reco_type = params['reco']['reco_type']

        if reco_type == 'account_only':
            new_movements = ()
        else:
            new_movement_ids = set(
                m['id'] for m in params['reco']['movements'])
            new_movements = self.get_new_movements(new_movement_ids)

        if reco_type == 'wallet_only':
            new_account_entries = ()
        else:
            new_account_entries = self.get_new_account_entries(
                params['reco']['account_entries'])

        reco = self.get_old_reco()
        self.final_check(
            new_movements=new_movements,
            new_account_entries=new_account_entries)

        # Everything checks out. Save the changes.

        if self.reco_id is not None:
            self.remove_old_movements(new_movements=new_movements)
            self.remove_old_account_entries(
                new_account_entries=new_account_entries)
        else:
            if (not new_movements and not new_account_entries and
                    not params['reco']['comment']):
                # This is a new reco with no movements, account entries, or
                # even a comment. Don't create an empty reco.
                return {'empty': True}

        reco_id = self.save(
            reco=reco,
            new_movements=new_movements,
            new_account_entries=new_account_entries)

        return {'ok': True, 'reco_id': reco_id}

    def get_new_movements(self, new_movement_ids):
        if not new_movement_ids:
            return ()

        request = self.request
        dbsession = request.dbsession
        owner = request.owner
        owner_id = owner.id
        file = self.file

        new_movements = (
            dbsession.query(Movement)
            .filter(
                Movement.owner_id == owner_id,
                Movement.id.in_(new_movement_ids),
                Movement.peer_id == file.peer_id,
                Movement.currency == file.currency,
                Movement.loop_id == file.loop_id,
                or_(
                    Movement.reco_id == null,
                    Movement.reco_id == self.reco_id,
                ),
                or_(
                    Movement.wallet_delta != zero,
                    Movement.vault_delta != zero,
                ),
            )
            .all())

        if len(new_movements) != len(new_movement_ids):
            raise HTTPBadRequest(json_body={
                'error': 'invalid_movement_id',
                'error_description': (
                    "One or more of the movements specified is not "
                    "eligible for reconciliation. A movement may have "
                    "been reconciled previously. "
                    "Try re-syncing with OPN."),
            })

        for attr, singular, plural in movement_matches_required:
            value_set = set(getattr(m, attr) for m in new_movements)
            if len(value_set) > 1:
                raise HTTPBadRequest(json_body={
                    'error': 'multiple_%s' % attr,
                    'error_description': (
                        "Multiple %s detected. All movements in a "
                        "reconciliation must be for the same %s."
                        % (plural, singular)),
                })

        return new_movements

    def create_account_entry(self, inputs):
        """Create a new AccountEntry from the inputs."""
        file = self.file
        delta_input = inputs['delta']
        if not delta_input:
            raise HTTPBadRequest(json_body={
                'error': 'amount_required',
                'error_description': (
                    "An amount is required for each account entry."),
            })

        try:
            delta = parse_amount(delta_input)
        except Exception as e:
            raise HTTPBadRequest(json_body={
                'error': 'amount_parse_error',
                'error_description': (
                    "Unable to parse amount '%s': %s" % (delta_input, e))
            })

        match = re.search(r'[A-Z]+', delta_input, re.I)
        if match is not None:
            currency = match.group(0).upper()
            if currency != file.currency:
                raise HTTPBadRequest(json_body={
                    'error': 'currency_mismatch',
                    'error_description': (
                        "Currency should be %s" % self.file.currency)
                })

        date_input = inputs['entry_date']
        if not date_input:
            raise HTTPBadRequest(json_body={
                'error': 'date_required',
                'error_description': (
                    "A date is required for each account entry."),
            })

        try:
            entry_date = dateutil.parser.parse(date_input).date()
        except Exception as e:
            raise HTTPBadRequest(json_body={
                'error': 'date_parse_error',
                'error_description': (
                    "Unable to parse date '%s': %s" % (date_input, e))
            })

        entry = AccountEntry(
            owner_id=self.request.owner.id,
            file_id=file.id,
            entry_date=entry_date,
            loop_id=file.loop_id,
            currency=file.currency,
            delta=delta,
            desc=inputs['desc'] or '',
        )
        return entry

    def get_new_account_entries(self, new_entries):
        res = []
        reusing_ids = []

        for entry in new_entries:
            if entry['creating']:
                if entry['delta'] or entry['entry_date'] or entry['desc']:
                    res.append(self.create_account_entry(entry))
                # else it's a blank input row; ignore it.
            else:
                reusing_ids.append(int(entry['id']))

        if reusing_ids:
            request = self.request
            dbsession = request.dbsession
            owner = request.owner
            owner_id = owner.id
            file = self.file

            reusing_entries = (
                dbsession.query(AccountEntry)
                .filter(
                    AccountEntry.owner_id == owner_id,
                    AccountEntry.id.in_(reusing_ids),
                    AccountEntry.currency == file.currency,
                    AccountEntry.loop_id == file.loop_id,
                    or_(
                        AccountEntry.reco_id == null,
                        AccountEntry.reco_id == self.reco_id,
                    ),
                    AccountEntry.delta != zero,
                )
                .all())

            if len(reusing_entries) != len(reusing_ids):
                raise HTTPBadRequest(json_body={
                    'error': 'invalid_account_entry_id',
                    'error_description': (
                        "One or more of the account entries specified is not "
                        "eligible for reconciliation. An account entry "
                        "may have been reconciled previously. "
                        "Try re-syncing with OPN."),
                })

            res.extend(reusing_entries)

        return res

    def get_old_reco(self):
        reco_id = self.reco_id
        if reco_id is None:
            return None

        request = self.request
        dbsession = request.dbsession
        owner_id = request.owner.id
        reco = (
            dbsession.query(Reco)
            .filter(
                Reco.owner_id == owner_id,
                Reco.id == reco_id)
            .first())
        if reco is None:
            raise HTTPBadRequest(json_body={
                'error': 'reco_not_found',
                'error_description': "Reconciliation record not found.",
            })

        return reco

    def final_check(self, new_movements, new_account_entries):
        reco_type = self.reco_type
        if reco_type == 'standard':
            wallet_sum = sum(m.wallet_delta for m in new_movements)
            vault_sum = sum(m.vault_delta for m in new_movements)
            entries_sum = sum(e.delta for e in new_account_entries)
            if wallet_sum + vault_sum + entries_sum != zero:
                raise HTTPBadRequest(json_body={
                    'error': 'unbalanced_reconciliation',
                    'error_description': "Unbalanced reconciliation. "
                    "Standard reconciliation requires the sum "
                    "of changes to the account, vault, and wallet to "
                    "equal zero.",
                })
        elif reco_type == 'wallet_only':
            for m in new_movements:
                if m.vault_delta:
                    raise HTTPBadRequest(json_body={
                        'error': 'wallet_only_excludes_vault',
                        'error_description': "Wallet Income/Expense "
                        "reconciliation can include wallet changes only, "
                        "not vault changes.",
                    })

        if self.reco_type != 'standard' and not self.params['reco']['comment']:
            raise HTTPBadRequest(json_body={
                'error': 'comment_required',
                'error_description': (
                    "An explanatory comment is required "
                    "for nonstandard reconciliations."),
            })

    def remove_old_movements(self, new_movements):
        """Remove old movements from the reco."""
        request = self.request
        dbsession = request.dbsession
        owner_id = request.owner.id

        filters = []
        if new_movements:
            filters.append(~Movement.id.in_(m.id for m in new_movements))

        old_movements = (
            dbsession.query(Movement)
            .filter(
                Movement.owner_id == owner_id,
                Movement.reco_id == self.reco_id,
                *filters)
            .all())

        for m in old_movements:
            m.reco_id = None
            m.reco_wallet_delta = m.wallet_delta

    def remove_old_account_entries(self, new_account_entries):
        """Remove old account entries from the reco."""
        request = self.request
        dbsession = request.dbsession
        owner_id = request.owner.id

        new_account_entry_ids = [
            e.id for e in new_account_entries if e.id is not None]
        filters = []
        if new_account_entry_ids:
            filters.append(~AccountEntry.id.in_(new_account_entry_ids))

        old_account_entries = (
            dbsession.query(AccountEntry)
            .filter(
                AccountEntry.owner_id == owner_id,
                AccountEntry.reco_id == self.reco_id,
                *filters)
            .all())

        for e in old_account_entries:
            e.reco_id = None

    def save(self, reco, new_movements, new_account_entries):
        request = self.request
        dbsession = request.dbsession
        owner_id = request.owner.id
        reco_type = self.reco_type
        params = self.params
        internal = (reco_type == 'standard' and not new_account_entries)
        comment = params['reco']['comment']

        if new_account_entries:
            # Get the file_id from the first account entry.
            by_date = sorted(
                new_account_entries, key=lambda x: (x.entry_date, x.id))
            file_id = by_date[0].file_id
        elif new_movements:
            # Get the file_id from the first movement.
            by_ts = sorted(new_movements, key=lambda x: (x.ts, x.number, x.id))
            file_id = by_ts[0].file_id
        else:
            file_id = self.file.id

        if reco is None:
            added = True
            reco = Reco(
                owner_id=owner_id,
                reco_type=reco_type,
                internal=internal,
                file_id=file_id,
                comment=comment)
            dbsession.add(reco)
            dbsession.flush()  # Assign reco.id
            reco_id = reco.id
        else:
            reco_id = reco.id
            reco.reco_type = reco_type
            reco.internal = internal
            reco.file_id = file_id
            reco.comment = comment
            added = False

        for m in new_movements:
            m.reco_id = reco_id
            if reco_type == 'wallet_only':
                # Wallet-only reconciliations should have no effect on
                # the surplus amount.
                m.reco_wallet_delta = zero
            else:
                # Other reconciliations expect the surplus to change
                # inversely to the wallet.
                m.reco_wallet_delta = m.wallet_delta

        created_account_entries = []
        for entry in new_account_entries:
            entry.reco_id = reco_id
            if entry.id is None:
                dbsession.add(entry)
                created_account_entries.append(entry)

        if created_account_entries:
            dbsession.flush()  # Assign the entry IDs

        dbsession.add(OwnerLog(
            owner_id=owner_id,
            event_type='reco_add' if added else 'reco_change',
            remote_addr=request.remote_addr,
            user_agent=request.user_agent,
            content={
                'reco_id': reco_id,
                'reco': params['reco'],
                'internal': internal,
                'created_account_entries': [{
                    'id': e.id,
                    'owner_id': e.owner_id,
                    'file_id': e.file_id,
                    'entry_date': e.entry_date,
                    'currency': e.currency,
                    'loop_id': e.loop_id,
                    'delta': e.delta,
                    'desc': e.desc,
                } for e in created_account_entries],
                'file_id': file_id,
            },
        ))
        dbsession.flush()

        return reco_id
