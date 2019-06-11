import json

import flask
from cereal_lazer import dumps, loads, register_class


def register_serializer(model, pk_name):
    def load_model(value):
        return model.query.get(value)

    def serialize_model(value):
        # TODO refine for composite keys
        return getattr(value, pk_name)

    register_class(model.__name__, model, serialize_model, load_model)


def run_object_method(instid, function_name, model):
    instance = model.query.get(instid)
    if not instance:
        return {}
    kwargs = loads(flask.request.get_json()['payload'], fmt='msgpack')
    return json.dumps({
        'payload': dumps(
            getattr(instance, function_name)(**kwargs), fmt='msgpack')
    })
