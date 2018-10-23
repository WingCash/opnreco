
import { createReducer } from './common';

const SET_PLOOP_KEY = 'report/SET_PLOOP_KEY';
const SET_FILE_ID = 'report/SET_FILE_ID';
const SHOW_RECO_TYPE = 'report/SHOW_RECO_TYPE';
const SET_ROWS_PER_PAGE = 'report/SET_ROWS_PER_PAGE';
const SET_PAGE_INDEX = 'report/SET_PAGE_INDEX';

const initialState = {
  ploopKey: null,
  fileId: null,
  // shownRecoTypes and rowsPerPage are for the Transactions report.
  shownRecoTypes: {manual: true, auto: false},
  rowsPerPage: 50,
  pageIndex: 0,
};

export const setPloopKey = (ploopKey) => ({
  type: SET_PLOOP_KEY, payload: {ploopKey}});

export const setFileId = (fileId) => ({
  type: SET_FILE_ID, payload: {fileId}});

export const showRecoType = (recoType, enabled) => ({
  type: SHOW_RECO_TYPE, payload: {recoType, enabled}});

export const setRowsPerPage = (rows) => ({
  type: SET_ROWS_PER_PAGE, payload: {rows}});

export const setPage = (pageIndex) => ({
  type: SET_PAGE_INDEX, payload: {pageIndex}});

const actionHandlers = {
  [SET_PLOOP_KEY]: (state, {payload: {ploopKey}}) => ({
    ...state,
    ploopKey,
    fileId: null,
  }),

  [SET_FILE_ID]: (state, {payload: {fileId}}) => ({...state, fileId}),

  [SHOW_RECO_TYPE]: (state, {payload: {recoType, enabled}}) => ({
    ...state,
    shownRecoTypes: {
      ...state.shownRecoTypes,
      [recoType]: enabled,
    },
  }),

  [SET_ROWS_PER_PAGE]: (state, {payload: {rows}}) => ({
    ...state,
    rowsPerPage: rows,
  }),

  [SET_PAGE_INDEX]: (state, {payload: {pageIndex}}) => ({
    ...state,
    pageIndex,
  }),
};

export default createReducer(initialState, actionHandlers);
