import sys
import os
import string
import ConfigParser

from _newrelic import *

from newrelic.profile import *

# Read in and apply agent configuration from the configuration
# file. Before we do that though we need to define some mapping
# functions to convert raw values into internal types expected
# by the internal configuration settings object.

_LOG_LEVEL = {
    'ERROR' : LOG_ERROR,
    'WARNING': LOG_WARNING,
    'INFO' : LOG_INFO,
    'VERBOSE' : LOG_VERBOSE,
    'DEBUG' : LOG_DEBUG,
    'VERBOSEDEBUG': LOG_VERBOSEDEBUG,
}

_RECORD_SQL = {
    "off": RECORDSQL_OFF,
    "raw": RECORDSQL_RAW,
    "obfuscated": RECORDSQL_OBFUSCATED,
}

def _map_log_level(s):
    return _LOG_LEVEL[s.upper()]

def _map_ignored_params(s):
    return s.split()

def _map_transaction_threshold(s):
    if s == 'apdex_f':
        return None
    return float(s)

def _map_record_sql(s):
    return _RECORD_SQL[s]

def _map_ignore_errors(s):
    return s.split()

# This is the actual internal settings object. Options which
# are read from the configuration file will be applied to this.

_settings = settings()

# Grab location of configuration file and name of environment
# name from environment variables. If configuration file is
# not defined the internal defaults will be use instead allowing
# everything to still work.

_config_file = os.environ.get('NEWRELIC_CONFIG_FILE', None)
_config_environment = os.environ.get('NEWRELIC_ENVIRONMENT', None)

# We use the raw config parser as we want to avoid interpolation
# within values. This avoids problems when writing lambdas with
# in the actual configuration file for options which value can
# be dynamically calculated at time wrapper is executed.

_config_object = ConfigParser.RawConfigParser()

# Cache of the parsed global settings found in the configuration
# file. We cache these so can dump them out to the log file once
# all the settings have been read.

_config_global_settings = []

# Processing of a single setting from configuration file.

def _process_setting(section, option, getter, mapper):
    try:
	# The type of a value is dictated by the getter
	# function supplied.

        value = getattr(_config_object, getter)(section, option)

    except ConfigParser.NoOptionError:
        pass

    except:
	# Get here and the getter must have failed to
	# decode the value for the option.

        value = _config_object.get(section, option)

        log(LOG_ERROR, 'Configuration Error')
        log(LOG_ERROR, 'Section = %s' % repr(section))
        log(LOG_ERROR, 'Option = %s' % repr(option))
        log(LOG_ERROR, 'Value = %s' % repr(value))
        log(LOG_ERROR, 'Parser = %s' % repr(getter))

        log_exception(*sys.exc_info())

        raise ConfigurationError('Invalid configuration entry with '
                'name %s and value %s. Check agent log file for '
                'further details.' % (repr(option), repr(value)))
    else:
	# The getter parsed the value okay but want to
	# pass this through a mapping function to change
	# it to internal value suitable for internal
	# settings object. This is usually one where the
        # value was a string.

        try:
            if mapper:
                value = mapper(value)

        except:
	    # Get here and value wasn't within the restricted
	    # range of values as defined by mapping function.

            log(LOG_ERROR, 'Configuration Error')
            log(LOG_ERROR, 'Section = %s' % repr(section))
            log(LOG_ERROR, 'Option = %s' % repr(option))
            log(LOG_ERROR, 'Value = %s' % repr(value))
            log(LOG_ERROR, 'Parser = %s' % repr(getter))

            log_exception(*sys.exc_info())

            raise ConfigurationError('Invalid configuration entry with '
                    'name %s and value %s. Check agent log file for '
                    'further details.' % (repr(option), repr(value)))

        else:
	    # Now need to apply the option from the
	    # configuration file to the internal settings
	    # object. Walk the object path and assign it.

            target = _settings
            parts = string.splitfields(option, '.', 1) 

            while True:
                if len(parts) == 1:
                    setattr(target, parts[0], value)
                    break
                else:
                    target = getattr(target, parts[0])
                    parts = string.splitfields(parts[1], '.', 1)

	    # Cache the configuration so can be dumped out to
	    # log file when whole main configuraiton has been
	    # processed. This ensures that the log file and log
	    # level entries have been set.

            _config_global_settings.append((option, value))

# Processing of all the settings for specified section except
# for log file and log level which are applied separately to
# ensure they are set as soon as possible.

def _process_configuration(section):
    _process_setting(section, 'app_name',
                     'get', None)
    _process_setting(section, 'monitor_mode',
                     'getboolean', None)
    _process_setting(section, 'capture_params',
                     'getboolean', None)
    _process_setting(section, 'ignored_params',
                     'get', _map_ignored_params)
    _process_setting(section, 'transaction_tracer.enabled',
                     'getboolean', None)
    _process_setting(section, 'transaction_tracer.transaction_threshold',
                     'get', _map_transaction_threshold)
    _process_setting(section, 'transaction_tracer.record_sql',
                     'get', _map_record_sql)
    _process_setting(section, 'transaction_tracer.stack_trace_threshold',
                     'getfloat', None)
    _process_setting(section, 'transaction_tracer.expensive_nodes_limit',
                     'getint', None)
    _process_setting(section, 'transaction_tracer.expensive_node_minimum',
                     'getfloat', None)
    _process_setting(section, 'error_collector.enabled',
                     'getboolean', None),
    _process_setting(section, 'error_collector.ignore_errors',
                     'get', _map_ignore_errors)
    _process_setting(section, 'browser_monitoring.auto_instrument',
                     'getboolean', None)
    _process_setting(section, 'local_daemon.socket_path',
                     'get', None)
    _process_setting(section, 'local_daemon.synchronous_startup',
                     'getboolean', None)
    _process_setting(section, 'debug.dump_metric_table',
                     'getboolean', None)
    _process_setting(section, 'debug.sql_statement_parsing',
                     'getboolean', None)

# Process then configuration file if one was specified via the
# environment variable.

if _config_file:
    if not _config_object.read([_config_file]):
        log(LOG_ERROR, 'Configuration File Does Not Exist')
        log(LOG_ERROR, 'File = %s' % repr(_config_file))

        raise ConfigurationError('Unable to open configuration file %s. '
                 'Check agent log file for further details.' % _config_file)

    # Although we have read the configuration here, only process
    # it if this hasn't already been done previously. This should
    # not ever occur unless user code trys to trigger reloading
    # of the configuration file. Decide later if want to provide
    # way of reading configuration file again if it has changed.
    # If allow this, can only reprocess the main global settings.

    if _settings.config_file is None:
        _settings.config_file = _config_file

        # Must process log file entries first so that errors with
        # the remainder will get logged if log file is defined.

        _process_setting('newrelic', 'log_file',
                         'get', None)
        _process_setting('newrelic', 'log_level',
                         'get', _map_log_level)

        if _config_environment:
            _process_setting('newrelic:%s' % _config_environment,
                             'log_file', 'get', None)
            _process_setting('newrelic:%s' % _config_environment ,
                             'log_level', 'get', _map_log_level)

	# Now process the remainder of the global configuration
	# settings.

        _process_configuration('newrelic')

	# And any overrides specified with a section
	# corresponding to a specific deployment environment.

        if _config_environment:
            _settings.environment = _config_environment
            _process_configuration('newrelic:%s' % _config_environment)

        # Log details of the configuration options which were
        # read and the values they have as would be applied
        # against the internal settings object.

        for option, value in _config_global_settings:
            log(LOG_INFO, "agent config %s=%s" % (option, repr(value)))

    else:
        assert _settings.config_file == _config_file
        assert _settings.environment == _config_environment

# Setup instrumentation by triggering off module imports.

sys.meta_path.insert(0, ImportHookFinder())

def _import_hook(module, function):
    def _instrument(target):
        log(LOG_INFO, "execute import-hook %s" % ((target,
                module, function),))
        getattr(import_module(module), function)(target)
    return _instrument

def _process_import_hook(target, module, function='instrument'):
    enabled = True
    section = 'import-hook:%s' % target
    if _config_object.has_section(section):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
        except ConfigParser.NoOptionError:
            pass
    if enabled and not _config_object.has_option(section, 'execute'):
        register_import_hook(target, _import_hook(module, function))
        log(LOG_INFO, "register import-hook %s" % ((target,
                module, function),))

for section in _config_object.sections():
    if section.startswith('import-hook:'):
        target = section.split(':')[1]
        try:
            enabled = _config_object.getboolean(section, 'enabled')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                try:
                    parts = _config_object.get(section, 'execute').split(':')
                except ConfigParser.NoOptionError:
                    pass
                else:
                    module = parts[0]
                    function = 'instrument'
                    if len(parts) != 1:
                        function = parts[1]
                    register_import_hook(target, _import_hook(
                            module, function))
                    log(LOG_INFO, "register import-hook %s" % ((target,
                            module, function),))

_process_import_hook('django.core.handlers.base',
                     'newrelic.imports.framework.django')
_process_import_hook('django.core.urlresolvers',
                     'newrelic.imports.framework.django')
_process_import_hook('django.core.handlers.wsgi',
                     'newrelic.imports.framework.django')
_process_import_hook('django.template',
                     'newrelic.imports.framework.django')
_process_import_hook('django.core.servers.basehttp',
                     'newrelic.imports.framework.django')

_process_import_hook('flask', 'newrelic.imports.framework.flask')
_process_import_hook('flask.app', 'newrelic.imports.framework.flask')

_process_import_hook('gluon.compileapp',
                     'newrelic.imports.framework.web2py',
                     'instrument_gluon_compileapp')
_process_import_hook('gluon.restricted',
                     'newrelic.imports.framework.web2py',
                     'instrument_gluon_restricted')
_process_import_hook('gluon.main',
                     'newrelic.imports.framework.web2py',
                     'instrument_gluon_main')
_process_import_hook('gluon.template',
                     'newrelic.imports.framework.web2py',
                     'instrument_gluon_template')
_process_import_hook('gluon.tools',
                     'newrelic.imports.framework.web2py',
                     'instrument_gluon_tools')
_process_import_hook('gluon.http',
                     'newrelic.imports.framework.web2py',
                     'instrument_gluon_http')

_process_import_hook('gluon.contrib.feedparser',
                     'newrelic.imports.external.feedparser')
_process_import_hook('gluon.contrib.memcache.memcache',
                     'newrelic.imports.memcache.memcache')

_process_import_hook('pylons.wsgiapp','newrelic.imports.framework.pylons')
_process_import_hook('pylons.controllers.core',
                     'newrelic.imports.framework.pylons')
_process_import_hook('pylons.templating', 'newrelic.imports.framework.pylons')

_process_import_hook('cx_Oracle', 'newrelic.imports.database.dbapi2')
_process_import_hook('MySQLdb', 'newrelic.imports.database.dbapi2')
_process_import_hook('postgresql.interface.proboscis.dbapi2',
                     'newrelic.imports.database.dbapi2')
_process_import_hook('psycopg2', 'newrelic.imports.database.dbapi2')
_process_import_hook('pysqlite2.dbapi2', 'newrelic.imports.database.dbapi2')
_process_import_hook('sqlite3.dbapi2', 'newrelic.imports.database.dbapi2')

_process_import_hook('memcache', 'newrelic.imports.memcache.memcache')
_process_import_hook('pylibmc', 'newrelic.imports.memcache.pylibmc')

_process_import_hook('jinja2.environment', 'newrelic.imports.template.jinja2')

_process_import_hook('mako.runtime', 'newrelic.imports.template.mako')

_process_import_hook('genshi.template.base', 'newrelic.imports.template.genshi')

_process_import_hook('feedparser', 'newrelic.imports.external.feedparser')

_process_import_hook('xmlrpclib', 'newrelic.imports.external.xmlrpclib')

# Setup wsgi application wrapper defined in configuration file.

def _wsgi_application_import_hook(object_path, application):
    def _instrument(target):
        log(LOG_INFO, "wrap wsgi-application %s" % ((object_path,
                application),))
        wrap_wsgi_application(target, object_path, application)
    return _instrument

for section in _config_object.sections():
    if section.startswith('wsgi-application:'):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
            function = _config_object.get(section, 'function')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                application = None

                if _config_object.has_option(section, 'application'):
                    application = _config_object.get(section, 'application')

                parts = function.split(':')
                if len(parts) == 2:
                    module, object_path = parts
                    hook = _wsgi_application_import_hook(object_path,
                                                         application)
                    register_import_hook(module, hook)
                    log(LOG_INFO, "register wsgi-application %s" % ((module,
                            object_path, application),))

# Setup background task wrapper defined in configuration file.

def _background_task_import_hook(object_path, application, name, scope):
    def _instrument(target):
        log(LOG_INFO, "wrap background-task %s" % ((object_path,
                application, name, scope),))
        wrap_background_task(target, object_path, application, name, scope)
    return _instrument

for section in _config_object.sections():
    if section.startswith('background-task:'):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
            function = _config_object.get(section, 'function')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                application = None
                name = None
                scope = 'Function'

                if _config_object.has_option(section, 'application'):
                    application = _config_object.get(section, 'application')
                if _config_object.has_option(section, 'name'):
                    name = _config_object.get(section, 'name')
                if _config_object.has_option(section, 'scope'):
                    scope = _config_object.get(section, 'scope')

                parts = function.split(':')
                if len(parts) == 2:
                    module, object_path = parts
                    if name and name.startswith('lambda '):
                        vars = { "callable_name": callable_name,
                                 "import_module": import_module, }
                        name = eval(name, vars)
                    hook = _background_task_import_hook(object_path,
                                                        application,
                                                        name, scope)
                    register_import_hook(module, hook)
                    log(LOG_INFO, "register background-task %s" % ((module,
                            object_path, application, name, scope),))

# Setup database traces defined in configuration file.

def _database_trace_import_hook(object_path, sql):
    def _instrument(target):
        log(LOG_INFO, "wrap database-trace %s" % ((object_path, sql),))
        wrap_database_trace(target, object_path, sql)
    return _instrument

for section in _config_object.sections():
    if section.startswith('database-trace:'):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
            function = _config_object.get(section, 'function')
            sql = _config_object.get(section, 'sql')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                parts = function.split(':')
                if len(parts) == 2:
                    module, object_path = parts
                    if sql.startswith('lambda '):
                        vars = { "callable_name": callable_name,
                                 "import_module": import_module, }
                        sql = eval(sql, vars)
                    hook = _database_trace_import_hook(object_path, sql)
                    register_import_hook(module, hook)
                    log(LOG_INFO, "register database-trace %s" % ((module,
                            object_path, sql),))

# Setup external traces defined in configuration file.

def _external_trace_import_hook(object_path, library, url):
    def _instrument(target):
        log(LOG_INFO, "wrap external-trace %s" % ((object_path,
                library, url),))
        wrap_external_trace(target, object_path, library, url)
    return _instrument

for section in _config_object.sections():
    if section.startswith('external-trace:'):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
            function = _config_object.get(section, 'function')
            library = _config_object.get(section, 'library')
            url = _config_object.get(section, 'url')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                parts = function.split(':')
                if len(parts) == 2:
                    module, object_path = parts
                    if url.startswith('lambda '):
                        vars = { "callable_name": callable_name,
                                 "import_module": import_module, }
                        url = eval(url, vars)
                    hook = _external_trace_import_hook(object_path, library,
                                                       url)
                    register_import_hook(module, hook)
                    log(LOG_INFO, "register external-trace %s" % ((module,
                            object_path, library, url),))

# Setup function traces defined in configuration file.

def _function_trace_import_hook(object_path, name, scope, interesting):
    def _instrument(target):
        log(LOG_INFO, "wrap function-trace %s" % ((object_path,
                name, scope, interesting),))
        wrap_function_trace(target, object_path, name, scope, interesting)
    return _instrument

for section in _config_object.sections():
    if section.startswith('function-trace:'):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
            function = _config_object.get(section, 'function')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                name = None
                scope = 'Function'
                interesting = True

                if _config_object.has_option(section, 'name'):
                    name = _config_object.get(section, 'name')
                if _config_object.has_option(section, 'scope'):
                    scope = _config_object.get(section, 'scope')
                if _config_object.has_option(section, 'interesting'):
                    interesting = _config_object.getboolean(section,
                                                            'interesting')

                parts = function.split(':')
                if len(parts) == 2:
                    module, object_path = parts
                    if name and name.startswith('lambda '):
                        vars = { "callable_name": callable_name,
                                 "import_module": import_module, }
                        name = eval(name, vars)
                    hook = _function_trace_import_hook(object_path, name,
                                                       scope, interesting)
                    register_import_hook(module, hook)
                    log(LOG_INFO, "register function-trace %s" % ((module,
                            object_path, name, scope, interesting),))

# Setup memcache traces defined in configuration file.

def _memcache_trace_import_hook(object_path, command):
    def _instrument(target):
        log(LOG_INFO, "wrap memcache-trace %s" % ((object_path, command),))
        wrap_memcache_trace(target, object_path, command)
    return _instrument

for section in _config_object.sections():
    if section.startswith('memcache-trace:'):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
            function = _config_object.get(section, 'function')
            command = _config_object.get(section, 'command')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                parts = function.split(':')
                if len(parts) == 2:
                    module, object_path = parts
                    if command.startswith('lambda '):
                        vars = { "callable_name": callable_name,
                                 "import_module": import_module, }
                        command = eval(command, vars)
                    hook = _memcache_trace_import_hook(object_path, command)
                    register_import_hook(module, hook)
                    log(LOG_INFO, "register memcache-trace %s" % ((module,
                            object_path, command),))

# Setup name transaction wrapper defined in configuration file.

def _name_transaction_import_hook(object_path, name, scope):
    def _instrument(target):
        log(LOG_INFO, "wrap name-transaction %s" % ((object_path,
                name, scope),))
        wrap_name_transaction(target, object_path, name, scope)
    return _instrument

for section in _config_object.sections():
    if section.startswith('name-transaction:'):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
            function = _config_object.get(section, 'function')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                name = None
                scope = 'Function'

                if _config_object.has_option(section, 'name'):
                    name = _config_object.get(section, 'name')
                if _config_object.has_option(section, 'scope'):
                    scope = _config_object.get(section, 'scope')

                parts = function.split(':')
                if len(parts) == 2:
                    module, object_path = parts
                    if name and name.startswith('lambda '):
                        vars = { "callable_name": callable_name,
                                 "import_module": import_module, }
                        name = eval(name, vars)
                    hook = _name_transaction_import_hook(object_path, name,
                                                         scope)
                    register_import_hook(module, hook)
                    log(LOG_INFO, "register name-transaction %s" % ((module,
                            object_path, name, scope),))

# Setup error trace wrapper defined in configuration file.

def _error_trace_import_hook(object_path, ignore_errors):
    def _instrument(target):
        log(LOG_INFO, "wrap error-trace %s" % ((object_path,
                ignore_errors),))
        wrap_error_trace(target, object_path, ignore_errors)
    return _instrument

for section in _config_object.sections():
    if section.startswith('error-trace:'):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
            function = _config_object.get(section, 'function')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                ignore_errors = []

                if _config_object.has_option(section, 'ignore_errors'):
                    ignore_errors = _config_object.get(section,
                            'ignore_errors').split()

                parts = function.split(':')
                if len(parts) == 2:
                    module, object_path = parts
                    hook = _error_trace_import_hook(object_path, ignore_errors)
                    register_import_hook(module, hook)
                    log(LOG_INFO, "register error-trace %s" % ((module,
                            object_path, ignore_errors),))

# Setup function profiler defined in configuration file.

def _function_profile_import_hook(object_path, interesting, depth):
    def _instrument(target):
        log(LOG_INFO, "wrap function-profile %s" % ((object_path,
                interesting, depth),))
        wrap_function_profile(target, object_path, interesting, depth)
    return _instrument

for section in _config_object.sections():
    if section.startswith('function-profile:'):
        try:
            enabled = _config_object.getboolean(section, 'enabled')
            function = _config_object.get(section, 'function')
        except ConfigParser.NoOptionError:
            pass
        else:
            if enabled:
                interesting = False
                depth = 5

                if _config_object.has_option(section, 'interesting'):
                    interesting = _config_object.getboolean(section,
                                                            'interesting')
                if _config_object.has_option(section, 'depth'):
                    depth = _config_object.getint(section, 'depth')

                parts = function.split(':')
                if len(parts) == 2:
                    module, object_path = parts
                    hook = _function_profile_import_hook(object_path,
                                                         interesting, depth)
                    register_import_hook(module, hook)
                    log(LOG_INFO, "register function-profile %s" % ((module,
                            object_path, interesting, depth),))

