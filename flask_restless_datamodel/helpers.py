import json

import flask
from cereal_lazer import dumps, loads, register_class


def register_serializer(model, pk_name, serialize, deserialize):
    def load_model(value):
        pkval = value.get(pk_name)
        if pkval:
            return model.query.filter_by(**{pk_name: pkval}).one_or_none()
        return deserialize(value)

    def serialize_model(value):
        return serialize(value)

    register_class(model.__name__, model, serialize_model, load_model)


def run_object_method(instid, function_name, model):
    instance = model.query.get(instid)
    if not instance:
        return {}
    params = loads(flask.request.get_json()['payload'], fmt='msgpack')
    result = getattr(instance, function_name)(*params['args'],
                                              **params['kwargs'])
    return json.dumps({'payload': dumps(result, fmt='msgpack')})


def get_object_property():
    params = loads(flask.request.get_json()['payload'], fmt='msgpack')
    result = getattr(params['object'], params['property'])
    return json.dumps({'payload': dumps(result, fmt='msgpack')})
