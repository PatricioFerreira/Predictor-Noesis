// Provide a default path to dwr.engine
if (typeof this['dwr'] == 'undefined') this.dwr = {};
if (typeof dwr['engine'] == 'undefined') dwr.engine = {};
if (typeof dwr.engine['_mappedClasses'] == 'undefined') dwr.engine._mappedClasses = {};

if (window['dojo']) dojo.provide('dwr.interface.BoletimService');

if (typeof this['BoletimService'] == 'undefined') BoletimService = {};

BoletimService._path = '/uruguai/dwr';

/**
 * @param {function|Object} callback callback function or options object
 */
BoletimService.findAll = function(callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'findAll', arguments);
};

/**
 * @param {class java.lang.Integer} p0 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.deleteById = function(p0, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'deleteById', arguments);
};

/**
 * @param {interface java.util.List} p0 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.deleteByIds = function(p0, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'deleteByIds', arguments);
};

/**
 * @param {class java.lang.Integer} p0 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.findById = function(p0, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'findById', arguments);
};

/**
 * @param {class java.lang.String} p0 a param
 * @param {class java.lang.String} p1 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.findAllOrderBy = function(p0, p1, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'findAllOrderBy', arguments);
};

/**
 * @param {interface java.util.List} p0 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.findByIds = function(p0, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'findByIds', arguments);
};

/**
 * @param {class com.coffey.cprm.publicacao.crud.bean.Boletim} p0 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.saveBoletim = function(p0, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'saveBoletim', arguments);
};

/**
 * @param {class com.coffey.cprm.publicacao.crud.bean.Boletim} p0 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.gerarBoletim = function(p0, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'gerarBoletim', arguments);
};

/**
 * @param {class com.coffey.cprm.publicacao.crud.bean.ConfiguracaoEmailBoletim} p0 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.enviaBoletimEmail = function(p0, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'enviaBoletimEmail', arguments);
};

/**
 * @param {class com.coffey.cprm.publicacao.crud.enums.EnumTipoBoletim} p0 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.obtemUltimoNumeroBoletimByTipo = function(p0, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'obtemUltimoNumeroBoletimByTipo', arguments);
};

/**
 * @param {function|Object} callback callback function or options object
 */
BoletimService.obtemUltimoBoletim = function(callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'obtemUltimoBoletim', arguments);
};

/**
 * @param {class com.coffey.cprm.publicacao.crud.bean.Boletim} p0 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.save = function(p0, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'save', arguments);
};

/**
 * @param {class com.coffey.cprm.geral.ui.flexigrid.bean.GridFilter} p0 a param
 * @param {class com.coffey.cprm.seguranca.crud.enums.EnumTipoAcesso} p1 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.populateGrid = function(p0, p1, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'populateGrid', arguments);
};

/**
 * @param {class com.coffey.cprm.geral.ui.flexigrid.bean.GridFilter} p0 a param
 * @param {class com.coffey.cprm.seguranca.crud.enums.EnumTipoAcesso} p1 a param
 * @param {function|Object} callback callback function or options object
 */
BoletimService.exportExcel = function(p0, p1, callback) {
  return dwr.engine._execute(BoletimService._path, 'BoletimService', 'exportExcel', arguments);
};


