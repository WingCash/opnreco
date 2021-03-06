
import Button from '@material-ui/core/Button';
import Dialog from '@material-ui/core/Dialog';
import DialogActions from '@material-ui/core/DialogActions';
import DialogContent from '@material-ui/core/DialogContent';
import DialogContentText from '@material-ui/core/DialogContentText';
import DialogTitle from '@material-ui/core/DialogTitle';
import PropTypes from 'prop-types';
import React from 'react';


class StatementDeleteDialog extends React.Component {
  static propTypes = {
    statementId: PropTypes.string.isRequired,
    deleteConflicts: PropTypes.object,
    onCancel: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
    deleting: PropTypes.bool,
  };

  render() {
    const {
      statementId,
      deleteConflicts,
      onCancel,
      onDelete,
      deleting,
      ...otherProps
    } = this.props;

    if (deleteConflicts) {
      let reason = null;
      if (deleteConflicts.entries_in_closed_period === 1) {
        reason = (
          <span>
            An account entry in this statement belongs to a closed period.
          </span>
        );
      } else if (deleteConflicts.entries_in_closed_period) {
        reason = (
          <span>
            {deleteConflicts} account entries in this statement belong
            to a closed period.
          </span>
        );
      }
      return (
        <Dialog
          onClose={onCancel}
          aria-labelledby="form-dialog-title"
          {...otherProps}
        >
          <DialogTitle id="form-dialog-title">Delete Statement</DialogTitle>
          <DialogContent>
            <DialogContentText>
              This statement can not be deleted yet. {reason}
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={onCancel} color="primary">
              Close
            </Button>
          </DialogActions>
        </Dialog>
      );
    }

    return (
      <Dialog
        onClose={onCancel}
        aria-labelledby="form-dialog-title"
        {...otherProps}
      >
        <DialogTitle id="form-dialog-title">Delete Statement</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to delete statement {statementId}?
            All account entries in the statement will be deleted and
            any associated reconciliations will be canceled.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={onCancel} color="primary" disabled={deleting}>
            Cancel
          </Button>
          <Button onClick={onDelete} color="primary" disabled={deleting}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    );
  }
}


export default StatementDeleteDialog;
