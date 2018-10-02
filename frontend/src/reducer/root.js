import { combineReducers } from 'redux';
import app from './app';
import deviceuuid from './deviceuuid';
import fetchcache from './fetchcache';
import login from './login';
import report from './report';
import tree from './tree';

export default combineReducers({
  app,
  deviceuuid,
  login,
  fetchcache,
  report,
  tree,
});
