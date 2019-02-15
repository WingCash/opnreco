
import { compose } from '../../util/functional';
import { connect } from 'react-redux';
import { fetchcache } from '../../reducer/fetchcache';
import { fOPNReco } from '../../util/fetcher';
import { withRouter } from 'react-router';
import { withStyles } from '@material-ui/core/styles';
import { verifyShowDetails } from '../../reducer/verify';
import Button from '@material-ui/core/Button';
import Checkbox from '@material-ui/core/Checkbox';
import FormControl from '@material-ui/core/FormControl';
import FormControlLabel from '@material-ui/core/FormControlLabel';
import FormGroup from '@material-ui/core/FormGroup';
import FormHelperText from '@material-ui/core/FormHelperText';
import LayoutConfig from '../app/LayoutConfig';
import LinearProgress from '@material-ui/core/LinearProgress';
import OPNAppBar from '../app/OPNAppBar';
import Paper from '@material-ui/core/Paper';
import PropTypes from 'prop-types';
import React from 'react';
import Require from '../../util/Require';
import Typography from '@material-ui/core/Typography';


const styles = {
  content: {
    margin: '0 16px',
  },

  checkboxHelperText: {
    marginTop: '-8px',
  },

  contentPaper: {
    margin: '16px auto',
    maxWidth: 800,
    padding: '16px',
  },

  introText: {
    textAlign: 'center',
    marginBottom: '16px',
  },

  resultsPaper: {
    margin: '16px auto',
    maxWidth: 800,
    padding: '16px',
  },

  field: {
    marginRight: '16px',
    marginBottom: '16px',
  },

  topCheckboxField: {
    marginTop: '-16px',
    marginRight: '16px',
    marginBottom: '16px',
  },

  progressBox: {
    padding: '8px 0',
  },

  progressNumber: {
    paddingTop: '8px',
  },

  button: {
    marginRight: '16px',
  },

  resultButtons: {
    margin: '16px 0',
  },
};


class Verify extends React.Component {
  static propTypes = {
    classes: PropTypes.object.isRequired,
    dispatch: PropTypes.func.isRequired,
    history: PropTypes.object.isRequired,
    showDetails: PropTypes.bool,
    detailURLs: PropTypes.array,
    detailContent: PropTypes.object,
    detailLoading: PropTypes.object,
  };

  constructor(props) {
    super(props);
    this.state = {
      verifySync: true,
      verifyPeriods: true,
      running: false,
      sync_done: 0,
      sync_total: null,
      progress_percent: null,
      error: null,
      verification_id: null,
    };
  }

  handleCheckBox = attr => event => {
    this.setState({[attr]: event.target.checked});
  }

  handleText = attr => event => {
    this.setState({[attr]: event.target.value});
  }

  handleStop = () => {
    this.setState({running: false});
  }

  handleDetailsToggle = () => {
    if (this.props.showDetails) {
      this.props.dispatch(verifyShowDetails(null, 0));
    } else {
      this.props.dispatch(verifyShowDetails(this.state.verification_id, 1));
    }
  }

  handleVerify = () => {
    const {dispatch} = this.props;

    this.setState({
      running: true,
      sync_done: 0,
      sync_total: null,
      progress_percent: null,
      error: null,
      verification_id: null,
    });
    dispatch(verifyShowDetails(null, 0));

    let verification_id = null;
    const verifyBatch = () => {
      const action = fOPNReco.fetchPath('/verify', {data: {
        verification_id: verification_id,
      }});
      dispatch(action).then(status => {
        verification_id = status.verification_id;
        this.setState({
          verification_id: verification_id,
          sync_done: status.sync_done,
          sync_total: status.sync_total,
          progress_percent: status.progress_percent,
        });
        if (status.more && this.state.running) {
          verifyBatch();
        } else {
          // Done.
          this.setState({running: false});
        }
      }).catch((error) => {
        this.setState({running: false, error});
      });
    };

    verifyBatch();
  }

  renderForm() {
    const {
      classes,
    } = this.props;
    const {state} = this;
    const {running} = state;

    return (
      <Paper className={classes.contentPaper}>

        <Typography variant="body1" className={classes.introText}>
          Use this form to test the integrity of this tool and OPN.
        </Typography>

        <FormGroup row>

          <FormControl disabled={running} className={classes.field}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={state.verifySync}
                  onChange={this.handleCheckBox('verifySync')}
                />
              }
              label="Verify Transfer Integrity"
            />
            <FormHelperText className={classes.checkboxHelperText}>
              Re-download the transfers from OPN and compare them with
              the transfer records downloaded previously. Verify no
              transfers have inappropriately changed.
            </FormHelperText>
          </FormControl>

        </FormGroup>

        <FormGroup row>
          <Button
            className={classes.button}
            variant="contained"
            onClick={this.handleVerify}
            disabled={running}
            color="primary"
          >
            Verify
          </Button>
        </FormGroup>

        <div style={{height: 1}}></div>
      </Paper>
    );
  }

  renderResults() {
    const {
      classes,
      showDetails,
    } = this.props;

    const {state} = this;

    let progressText;

    if (state.sync_done === 1) {
      progressText = 'transfer verified';
    } else {
      progressText = 'transfers verified';
    }

    return (
      <Paper className={classes.resultsPaper}>
        <Typography variant="h6">Results</Typography>
        <div className={classes.progressBox}>
          <LinearProgress
            variant="determinate"
            value={state.progress_percent || 0} />
          <Typography variant="body1" className={classes.progressNumber}>
            {state.sync_done || 0} / {state.sync_total || 0} {progressText} (
            {state.progress_percent || 0}%)
          </Typography>

          <FormGroup row className={classes.resultButtons}>
            <Button
              className={classes.button}
              variant="contained"
              onClick={this.handleDetailsToggle}
              color={showDetails ? 'primary' : 'default'}
            >
              Details
            </Button>
            <Button
              className={classes.button}
              variant="contained"
              onClick={this.handleStop}
              disabled={!this.state.running}
            >
              Stop
            </Button>
          </FormGroup>

          <div style={{height: 1}}></div>

        </div>
      </Paper>
    );
  }

  render() {
    const {
      classes,
      detailURLs,
    } = this.props;

    let results = null;
    if (this.state.sync_total || this.state.running) {
      results = this.renderResults();
    }

    return (
      <div className={classes.root}>
        <LayoutConfig title="Verify" />
        <Require urls={detailURLs} fetcher={fOPNReco} />

        <OPNAppBar />

        <div className={classes.content}>
          {this.renderForm()}
          {results}
        </div>
      </div>
    );
  }
}

function mapStateToProps(state) {
  const detailURLs = [];
  const detailContent = {};
  const detailLoading = {};

  const {verification_id, batch_count} = state.verify;
  if (verification_id && batch_count && batch_count > 0) {
    const vidEnc = encodeURIComponent(verification_id);
    for (let batchIndex = 0; batchIndex < batch_count; batchIndex++) {
      const url = fOPNReco.pathToURL(
        `/verify-details?verification_id=${vidEnc}` +
        `&offset=${batchIndex}`);
      detailURLs.push(url);
      detailContent[url] = fetchcache.get(state, url);
      detailLoading[url] = fetchcache.fetching(state, url);
    }
  }

  return {
    detailURLs,
    detailContent,
    detailLoading,
    showDetails: detailURLs.length > 0,
  };
}

export default compose(
  withStyles(styles),
  withRouter,
  connect(mapStateToProps),
)(Verify);