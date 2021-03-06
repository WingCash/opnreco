
import PropTypes from 'prop-types';
import React from 'react';
import { fOPN } from '../../util/fetcher';
import { connect } from 'react-redux';
import { logIn, setCameFrom, clearOAuthState } from '../../reducer/login';
import { parse } from 'query-string';
import { withRouter } from 'react-router';
import { compose } from '../../util/functional';


class OAuth2CallbackView extends React.Component {
  static propTypes = {
    cameFrom: PropTypes.string,
    dispatch: PropTypes.func.isRequired,
    deviceUUID: PropTypes.string,
    history: PropTypes.object.isRequired,
    oauthState: PropTypes.string,
    authenticated: PropTypes.bool,
  };

  constructor(props) {
    super(props);
    this.state = {error: null};
  }

  componentDidMount() {
    if (this.props.authenticated) {
      // Another instance of this view already set the token
      // and will finish asynchronously.
      return;
    }
    const parsed = parse(window.location.hash);
    if (parsed.access_token && parsed.state === this.props.oauthState) {
      // Set the token without a profile name, request info about the
      // profile, then set the token again with a profile name.

      // Note: grab refs to the props we need because the sequence below
      // may have a side effect of removing this component from the DOM,
      // possibly making the props no longer available.
      const cameFrom = this.props.cameFrom || '/';
      const dispatch = this.props.dispatch;
      const propsHistory = this.props.history;

      dispatch(clearOAuthState());
      dispatch(logIn(parsed.access_token));
      const action = fOPN.fetchPath('/me', {
        disableRefresh: true,
        token: parsed.access_token,
      });
      dispatch(action).then(profileInfo => {
        dispatch(logIn(parsed.access_token, {
          id: profileInfo.id,
          title: profileInfo.title,
        }));
        dispatch(setCameFrom(''));
        window.setTimeout(() => propsHistory.push(cameFrom), 0);
      }).catch((error) => {
        this.setState({error: String(error)});
      });
    } else {
      this.setState({
        error: 'The server provided invalid authentication state.',
      });
    }
  }

  render() {
    const {error} = this.state;
    if (!error) {
      return (<p style={{opacity: '0.1'}}>Signing in&hellip;</p>);
    } else {
      return (
        <p>
          An error occurred while signing in:
          <strong>{error}</strong>
        </p>
      );
    }
  }
}

function mapStateToProps(state) {
  const {
    oauthState,
    cameFrom,
    authenticated,
  } = state.login;
  return {
    oauthState,
    cameFrom,
    authenticated,
  };
}

export default compose(
  withRouter,
  connect(mapStateToProps),
)(OAuth2CallbackView);
