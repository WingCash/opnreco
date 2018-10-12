
from sqlalchemy.orm import backref
from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Numeric
from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy import Integer
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import Unicode
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import MetaData


# Recommended naming convention used by Alembic, as various different database
# providers will autogenerate vastly different names making migrations more
# difficult. See: http://alembic.readthedocs.org/en/latest/naming.html
NAMING_CONVENTION = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
Base = declarative_base(metadata=metadata)

now_func = func.timezone('UTC', func.current_timestamp())


class Owner(Base):
    """Info about an OPN profile that has used this tool."""
    __tablename__ = 'owner'
    # id is an OPN profile ID.
    id = Column(String, nullable=False, primary_key=True)
    title = Column(Unicode, nullable=False)
    username = Column(String, nullable=False)
    # last_update is when the title and username were last updated.
    last_update = Column(DateTime, nullable=True, server_default=now_func)
    # first_sync_ts is set when a sync has started but not
    # finished.  It contains the first_sync_ts from the first batch.
    first_sync_ts = Column(DateTime, nullable=True)
    last_sync_ts = Column(DateTime, nullable=True)
    last_sync_transfer_id = Column(String, nullable=True)
    # sync_total is the number of transfer records in this sync operation.
    sync_total = Column(BigInteger, nullable=False, default=0)
    # sync_done is the number of transfer records downloaded
    # successfully in this sync operation.
    sync_done = Column(BigInteger, nullable=False, default=0)


class OwnerLog(Base):
    """Log of an event related to an owner"""
    __tablename__ = 'owner_log'
    id = Column(BigInteger, nullable=False, primary_key=True)
    ts = Column(DateTime, nullable=False, server_default=now_func)
    owner_id = Column(
        String, ForeignKey('owner.id'), nullable=False, index=True)
    event_type = Column(String, nullable=False)
    remote_addr = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    memo = Column(JSONB, nullable=False)


class Peer(Base):
    """Info about a peer (an OPN holder).

    Peers are updated automatically until frozen into a file.
    """
    __tablename__ = 'peer'
    owner_id = Column(
        String, ForeignKey('owner.id'), nullable=False, primary_key=True)
    peer_id = Column(String, nullable=False, primary_key=True)

    title = Column(Unicode, nullable=True)
    username = Column(String, nullable=True)
    is_dfi_account = Column(Boolean, nullable=False, default=False)

    # Note: don't try to update if removed or if file_id is non-null.
    removed = Column(Boolean, nullable=False, default=False)
    last_update = Column(DateTime, nullable=True)


class CashDesign(Base):
    """Info about an unfiled cash design.

    Cash designs are updated automatically until frozen into a file.
    """
    __tablename__ = 'cash_design'
    owner_id = Column(
        String, ForeignKey('owner.id'), nullable=False, primary_key=True)
    loop_id = Column(String, nullable=False, primary_key=True)

    title = Column(Unicode, nullable=True)

    # Note: don't try to update if removed or if file_id is non-null.
    removed = Column(Boolean, nullable=False, default=False)
    last_update = Column(DateTime, nullable=True)


class File(Base):
    """A time-boxed record of movements that should mirror OPN transfers.

    Represents a period of time for transfers with a specific peer,
    where a peer is a wallet, account, or the circulating omnibus account
    managed by an issuer.
    """
    __tablename__ = 'file'
    id = Column(BigInteger, nullable=False, primary_key=True)
    owner_id = Column(String, ForeignKey('owner.id'), nullable=False)
    # peer_id is either an OPN holder ID or
    # the letter 'c' for circulating.
    peer_id = Column(String, nullable=False)
    loop_id = Column(String, nullable=False)
    currency = Column(String(3), nullable=False)
    # New recos are added to the 'is_new' file.
    is_new = Column(Boolean, nullable=False, default=True)
    # has_vault becomes true if money ever moves in or out of the
    # vault connected with this File.
    has_vault = Column(Boolean, nullable=False, default=False)
    subtitle = Column(Unicode, nullable=True)

    owner = backref(Owner)

    def getstate(self):
        return {
            'id': str(self.id),
            'owner_id': self.owner_id,
            'peer_id': self.peer_id,
            'loop_id': self.loop_id,
            'currency': self.currency,
            'is_new': self.is_new,
            'has_vault': self.has_vault,
            'subtitle': self.subtitle,
        }


Index(
    'ix_file_is_new_unique',
    File.owner_id,
    File.peer_id,
    File.loop_id,
    File.currency,
    postgresql_where=File.is_new,
    unique=True)


class FileFrozen(Base):
    """Frozen attributes of a File.

    FileFrozen is created when the user closes a File.
    """
    __tablename__ = 'file_frozen'

    file_id = Column(
        BigInteger, ForeignKey('file.id'), nullable=False, primary_key=True)
    start_date = Column(Date, nullable=False)
    start_balance = Column(Numeric, nullable=False, default=0)
    end_date = Column(Date, nullable=False)
    end_balance = Column(Numeric, nullable=False)
    peer_title = Column(Unicode, nullable=True)
    peer_username = Column(String, nullable=True)
    peer_is_dfi_account = Column(Boolean, nullable=False, default=False)
    loop_title = Column(Unicode, nullable=True)

    file = backref(File)


class TransferRecord(Base):
    """An owner's transfer record.

    Each owner has a different filtered view of the list of movements
    for a transfer, so this app only keeps owner-specific transfer records.

    Note: transfers have other fields that aren't reflected here because they
    aren't important for this app.
    """
    __tablename__ = 'transfer_record'
    id = Column(BigInteger, nullable=False, primary_key=True)
    owner_id = Column(String, ForeignKey('owner.id'), nullable=False)
    transfer_id = Column(String, nullable=False)

    workflow_type = Column(String, nullable=False)    # Never changes
    start = Column(DateTime, nullable=False)          # Never changes
    currency = Column(String, nullable=False)         # May change
    amount = Column(Numeric, nullable=False)          # May change
    timestamp = Column(DateTime, nullable=False)      # May change
    next_activity = Column(String, nullable=False)    # May change
    completed = Column(Boolean, nullable=False)       # May change
    canceled = Column(Boolean, nullable=False)        # May change

    sender_id = Column(String, nullable=True)         # May change
    sender_uid = Column(Unicode, nullable=True)       # May change
    sender_info = Column(JSONB, nullable=True)        # May change

    recipient_id = Column(String, nullable=True)      # May change
    recipient_uid = Column(Unicode, nullable=True)    # May change
    recipient_info = Column(JSONB, nullable=True)     # May change

    owner = backref(Owner)


Index(
    'ix_transfer_record_unique',
    TransferRecord.owner_id,
    TransferRecord.transfer_id,
    unique=True)


class OPNDownload(Base):
    """A record of OPN data downloaded for an owner.
    """
    __tablename__ = 'opn_download'
    id = Column(BigInteger, nullable=False, primary_key=True)
    owner_id = Column(
        String, ForeignKey('owner.id'), index=True, nullable=False)
    ts = Column(DateTime, nullable=False, server_default=now_func)
    content = Column(JSONB, nullable=False)


class TransferDownloadRecord(Base):
    """A record of which download(s) provided TransferRecord data."""
    __tablename__ = 'transfer_download_record'
    opn_download_id = Column(
        BigInteger, ForeignKey('opn_download.id'),
        nullable=False, primary_key=True)
    transfer_record_id = Column(
        BigInteger, ForeignKey('transfer_record.id'),
        nullable=False, primary_key=True)
    transfer_id = Column(String, nullable=False)
    changed = Column(JSONB, nullable=False)

    opn_download = backref(OPNDownload)
    transfer_record = backref(TransferRecord)


class Movement(Base):
    """A movement in a transfer record.

    Note: two rows are created for every movement, one for the peer file,
    and one for the 'c' file ('c' means 'circulation' or 'common'). This
    doubling reflects the fact that the user may need to run a separate
    reconciliation for the circulation account and the peer account.

    The UI should do what it can to show only one of the two reconciliations;
    for example, if the peer has no vault, the circulation reconciliation
    should not be shown; as another example, if the peer is a wallet rather
    than a DFI account, the peer reconciliation should not be shown.

    Note: movement rows are meant to be immutable.
    """
    __tablename__ = 'movement'
    id = Column(BigInteger, nullable=False, primary_key=True)
    transfer_record_id = Column(
        BigInteger, ForeignKey('transfer_record.id'), nullable=False)
    number = Column(Integer, nullable=False)

    # peer_id can be 'c' (for 'common' or 'circulation'). The 'c'
    # row is the doubled row.
    peer_id = Column(String, nullable=False)
    # orig_peer_id is never 'c'.
    orig_peer_id = Column(
        String, CheckConstraint(
            "orig_peer_id != 'c'", name='orig_peer_id_not_c'),
        nullable=False)
    loop_id = Column(String, nullable=False)
    currency = Column(String(3), nullable=False)
    issuer_id = Column(String, nullable=False)

    from_id = Column(String, nullable=True)  # Null for issuance
    to_id = Column(String, nullable=False)
    amount = Column(Numeric, nullable=False)
    action = Column(String, nullable=False)
    ts = Column(DateTime, nullable=False)

    # The delta is positive for movements into the wallet or vault
    # or negative for movements out of the wallet or vault.
    wallet_delta = Column(Numeric, nullable=False)
    vault_delta = Column(Numeric, nullable=False)

    transfer_record = backref(TransferRecord)


Index(
    'ix_movement_unique',
    Movement.transfer_record_id,
    Movement.number,
    Movement.peer_id,
    Movement.orig_peer_id,
    Movement.loop_id,
    Movement.currency,
    Movement.issuer_id,
    unique=True)


class MovementLog(Base):
    """Log of changes to a movement"""
    __tablename__ = 'movement_log'
    id = Column(BigInteger, nullable=False, primary_key=True)
    ts = Column(DateTime, nullable=False, server_default=now_func)
    movement_id = Column(
        BigInteger, ForeignKey('movement.id'),
        nullable=False, index=True)
    event_type = Column(String, nullable=False)
    comment = Column(Unicode, nullable=True)

    # changes is a dict. The possible changes are:
    # reco_id
    changes = Column(JSONB, nullable=False)

    movement = backref(Movement)


class Statement(Base):
    """A statement of movements to/from an account connected with a File."""
    __tablename__ = 'statement'
    id = Column(BigInteger, nullable=False, primary_key=True)
    file_id = Column(
        BigInteger, ForeignKey('file.id'),
        nullable=False, index=True)
    ts = Column(DateTime, nullable=False, server_default=now_func)
    content = Column(JSONB, nullable=False)

    owner = backref(Owner)
    file = backref(File)


class AccountEntry(Base):
    """An entry in an account statement."""
    __tablename__ = 'account_entry'
    id = Column(BigInteger, nullable=False, primary_key=True)
    file_id = Column(
        BigInteger, ForeignKey('file.id'),
        nullable=False, index=True)

    statement_id = Column(
        BigInteger, ForeignKey('statement.id'),
        nullable=True, index=True)
    statement_ref = Column(JSONB, nullable=True)
    entry_date = Column(Date, nullable=False)

    # The delta is negative for account decreases.
    # Note: we use the terms increase and decrease instead of debit/credit
    # because debit/credit is ambiguous: an increase of a checking account is
    # both a *credit* to the account holder's asset account and a *debit* to
    # the bank's liability account.
    delta = Column(Numeric, nullable=False)

    # desc contains descriptive info provided by the bank.
    desc = Column(JSONB, nullable=False)

    file = backref(File)
    statement = backref(Statement)


class AccountEntryLog(Base):
    """Log of changes to an account entry"""
    __tablename__ = 'account_entry_log'
    id = Column(BigInteger, nullable=False, primary_key=True)
    ts = Column(DateTime, nullable=False, server_default=now_func)
    account_entry_id = Column(
        BigInteger, ForeignKey('account_entry.id'),
        nullable=False, index=True)
    event_type = Column(String, nullable=False)
    comment = Column(Unicode, nullable=True)

    # changes is a dict. The possible changes are:
    # reco_id, statement_id, statement_ref, entry_date, delta, and desc.
    changes = Column(JSONB, nullable=False)

    account_entry = backref(AccountEntry)


class Reco(Base):
    """A reconciliation row matches movement(s) and account entries.

    The linked movements, exchanges, and account entries must be connected
    to the same File. The total deltas must be equal if the
    movements are sent from or received into the
    wallet; the total deltas must be negatives of each other if the
    movements are sent from or received into the vault.
    """
    __tablename__ = 'reco'
    id = Column(BigInteger, nullable=False, primary_key=True)
    file_id = Column(
        BigInteger, ForeignKey('file.id'),
        nullable=False, index=True)
    # entry_date is copied from an account statement or movement.
    entry_date = Column(Date, nullable=False)
    # auto is true if the reconciliation was generated automatically.
    auto = Column(Boolean, nullable=False)
    # auto_edited is true if the reconciliation was generated automatically
    # and later edited.
    auto_edited = Column(Boolean, nullable=False, default=False)

    file = backref(File)


class MovementReco(Base):
    """Association of a movement to a Reco.

    A movement can be connected to only one Reco, but a Reco
    can be connected to multiple movements.
    """
    __tablename__ = 'movement_reco'
    movement_id = Column(
        BigInteger, ForeignKey('movement.id'),
        nullable=False, primary_key=True)
    reco_id = Column(
        BigInteger, ForeignKey('reco.id'), nullable=False, index=True)

    movement = backref(Movement)
    reco = backref(Reco)


class AccountEntryReco(Base):
    """Association of an AccountEntry to a Reco.

    An AccountEntry can be connected to only one Reco, but a Reco
    can be connected to multiple AccountEntry rows.
    """
    __tablename__ = 'account_entry_reco'
    account_entry_id = Column(
        BigInteger, ForeignKey('account_entry.id'),
        nullable=False, primary_key=True)
    reco_id = Column(
        BigInteger, ForeignKey('reco.id'), nullable=False, index=True)

    account_entry = backref(AccountEntry)
    reco = backref(Reco)


class Exchange(Base):
    """A record of an exchange between wallet and vault amounts in a transfer.

    The exchange balances out the movements.
    """
    __tablename__ = 'exchange'
    id = Column(BigInteger, nullable=False, primary_key=True)
    transfer_record_id = Column(
        BigInteger, ForeignKey('transfer_record.id'), nullable=False)
    peer_id = Column(String, nullable=False)
    loop_id = Column(String, nullable=False)
    currency = Column(String(3), nullable=False)

    # origin_reco_id identifies the auto-generated reco that originated the
    # exchange.
    origin_reco_id = Column(
        BigInteger, ForeignKey('reco.id'), nullable=False, index=True)

    # reco_id identifies the reco that settles the exchange.
    reco_id = Column(
        BigInteger, ForeignKey('reco.id'), nullable=True, index=True)

    wallet_delta = Column(Numeric, nullable=False)
    vault_delta = Column(Numeric, nullable=False)


# all_metadata_defined must be at the end of the file. It signals that
# all model classes have been defined successfully.
all_metadata_defined = True
