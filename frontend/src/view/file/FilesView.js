import { binder, binder1 } from '../../util/binder';
import { compose } from '../../util/functional';
import { connect } from 'react-redux';
import { fOPNReco } from '../../util/fetcher';
import { fetchcache } from '../../reducer/fetchcache';
import { FormattedDate } from 'react-intl';
import { getCurrencyFormatter } from '../../util/currency';
import { getPagerState } from '../../reducer/pager';
import { withRouter } from 'react-router';
import { withStyles } from '@material-ui/core/styles';
import CircularProgress from '@material-ui/core/CircularProgress';
import LayoutConfig from '../app/LayoutConfig';
import Pager from '../../util/Pager';
import Paper from '@material-ui/core/Paper';
import PropTypes from 'prop-types';
import React from 'react';
import Require from '../../util/Require';
import Typography from '@material-ui/core/Typography';
import Lock from '@material-ui/icons/Lock';
import LockOpen from '@material-ui/icons/LockOpen';


const tableWidth = 800;


const styles = {
  root: {
    fontSize: '0.9rem',
    padding: '0 16px',
  },
  pagerPaper: {
    margin: '16px auto',
    maxWidth: tableWidth - 16,
    padding: '8px',
  },
  tablePaper: {
    margin: '16px auto',
    maxWidth: tableWidth,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    color: '#000',
  },
  titleCell: {
    border: '1px solid #bbb',
    padding: '4px 8px',
    fontWeight: 'normal',
    backgroundColor: '#ddd',
  },
  headCell: {
    border: '1px solid #bbb',
    padding: '4px 8px',
    backgroundColor: '#eee',
  },
  headCellLeft: {
    borderLeft: '4px solid #bbb',
    borderRight: '1px solid #bbb',
    borderTop: '1px solid #bbb',
    borderBottom: '1px solid #bbb',
    padding: '4px 8px',
    backgroundColor: '#eee',
  },
  headCellRight: {
    borderRight: '4px solid #bbb',
    borderLeft: '1px solid #bbb',
    borderTop: '1px solid #bbb',
    borderBottom: '1px solid #bbb',
    padding: '4px 8px',
    backgroundColor: '#eee',
  },
  headCellLeftRight: {
    borderLeft: '4px solid #bbb',
    borderRight: '4px solid #bbb',
    borderTop: '1px solid #bbb',
    borderBottom: '1px solid #bbb',
    padding: '4px 8px',
    backgroundColor: '#eee',
  },
  cell: {
    border: '1px solid #bbb',
    padding: '4px 8px',
  },
  cellLeft: {
    borderLeft: '4px solid #bbb',
    borderRight: '1px solid #bbb',
    borderTop: '1px solid #bbb',
    borderBottom: '1px solid #bbb',
    padding: '4px 8px',
  },
  cellRight: {
    borderRight: '4px solid #bbb',
    borderLeft: '1px solid #bbb',
    borderTop: '1px solid #bbb',
    borderBottom: '1px solid #bbb',
    padding: '4px 8px',
  },
  cellLeftRight: {
    borderLeft: '4px solid #bbb',
    borderRight: '4px solid #bbb',
    borderTop: '1px solid #bbb',
    borderBottom: '1px solid #bbb',
    padding: '4px 8px',
  },
  center: {
    textAlign: 'center',
  },
  right: {
    textAlign: 'right',
  },
  amountCell: {
    border: '1px solid #bbb',
    textAlign: 'right',
    padding: '4px 8px',
  },
  fileRow: {
    cursor: 'pointer',
    '&:hover': {
      backgroundColor: '#eee',
    },
  },
  fileSelectedRow: {
    backgroundColor: '#ffe',
  },
};


class FilesView extends React.Component {
  static propTypes = {
    classes: PropTypes.object.isRequired,
    dispatch: PropTypes.func.isRequired,
    history: PropTypes.object.isRequired,
    contentURL: PropTypes.string,
    content: PropTypes.object,
    loading: PropTypes.bool,
    ploop: PropTypes.object,
    pagerName: PropTypes.string.isRequired,
    initialRowsPerPage: PropTypes.number.isRequired,
    file: PropTypes.object,
  };

  constructor(props) {
    super(props);
    this.binder = binder(this);
    this.binder1 = binder1(this);
  }

  handleClickFile(fileId) {
    this.props.history.push('/file/' + fileId);
  }

  renderTableBody(showCirc) {
    const {
      classes,
      content,
      ploop,
      file: selectedFile,
    } = this.props;

    const cfmt = new getCurrencyFormatter(ploop.currency);
    const rows = [];
    const ccStartDate = classes.cell;
    const ccEndDate = classes.cellRight;
    const ccStartCirc = `${classes.cellLeft} ${classes.right}`;
    const ccEndCirc = `${classes.cellRight} ${classes.right}`;
    const ccStartCombined = `${classes.cellLeft} ${classes.right}`;
    const ccEndCombined = `${classes.cellRight} ${classes.right}`;
    const ccStatements = `${classes.cellLeft} ${classes.right}`;
    const ccState = `${classes.cell} ${classes.center}`;

    content.files.forEach(file => {
      let rowClass = classes.fileRow;
      if (selectedFile && file.file_id === selectedFile.file_id) {
        rowClass += ' ' + classes.fileSelectedRow;
      }

      rows.push(
        <tr
          key={file.file_id}
          data-file-id={file.file_id}
          className={rowClass}
          onClick={this.binder1(this.handleClickFile, file.file_id)}
        >
          <td className={ccStartDate} width="14%">
            {file.start_date ?
              <FormattedDate value={file.start_date}
                day="numeric" month="short" year="numeric"
                timeZone="UTC" />
              : 'Initial'}
          </td>
          <td className={ccEndDate} width="14%">
            {file.end_date ?
              <FormattedDate value={file.end_date}
                day="numeric" month="short" year="numeric"
                timeZone="UTC" />
              : 'In progress'}
          </td>
          {showCirc ?
            <td className={ccStartCirc} width="12%">
              {cfmt(file.start_circ)}
            </td>
            : null}
          {showCirc ?
            <td className={ccEndCirc} width="12%">
              {cfmt(file.end_circ)}
            </td>
            : null}
          <td className={ccStartCombined} width="12%">
            {cfmt(file.start_combined)}
          </td>
          <td className={ccEndCombined} width="12%">
            {file.end_combined ? cfmt(file.end_combined) : 'In progress'}
          </td>
          <td className={ccStatements} width="12%" title="Statements">
            {file.statement_count}
          </td>
          <td className={ccState} width="12%" title={file.locked ? 'Locked' : 'Unlocked'}>
            {file.locked ? <Lock/> : <LockOpen/>}
          </td>
        </tr>
      );
    });

    return <tbody>{rows}</tbody>;
  }

  renderTable() {
    const {
      classes,
      ploop,
    } = this.props;

    const {currency, loop_id} = ploop;

    let circHead0 = null;
    let circHead1 = null;
    let columnCount;

    const showCirc = (ploop.peer_id === 'c');

    if (showCirc) {
      columnCount = 8;
      circHead0 = (
        <td colSpan="2" className={`${classes.headCellLeftRight} ${classes.center}`}>Circulation</td>
      );
      circHead1 = (
        <React.Fragment>
          <td className={`${classes.headCellLeft} ${classes.right}`}>Start</td>
          <td className={`${classes.headCellRight} ${classes.right}`}>End</td>
        </React.Fragment>
      );
    } else {
      columnCount = 6;
    }

    const headRow0 = (
      <tr>
        <td colSpan="2" className={`${classes.headCellRight} ${classes.center}`}>Date</td>
        {circHead0}
        <td colSpan="2" className={`${classes.headCellLeftRight} ${classes.center}`}>Balance</td>
        <td className={`${classes.headCellLeft} ${classes.center}`}>Statements</td>
        <td className={`${classes.headCell} ${classes.center}`}>State</td>
      </tr>
    );

    const headRow1 = (
      <tr>
        <td className={classes.headCell}>Start</td>
        <td className={classes.headCellRight}>End</td>
        {circHead1}
        <td className={`${classes.headCellLeft} ${classes.right}`}>Start</td>
        <td className={`${classes.headCellRight} ${classes.right}`}>End</td>
        <td className={`${classes.headCellLeft} ${classes.center}`}></td>
        <td className={`${classes.headCell} ${classes.center}`}></td>
      </tr>
    );

    return (
      <Paper className={classes.tablePaper}>
        <table className={classes.table}>
          <thead>
            <tr>
              <th className={classes.titleCell} colSpan={columnCount}>
                {ploop.peer_title} Reconciliation Files
                <div>
                  {currency}
                  {' '}{loop_id === '0' ? 'Open Loop' : ploop.loop_title}
                  {' - '}
                  <FormattedDate
                    value={new Date()}
                    day="numeric" month="short" year="numeric" />
                </div>
              </th>
            </tr>
            {headRow0}
            {headRow1}
          </thead>
          {this.renderTableBody(showCirc)}
        </table>
      </Paper>
    );
  }

  render() {
    const {
      classes,
      contentURL,
      content,
      loading,
      pagerName,
      initialRowsPerPage,
    } = this.props;

    if (!contentURL) {
      // No peer loop selected.
      return null;
    }

    let pageContent, rowcount;

    if (!content) {
      rowcount = null;
      if (loading) {
        pageContent = (
          <div className={classes.root}>
            <Paper className={classes.tablePaper}
              style={{textAlign: 'center', }}
            >
              <CircularProgress style={{padding: '16px'}} />
            </Paper>
            <div style={{height: 1}}></div>
          </div>);
      } else {
        pageContent = null;
      }
    } else {
      rowcount = content.rowcount;
      pageContent = this.renderTable();
    }

    return (
      <Typography className={classes.root} component="div">
        <LayoutConfig title="Files" />
        <Require fetcher={fOPNReco} urls={[contentURL]} />
        <Paper className={classes.pagerPaper}>
          <Pager
            name={pagerName}
            initialRowsPerPage={initialRowsPerPage}
            rowcount={rowcount} />
        </Paper>
        {pageContent}
        <div style={{height: 1}}></div>
      </Typography>
    );
  }
}


function mapStateToProps(state, ownProps) {
  const pagerName = 'fileList';
  const {ploop} = ownProps;
  const {
    rowsPerPage,
    pageIndex,
    initialRowsPerPage,
  } = getPagerState(state, pagerName, 10);

  if (ploop) {
    const contentURL = fOPNReco.pathToURL(
      `/files?ploop_key=${encodeURIComponent(ploop.ploop_key)}` +
      `&offset=${encodeURIComponent(pageIndex * rowsPerPage)}` +
      `&limit=${encodeURIComponent(rowsPerPage || 'none')}`);
    const content = fetchcache.get(state, contentURL);
    const loading = fetchcache.fetching(state, contentURL);
    const loadError = !!fetchcache.getError(state, contentURL);
    return {
      contentURL,
      content,
      loading,
      loadError,
      pagerName,
      initialRowsPerPage,
    };
  } else {
    return {
      pagerName,
      initialRowsPerPage,
    };
  }
}


export default compose(
  withStyles(styles),
  withRouter,
  connect(mapStateToProps),
)(FilesView);