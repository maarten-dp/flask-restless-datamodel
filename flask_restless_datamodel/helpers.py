import json

import flask
from sqlalchemy.orm.session import Session


def cr():
    return flask.current_app.extensions['cereal']


def register_serializer(model, pk_name, serialize, deserialize, cr):
    def load_model(value):
        pkval = value.get(pk_name)
        if pkval:
            return model.query.filter_by(**{pk_name: pkval}).one_or_none()
        return deserialize(value)

    def serialize_model(value):
        return serialize(value)

    cr.register_class(model.__name__, model, serialize_model, load_model)


def run_object_method(instid, function_name, model, commit_on_return):
    instance = model.query.get(instid)
    if not instance:
        return {}
    params = cr().loads(flask.request.get_json()['payload'])
    try:
        result = getattr(instance, function_name)(*params['args'],
                                                  **params['kwargs'])
        result = json.dumps({'payload': cr().dumps(result)})
    except Exception as e:
        msg = '{}: {}'.format(e.__class__.__name__, str(e))
        resp = flask.jsonify(message=msg)
        resp.status_code = 500
        flask.abort(resp)

    if commit_on_return:
        try:
            session = Session.object_session(instance)
            session.commit()
        except Exception:
            pass

    return result


def get_object_property():
    params = cr().loads(flask.request.get_json()['payload'])
    result = getattr(params['object'], params['property'])
    return json.dumps({'payload': cr().dumps(result)})
