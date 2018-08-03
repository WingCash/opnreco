
from sqlalchemy.orm import backref
from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Numeric
from sqlalchemy import ForeignKey
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


class Profile(Base):
    """Info about a profile that has used this tool."""
    __tablename__ = 'profile'
    # id is an OPN profile ID.
    id = Column(String, nullable=False, primary_key=True)
    title = Column(Unicode, nullable=False)
    last_transfer_update = Column(DateTime, nullable=True)
    # access_token = Column(String, nullable=True)
    # access_token_expires = Column(DateTime, nullable=True)


class OPNDownload(Base):
    """A record of transfer info downloaded for a profile.
    """
    __tablename__ = 'opn_download'
    id = Column(BigInteger, nullable=False, primary_key=True)
    profile_id = Column(
        String, ForeignKey('profile.id'), index=True, nullable=False)
    ts = Column(DateTime, nullable=False)
    content = Column(JSONB, nullable=False)


class Transfer(Base):
    """A profile's transfer record.

    Each profile has a different filtered view of the list of movements
    for a transfer, so this app only keeps profile-specific transfer records,
    not cross-profile transfer records.

    Note: transfers have other fields that aren't reflected here because they
    aren't important for this app.
    """
    __tablename__ = 'transfer'
    transfer_id = Column(String, primary_key=True, nullable=False)
    profile_id = Column(
        String, ForeignKey('profile.id'), primary_key=True, nullable=False)
    workflow_type = Column(String, nullable=False)    # Never changes
    start = Column(DateTime, nullable=False)          # Never changes

    end = Column(DateTime, nullable=True)             # Changes once
    completed = Column(Boolean, nullable=False)       # May change
    canceled = Column(Boolean, nullable=False)        # May change

    sender_id = Column(String, nullable=True)         # May change
    sender_uid = Column(Unicode, nullable=True)       # May change
    sender_title = Column(Unicode, nullable=True)     # May change

    recipient_id = Column(String, nullable=True)      # May change
    recipient_uid = Column(Unicode, nullable=True)    # May change
    recipient_title = Column(Unicode, nullable=True)  # May change

    movement_lists = Column(JSONB, nullable=False)    # Append-only

    # need_reco is true only if the profile should reconcile this transfer.
    need_reco = Column(Boolean, nullable=False)

    profile = backref(Profile)


class MovementSummary(Base):
    """The summary of some movements in a transfer on a profile's wallet/vault.
    """
    __tablename__ = 'movement_summary'
    id = Column(BigInteger, nullable=False, primary_key=True)
    transfer_id = Column(
        String, ForeignKey('transfer.id'), nullable=False)
    profile_id = Column(
        String, ForeignKey('profile.id'), nullable=False)

    # movement_list_index specifies which movement list this summary is based
    # on. If more movements happen later, we'll add another MovementSummary
    # that offsets the previous MovementSummary.
    movement_list_index = Column(Integer, nullable=False)

    # If vault is true, the cash was sent to/from the profile's vault.
    # If vault is false, the cash was sent to/from the profile's wallet.
    vault = Column(Boolean, nullable=False)

    loop_id = Column(String, nullable=False)
    currency = Column(String(3), nullable=False)

    # The delta is negative for account decreases.
    delta = Column(Numeric, nullable=False)

    transfer = backref(Transfer)
    profile = backref(Profile)


Index(
    'ix_movement_summary_transfer_profile',
    MovementSummary.transfer_id, MovementSummary.profile_id)


class DFIBalance(Base):
    """A record of the verified DFI balance at the start of a day."""
    __tablename__ = 'dfi_balance'
    profile_id = Column(
        String, ForeignKey('profile.id'), primary_key=True, nullable=False)
    day = Column(Date, primary_key=True, nullable=False)
    balance = Column(Numeric, nullable=False)

    profile = backref(Profile)


class DFIStatement(Base):
    """A record of a statement provided by a DFI."""
    __tablename__ = 'dfi_statement'
    id = Column(BigInteger, nullable=False, primary_key=True)
    profile_id = Column(
        String, ForeignKey('profile.id'), index=True, nullable=False)
    ts = Column(DateTime, nullable=False)
    content = Column(JSONB, nullable=False)

    profile = backref(Profile)


class DFIEntry(Base):
    """The DFI side of a RecoEntry."""
    __tablename__ = 'dfi_entry'
    id = Column(BigInteger, nullable=False, primary_key=True)
    profile_id = Column(
        String, ForeignKey('profile.id'), nullable=False, index=True)
    statement_id = Column(
        BigInteger, ForeignKey('dfi_statement.id'), nullable=True, index=True)
    statement_ref = Column(JSONB, nullable=True)
    entry_date = Column(Date, nullable=False)
    loop_id = Column(String, nullable=False)
    currency = Column(String(3), nullable=False)
    # The delta is negative for account decreases.
    delta = Column(Numeric, nullable=False)
    # Note: we use the terms increase and decrease instead of credit/debit
    # because credit/debit is ambiguous: an increase of a checking account is
    # both a credit to the account holder's asset account and a debit to
    # the bank's liability account.

    # desc contains descriptive info provided by the bank.
    desc = Column(JSONB, nullable=False)


class RecoEntry(Base):
    """A reconciliation entry matches a movement summary with a DFI entry.

    The linked movement summary and linked DFI entry must have matching
    currency and loop_id values. The deltas must match if the DFI entry
    is for the wallet (because the money is sent from or received into the
    wallet); the deltas must be negatives of each other if the
    DFI entry is for the vault (because the money is sent from or received
    into someone else's wallet.)

    A RecoEntry may be marked as reconciled externally, in which case the
    movement summary or DFI entry will be missing.
    """
    __tablename__ = 'reco_entry'
    id = Column(BigInteger, nullable=False, primary_key=True)
    profile_id = Column(
        String, ForeignKey('profile.id'), nullable=False, index=True)
    movement_summary_id = Column(
        BigInteger, ForeignKey('movement_summary.id'),
        nullable=True, index=True)
    dfi_entry_id = Column(
        BigInteger, ForeignKey('dfi_entry.id'), nullable=True, index=True)
    comment = Column(Unicode, nullable=True)
    reco_ts = Column(DateTime, nullable=True)
    reco_by = Column(String, nullable=True)

    profile = backref(Profile)
    movement_summary = backref(MovementSummary)
    dfi_entry = backref(DFIEntry)


class RecoLog(Base):
    """Log of reconciliation activity"""
    __tablename__ = 'reco_log'
    id = Column(BigInteger, nullable=False, primary_key=True)
    ts = Column(DateTime, nullable=False)  # Timestamp
    profile_id = Column(String, nullable=True)
    transfer_id = Column(String, nullable=True)
    movement_id = Column(BigInteger, nullable=True)
    dfi_entry_id = Column(BigInteger, nullable=True)
    reco_id = Column(BigInteger, nullable=True)
    content = Column(JSONB, nullable=False)


# all_metadata_defined must be at the end of the file. It signals that
# all model classes have been defined successfully.
all_metadata_defined = True
