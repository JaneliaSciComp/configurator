''' configurator.py
    Configuration GUI
'''

from datetime import datetime, timedelta
import glob
import hashlib
import json
import os
import re
from shutil import copyfile
import sys
from time import time
import traceback
from flask import Flask, g, render_template, request, jsonify
from flask_cors import CORS
from flask_pymongo import PyMongo
from flask_swagger import swagger
import pymongo
from jwt import decode

TEMPLATE = "An exception of type {0} occurred. Arguments:{1!r}"

__version__ = '1.5.0'
app = Flask(__name__)
app.config.from_pyfile("config.cfg")
CORS(app, supports_credentials=True)
g = PyMongo(app)
print(g.db)
CV_optional = ['access_list', 'definition', 'display_name', 'version', 'is_current']
app.config['STARTTIME'] = time()
app.config['STARTDT'] = datetime.now()
app.config['LAST_TRANSACTION'] = time()


@app.before_request
def before_request():
    ''' Code to run before a request is processed
        Keyword arguments:
          None
        Returns:
          None
    '''
    app.config['REQUEST_TIME'] = time()
    app.config['COUNTER'] += 1
    endpoint = request.endpoint if request.endpoint else '(Unknown)'
    app.config['ENDPOINTS'][endpoint] = app.config['ENDPOINTS'].get(endpoint, 0) + 1


# *****************************************************************************
# * Classes                                                                   *
# *****************************************************************************


class InvalidUsage(Exception):
    ''' Class for InvalidUsage
        Keyword arguments:
          Exception: exception
        Returns:
          None
    '''
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        retval = dict(self.payload or ())
        retval['rest'] = {'error': True,
                          'message': self.message}
        return retval

# *****************************************************************************
# * Utility functions                                                         *
# *****************************************************************************


def initialize_result():
    ''' Initialize the standard JSON return
        Keyword arguments:
          None
        Returns:
          JSON result
    '''
    result = {"rest" : {'requester': request.remote_addr,
                        'url': request.url,
                        'endpoint': request.endpoint,
                        'error': False,
                        'elapsed_time': '',
                        'user': 'unknown'}}
    if 'Authorization' in request.headers:
        token = re.sub(r'Bearer\s+', '', request.headers['Authorization'])
        try:
            dtok = decode(token, verify=False)
            if 'user_name' in dtok:
                result['rest']['user'] = dtok['user_name']
                app.config['USERS'][dtok['user_name']] = \
                    app.config['USERS'].get(dtok['user_name'], 0) + 1
        except Exception as err:
            message = TEMPLATE.format(type(err).__name__, err.args)
            # raise InvalidUsage(message, 500)
            print(message)
    app.config['LAST_TRANSACTION'] = time()
    return result


def generate_response(result):
    ''' Generate a JSON response
        Keyword arguments:
          result: return result
        Returns:
          JSON
    '''
    result['rest']['elapsed_time'] = str(timedelta(seconds=time() - app.config['REQUEST_TIME']))
    return jsonify(**result)


def config_from_file(result, configtype):
    ''' Get a configuration from a file
        Keyword arguments:
          result: return result
          configtype: configuration type
        Returns:
          None
    '''
    print(f"In config_from_file, reading {configtype}")
    result['rest']['method'] = 'file'
    filepath = app.config['CONFIG_PATH'] + configtype + '.json'
    if os.path.exists(filepath):
        try:
            with open(filepath, encoding="utf-8") as data_file:
                result['config'] = json.load(data_file)
        except ValueError as valerr:
            raise InvalidUsage(f"Invalid JSON: {valerr}")
    else:
        raise InvalidUsage(f"Configuration {configtype} was not found on filesystem", 404)


def config_from_mongo(result, configtype, failover=True, ignore_not_found=False):
    ''' Get a configuration from MongoDB
        Keyword arguments:
          result: return result
          configtype: configuration type
          failover: allow failover to file
          ignore_not_found: do not issue error if config was not found
        Returns:
          None
    '''
    print(f"In config_from_mongo, reading {configtype}")
    result['rest']['method'] = 'mongodb'
    try:
        data = g.db[app.config['MONGODB_COLLECTION']].find({"type": configtype})
    except pymongo.errors.PyMongoError:
        if failover:
            config_from_file(result, configtype)
        else:
            raise InvalidUsage(f"Configuration {configtype} was not found", 404)
    if ignore_not_found:
        return
    try:
        result['config'] = data[0]['data']
        for opt in CV_optional:
            if opt in data[0]:
                result[opt] = data[0][opt]
    except Exception as ex:
        if failover:
            config_from_file(result, configtype)
        else:
            message = TEMPLATE.format(type(ex).__name__, ex.args)
            raise InvalidUsage(f"Configuration {configtype} was not found " \
                               + f"({message})", 404)


def dump_to_file(configtype, result, backup=False):
    ''' Dump a configuration to a file
        Keyword arguments:
          configtype: configuration type
          result: return result
          backup: create a backup file in the "backup" directory
        Returns:
          None
    '''
    filepath = app.config['CONFIG_PATH'] + configtype + '.json'
    if backup and os.path.exists(filepath):
        timestamp = datetime.fromtimestamp(time()).strftime('%Y%m%dT%H%M%S')
        backuppath = app.config['CONFIG_PATH'] + 'backup/' + configtype + '.json.' + timestamp
        try:
            copyfile(filepath, backuppath)
        except Exception as ex:
            message = TEMPLATE.format(type(ex).__name__, ex.args)
            raise InvalidUsage(f"Could not export configuration for {configtype} " \
                               + f"to {backuppath}: {message}")
    try:
        with open(filepath, 'w', encoding="utf-8") as outfile:
            json.dump(result['config'], outfile, sort_keys=True, indent=4,)
        outfile.close()
        del result['config']
        result['export_path'] = filepath
        result['export_size'] = os.path.getsize(filepath)
    except Exception as ex:
        message = TEMPLATE.format(type(ex).__name__, ex.args)
        raise InvalidUsage(f"Could not export configuration for {configtype} " \
                           + f"to {filepath}: {message}")


def validate_configtype(doc):
    ''' Validate a configuration in MongoDB against a file
        Keyword arguments:
          doc: document
        Returns:
          Validation result
    '''
    configtype = doc['type']
    data = doc['data']
    jdata = json.dumps(data, sort_keys=True)
    jdata = jdata.encode('utf-8')
    data_md5 = hashlib.md5(jdata).hexdigest()
    fileresult = initialize_result()
    fileresult['rest']['configtype'] = configtype
    config_from_file(fileresult, configtype)
    jdata = json.dumps(fileresult['config'], sort_keys=True)
    jdata = jdata.encode('utf-8')
    file_md5 = hashlib.md5(jdata).hexdigest()
    match = data_md5 == file_md5
    vresult = {configtype: match}
    return vresult


# *****************************************************************************
# * Endpoints                                                                 *
# *****************************************************************************


@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@app.route('/')
def show_swagger():
    return render_template('swagger_ui.html')


@app.route("/spec")
def spec():
    return get_doc_json()


@app.route('/doc')
def get_doc_json():
    swag = swagger(app)
    swag['info']['version'] = "1.0"
    swag['info']['title'] = "Configurator"
    return jsonify(swag)


@app.route("/stats")
def stats():
    '''
    Show stats
    Show uptime/requests statistics
    ---
    tags:
      - Configuration
    responses:
      200:
          description: Stats
      400:
          description: Stats could not be calculated
    '''
    tbt = time() - app.config['LAST_TRANSACTION']
    result = initialize_result()
    try:
        start = datetime.fromtimestamp(app.config['STARTTIME']).strftime('%Y-%m-%d %H:%M:%S')
        up_time = datetime.now() - app.config['STARTDT']
        result['stats'] = {"version": __version__,
                           "requests": app.config['COUNTER'],
                           "python": sys.version,
                           "pid": os.getpid(),
                           "start_time": start,
                           "uptime": str(up_time),
                           "time_since_last_transaction": tbt,
                           "config_path": app.config['CONFIG_PATH'],
                           "endpoint_counts": app.config['ENDPOINTS'],
                           "user_counts": app.config['USERS'],
                           "request_counts": app.config['REQUESTS'],
                           "import_counts": app.config['IMPORTS'],
                           "export_counts": app.config['EXPORTS']}
        return generate_response(result)
    except Exception as ex:
        message = TEMPLATE.format(type(ex).__name__, ex.args)
        traceback.print_tb(ex.__traceback__)
        print(result)
        raise InvalidUsage(f"Error: {message}")


@app.route('/validate', methods=['GET'])
def get_validations():
    '''
    Validate configurations
    Validate configurations in database versus filesystem
    ---
    tags:
      - Configuration
    responses:
      200:
          description: Validation results (1=match, 0=mismatch)
      400/404:
          description: Error validating configurations
    '''
    result = initialize_result()
    result['validations'] = {}
    result['rest']['method'] = 'mongodb'
    try:
        data = g.db[app.config['MONGODB_COLLECTION']].find({})
    except Exception as ex:
        message = TEMPLATE.format(type(ex).__name__, ex.args)
        raise InvalidUsage(f"Error: {message}")
    for doc in data:
        valresult = validate_configtype(doc)
        print(valresult)
        result['validations'].update(valresult)
    return generate_response(result)


@app.route('/configurations', methods=['GET'])
def get_configurations():
    '''
    Show available configurations
    Return a list of available configurations
    ---
    tags:
      - Configuration
    responses:
      200:
          description: List of configurations
      400/404:
          description: Error fetching configurations
    '''
    result = initialize_result()
    result['configlist'] = []
    result['rest']['method'] = 'mongodb'
    try:
        data = g.db[app.config['MONGODB_COLLECTION']].find({}, {"_id": 0, "type": 1}).sort("type")
        for doc in data:
            result['configlist'].append(doc['type'])
    except Exception as ex:
        message = TEMPLATE.format(type(ex).__name__, ex.args)
        result['rest']['failover'] = message
        result['rest']['method'] = 'file'
        for filename in sorted(glob.glob(app.config['CONFIG_PATH'] + '*.json')):
            filename = filename.replace(app.config['CONFIG_PATH'], '')
            filename = filename.replace('.json', '')
            result['configlist'].append(filename)
    return generate_response(result)


def authenticate_access(result):
    ''' Determine if a configuration access requires authorization
        Keyword arguments:
          result: return result
        Returns:
          True or False
    '''
    if 'access_list' in result:
        authorized_users = json.loads(result['access_list'])
        if result['rest']['user'] in authorized_users:
            return True
    else:
        return True
    return False


@app.route('/config/<string:configtype>', methods=['GET'])
def get_config(configtype):
    '''
    Get configuration
    Return JSON configuration for a specified type.
    ---
    tags:
      - Configuration
    parameters:
      - in: path
        name: configtype
        type: string
        required: true
        description: configuration type
    responses:
      200:
          description: Configuration JSON
      404:
          description: Error fetching configuration
    '''
    result = initialize_result()
    result['rest']['configtype'] = configtype
    app.config['REQUESTS'][configtype] = app.config['REQUESTS'].get(configtype, 0) + 1
    config_from_mongo(result, configtype)
    if not authenticate_access(result):
        raise InvalidUsage(f"You are not authorized to access configuration {configtype}", 401)
    result['rest']['config_length'] = len(result['config'])
    return generate_response(result)


@app.route('/config/<string:configtype>/<path:entry>', methods=['GET'])
def get_config_entry(configtype, entry):
    '''
    Get a single entry from a configuration
    Return JSON configuration for an entry in a a specified type.
    ---
    tags:
      - Configuration
    definitions:
      - schema:
          id: Group
          properties:
            name:
              type: string
              description: the group's name
    parameters:
      - in: path
        name: configtype
        type: string
        required: true
        description: configuration type
      - in: path
        name: entry
        type: path
        required: true
        description: entry to return from configuration type
    responses:
      200:
          description: Configuration JSON
      404:
          description: Error fetching configuration or entry
    '''
    result = initialize_result()
    result['rest']['configtype'] = configtype
    app.config['REQUESTS'][configtype] = app.config['REQUESTS'].get(configtype, 0) + 1
    config_from_mongo(result, configtype)
    if entry in result['config']:
        result['config'] = result['config'][entry]
    else:
        raise InvalidUsage(f"Entry {entry} not found in configuration {configtype}", 404)
    if not authenticate_access(result):
        raise InvalidUsage(f"You are not authorized to access configuration {configtype}", 401)
    result['rest']['config_length'] = len(result['config'])
    return generate_response(result)


@app.route('/export/<string:configtype>', methods=['OPTIONS', 'POST'])
def export_config(configtype):
    '''
    Export configuration
    Export JSON configuration for a specified type to a file.
    ---
    tags:
      - Configuration
    parameters:
      - in: path
        name: configtype
        type: string
        required: true
        description: configuration type
    responses:
      200:
          description: Success
      400:
          description: Error exporting configuration
    '''
    result = initialize_result()
    result['rest']['configtype'] = configtype
    if request.method == 'OPTIONS':
        return generate_response(result)
    app.config['EXPORTS'][configtype] = app.config['EXPORTS'].get(configtype, 0) + 1
    config_from_mongo(result, configtype, False)
    if not authenticate_access(result):
        raise InvalidUsage(f"You are not authorized to access configuration {configtype}", 401)
    dump_to_file(configtype, result)
    return generate_response(result)


@app.route('/import/<string:configtype>', methods=['OPTIONS', 'POST'])
def import_config(configtype):
    '''
    Import configuration from file
    Import JSON configuration for a specified type from a file.
    ---
    tags:
      - Configuration
    parameters:
      - in: path
        name: configtype
        type: string
        required: true
        description: configuration type
    responses:
      200:
          description: Success
      400:
          description: Error importing configuration from file
    '''
    result = initialize_result()
    result['rest']['configtype'] = configtype
    if request.method == 'OPTIONS':
        return generate_response(result)
    app.config['IMPORTS'][configtype] = app.config['IMPORTS'].get(configtype, 0) + 1
    parms = {}
    if request.form:
        result['rest']['form'] = request.form
        for i in request.form:
            parms[i] = request.form[i]
    config_from_file(result, configtype)
    ddict = {"type": configtype, "data": result['config']}
    mongo = {"rest": {}}
    config_from_mongo(mongo, configtype, False, True)
    for opt in CV_optional:
        if opt in parms:
            ddict[opt] = parms[opt]
        elif opt in mongo:
            ddict[opt] = mongo[opt]
    try:
        print(g.db)
        data = g.db[app.config['MONGODB_COLLECTION']].update_one({"type": configtype},
                                          {"$set": ddict}, upsert=True)
        result['rest']['matched_count'] = data.matched_count
        result['rest']['modified_count'] = data.modified_count
        result['rest']['upserted_id'] = str(data.upserted_id)
        result['rest']['updated' if data.matched_count else 'inserted'] = 1
    except Exception as ex:
        message = TEMPLATE.format(type(ex).__name__, ex.args)
        raise InvalidUsage(f"Could not import configuration for {configtype}: {message}")
    return generate_response(result)


@app.route('/importjson/<string:configtype>', methods=['OPTIONS', 'POST'])
def import_json_config(configtype):
    '''
    Import JSON configuration
    Import JSON configuration for a specified type. The configuration is also
    automatically exported to the filesystem. Note that the definition,
    display_name, version, and is_current parameters are only useful if
    importing a controlled vocabulary.
    ---
    tags:
      - Configuration
    parameters:
      - in: path
        name: configtype
        type: string
        required: true
        description: configuration type
      - in: query
        name: config
        type: string
        required: true
        description: JSON configuration
      - in: query
        name: definition
        type: string
        description: CV description
      - in: query
        name: display_name
        type: string
        description: CV display name
      - in: query
        name: version
        type: string
        description: CV version
      - in: query
        name: is_current
        type: string
        description: is CV current?
    responses:
      200:
          description: Success
      400:
          description: Error importing JSON configuration
    '''
    result = initialize_result()
    result['rest']['configtype'] = configtype
    if request.method == 'OPTIONS':
        return generate_response(result)
    app.config['IMPORTS'][configtype] = app.config['IMPORTS'].get(configtype, 0) + 1
    parms = {}
    if request.form:
        result['rest']['form'] = request.form
        for i in request.form:
            parms[i] = request.form[i]
    if 'config' not in parms:
        raise InvalidUsage("Missing configuration in JSON import")
    try:
        result['config'] = json.loads(parms['config'])
    except ValueError as valerr:
        raise InvalidUsage(f"Invalid JSON: {valerr}")
    ddict = {"type": configtype, "data": result['config']}
    for this_parm in CV_optional:
        if this_parm in parms:
            ddict[this_parm] = parms[this_parm]
    try:
        data = g.db[app.config['MONGODB_COLLECTION']].update_one({"type": configtype},
                                          {"$set": ddict}, upsert=True)
        result['rest']['matched_count'] = data.matched_count
        result['rest']['modified_count'] = data.modified_count
        result['rest']['upserted_id'] = str(data.upserted_id)
        result['rest']['updated' if data.matched_count else 'inserted'] = 1
    except Exception as ex:
        message = TEMPLATE.format(type(ex).__name__, ex.args)
        raise InvalidUsage(f"Could not import configuration for {configtype}: {message}")
    dump_to_file(configtype, result, True)
    return generate_response(result)


@app.route('/importjson/<string:configtype>/<path:entry>', methods=['OPTIONS', 'POST'])
def import_json_config_entry(configtype, entry):
    '''
    Import JSON configuration/entry
    Import JSON configuration for a specified type/entry. If the entry already
    exists, it will be replaced. The configuration is also automatically
    exported to the filesystem.
    ---
    tags:
      - Configuration
    parameters:
      - in: path
        name: configtype
        type: string
        required: true
        description: configuration type
      - in: path
        name: entry
        type: path
        required: true
        description: entry in configuration type
      - in: query
        name: config
        type: string
        required: true
        description: JSON configuration
    responses:
      200:
          description: Success
      400:
          description: Error importing JSON configuration entry
    '''
    result = initialize_result()
    result['rest']['configtype'] = configtype
    result['rest']['entry'] = entry
    if request.method == 'OPTIONS':
        return generate_response(result)
    app.config['IMPORTS'][configtype] = app.config['IMPORTS'].get(configtype, 0) + 1
    parms = {}
    if request.form:
        result['rest']['form'] = request.form
        for i in request.form:
            parms[i] = request.form[i]
    if 'config' not in parms:
        raise InvalidUsage("Missing configuration in JSON import")
    try:
        result['rest']['config'] = json.loads(parms['config'])
    except ValueError as valerr:
        raise InvalidUsage(f"Invalid JSON: {valerr}")
    result['config'] = {}
    config_from_mongo(result, configtype)
    result['config'][entry] = result['rest']['config']
    new_config = result['config']
    ddict = {"type": configtype, "data": new_config}
    try:
        data = g.db[app.config['MONGODB_COLLECTION']].update_one({"type": configtype},
                                          {"$set": ddict}, upsert=True)
        result['rest']['matched_count'] = data.matched_count
        result['rest']['modified_count'] = data.modified_count
        result['rest']['upserted_id'] = str(data.upserted_id)
        result['rest']['updated' if data.matched_count else 'inserted'] = 1
    except Exception as ex:
        message = TEMPLATE.format(type(ex).__name__, ex.args)
        raise InvalidUsage(f"Could not import configuration for {configtype}: {message}")
    # Export
    eresult = initialize_result()
    config_from_mongo(eresult, configtype, False)
    dump_to_file(configtype, eresult)
    result['config'] = new_config
    result['rest']['config_length'] = len(result['config'])
    return generate_response(result)

if __name__ == '__main__':
    app.run()
