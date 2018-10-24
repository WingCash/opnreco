import { binder } from '../../util/binder';
import { compose } from '../../util/functional';
import { connect } from 'react-redux';
import { fOPNReport } from '../../util/fetcher';
import { fetchcache } from '../../reducer/fetchcache';
import { withRouter } from 'react-router';
import { withStyles } from '@material-ui/core/styles';
import Hidden from '@material-ui/core/Hidden';
import LayoutConfig from '../app/LayoutConfig';
import PropTypes from 'prop-types';
import React from 'react';
import FileSelector from '../report/FileSelector';
import Tab from '@material-ui/core/Tab';
import TabContent from './TabContent';
import Tabs from '@material-ui/core/Tabs';


const styles = theme => ({
  root: {
  },
  topLine: {
    [theme.breakpoints.up('lg')]: {
      display: 'flex',
      alignItems: 'flex-end',
    },
    backgroundColor: theme.palette.primary.light,
    color: '#fff',
  },
  fileSelectorBox: {
    padding: 16,
  },
  tabs: {
    flexGrow: '1',
  },
});


class Home extends React.Component {
  static propTypes = {
    classes: PropTypes.object.isRequired,
    history: PropTypes.object.isRequired,
    match: PropTypes.object.isRequired,
    ploop: PropTypes.object,
    file: PropTypes.object,
    transferId: PropTypes.string,
  };

  constructor(props) {
    super(props);
    this.binder = binder(this);
  }

  handleTabChange(event, value) {
    if (value === 't' && this.props.transferId) {
      this.props.history.push(`/${value}/${this.props.transferId}`);
    } else {
      this.props.history.push(`/${value}`);
    }
  }

  handleTabClick(event) {
    if (event.button === 0) {
      event.preventDefault();
    }
  }

  render() {
    const {
      classes,
      match,
      ploop,
      file,
      transferId,
    } = this.props;

    const tab = match.params.tab || 'reco';

    const transferPath = transferId ? `/t/${transferId}` : '/t';
    const tabs = (
      <Tabs
        className={classes.tabs}
        value={tab}
        scrollable
        scrollButtons="auto"
        onChange={this.binder(this.handleTabChange)}
      >
        <Tab value="reco" label="Reconciliation" href="/reco"
          onClick={this.binder(this.handleTabClick)} />
        <Tab value="transactions" label="Transactions" href="/transactions"
          onClick={this.binder(this.handleTabClick)} />
        <Tab value="liabilities" label="Liabilities" href="/liabilities"
          onClick={this.binder(this.handleTabClick)} />
        <Tab value="t" label="Transfer Summary" href={transferPath}
          onClick={this.binder(this.handleTabClick)} />
      </Tabs>
    );

    const filterBox = (
      <div className={classes.fileSelectorBox}>
        <FileSelector ploop={ploop} file={file} />
      </div>
    );

    return (
      <div className={classes.root}>
        <LayoutConfig title="OPN Reports" />

        <div className={classes.topLine}>

          <Hidden lgUp>
            {filterBox}
            {tabs}
          </Hidden>

          <Hidden mdDown>
            {tabs}
            {filterBox}
          </Hidden>

        </div>

        <TabContent tab={tab} ploop={ploop} file={file} />
      </div>
    );
  }
}

const ploopsURL = fOPNReport.pathToURL('/ploops');


function mapStateToProps(state) {
  const {ploopKey, fileId} = state.report;
  const fetched = fetchcache.get(state, ploopsURL) || {};
  const ploops = fetched.ploops || {};
  const ploopOrder = fetched.ploop_order;
  let selectedPloopKey = ploopKey;

  if (ploopOrder && ploopOrder.length) {
    if (!selectedPloopKey || !ploops[selectedPloopKey]) {
      selectedPloopKey = fetched.default_ploop || '';
    }

    if (!selectedPloopKey) {
      selectedPloopKey = ploopOrder[0];
    }
  } else {
    selectedPloopKey = '';
  }

  const ploop = selectedPloopKey ? ploops[selectedPloopKey] : null;

  let file = null;
  if (ploop && ploop.files) {
    if (fileId) {
      file = ploop.files[fileId];
    } else if (ploop.file_order && ploop.file_order.length) {
      file = ploop.files[ploop.file_order[0]];
    }
  }

  return {
    ploop,
    file,
    transferId: state.app.transferId,
  };
}


export default compose(
  withStyles(styles, {withTheme: true}),
  withRouter,
  connect(mapStateToProps),
)(Home);
