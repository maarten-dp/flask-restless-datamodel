import json
from collections import defaultdict
from functools import wraps

import flask_restless
from cereal_lazer import Cereal
from flask import Response, abort
from flask.testing import EnvironBuilder
from pbr.version import VersionInfo

from .helpers import ModelConfiguration
from .render import DataModelRenderer


def catch_model_view(dispatch_request, getaway_car):
    """
    This is the actual point where we catch the relevant configuration made
    by Flask-Restless. Currently we are only interested in the include and
    exclude columns, but as needs may arise in the future this method may
    grow.

    Flask-Restless generates APIView classes on the fly for each registered model
    and uses this class as a view_func. We monkey patch the call to get access
    to the parameters and then return it back to the original method.
    Due to Flask's "as_view" implementation, it is the only entry point to
    retrieve this information without restrictions. There are other ways to
    retrieve it, but it relies on import and initialisation order, and quickly
    becomes dirty and restrictive.

    And this way, we're at least dropping the restrictive part :)
    """

    def wrapper(self, *args, **kwargs):
        # Putting back the old and original dispatch_request method to continue
        # normal operation from this point on.
        self.__class__.dispatch_request = dispatch_request
        getaway_car.append(self)
        return {}

    return wrapper


def attach_listener(create_blueprint, data_model):
    @wraps(create_blueprint)
    def wrapper(model, *args, **kwargs):
        app = kwargs.get('app', data_model.api_manager.app)
        if isinstance(model, DataModel):
            data_model.init(app)
            kwargs['preprocessors'] = data_model.processors
            return create_blueprint(model, *args, **kwargs)
        blueprint = create_blueprint(model, *args, **kwargs)
        app.register_blueprint(blueprint)
        api_info = data_model.api_manager.created_apis_for[model]
        data_model.register_model(model, api_info, app)
        return blueprint

    return wrapper


class DataModel(object):
    __tablename__ = 'flask-restless-datamodel'

    def __init__(self, api_manager, **options):
        """
        In Flask-Restless, it is up to you to choose which models you would like
        to make available as an api. It should also be a choice to expose your
        datamodel, and preferably in the same intuitive way that you register
        your models.

        This object functions as a puppet model to give the user the feeling
        like they are registering just another model they want to expose.
        """
        api_manager.create_api_blueprint = attach_listener(
            api_manager.create_api_blueprint, self)
        self.api_manager = api_manager
        vi = VersionInfo('flask-restless-datamodel')
        serialize_naively = options.get('serialize_naively', False)
        self.data_model = {
            'FlaskRestlessDatamodel': {
                'server_version': vi.release_string(),
                'serialize_naively': serialize_naively
            }
        }
        self.polymorphic_info = defaultdict(dict)
        self.options = options
        self.model_renderer = None
        self.model_views = {}
        self.app = None
        self.cereal = Cereal(
            raise_load_errors=options.get('raise_load_errors', True),
            serialize_naively=serialize_naively)

    def init(self, app):
        db = self.api_manager.flask_sqlalchemy_db
        self.app = app
        if not hasattr(app, 'extensions'):
            app.extensions = {}
        app.extensions['cereal'] = self.cereal
        self.model_renderer = DataModelRenderer(app, db, self.options)
        # render datamodel for models that were already registered to
        # flask-restless
        for model, api_info in self.api_manager.created_apis_for.items():
            self.register_model(model, api_info, app)

    def register_model(self, model, api_info, app):
        name = model.__name__
        view = self.get_restless_view(model, api_info, app)
        blueprint = app.blueprints[api_info.blueprint_name]
        collection_name = api_info.collection_name

        conf = ModelConfiguration(collection_name, view, blueprint)
        render = self.model_renderer.render(model, conf)

        polymorphic_info = self.model_renderer.render_polymorphic(
            model, self.polymorphic_info[name])

        if 'parent' in polymorphic_info:
            parent = polymorphic_info['parent']
            identity = polymorphic_info['identity']
            self.polymorphic_info[parent][identity] = name

        if polymorphic_info:
            render['polymorphic'] = polymorphic_info

        self.data_model[name] = render
        self.app.register_blueprint(blueprint)

    @property
    def processors(self):
        return {
            'GET': [self.intercept_and_return_datamodel],
            'GET_MANY': [self.intercept_and_return_datamodel]
        }

    def intercept_and_return_datamodel(self, *args, **kwargs):
        """
        This method must be called as a preprocessor to the actual restless
        api call. It will construct the json data model, if it hasn't already been
        constructed, and return it.

        The goal of running this method as a preprocessor is so that we have
        chance to intercept the request before it gets sent to do the actual
        restless database query.

        Since this model is not an actual SQLAlchemy model, it will crash when
        actual db queries are executed on it. This is why we're (mis)using the
        flask abort to prematurely break off the normal restless flow,
        as by now we have all the data we need to return our request.
        """
        # (Mis)using the flask abort to return the datamodel before the
        # request gets forwarded to the actual db querying
        abort(
            Response(
                response=json.dumps(self.data_model),
                mimetype='application/json'))

    def get_restless_view(self, model, api_info, app):
        """
        This method will try to find the corresponding view within the registered
        blueprints in flask-restless and momentarily replace it with a function
        that is able to distil the relevant infomation we need to construct a
        datamodel that is conform to what constraints were defined in
        flask-restless when registering models.
        After the first call it will replace the function handle back to its
        original function.
        """
        api_format = flask_restless.APIManager.APINAME_FORMAT
        endpoint = api_format.format('{1}.{0}'.format(*api_info))

        view_func = app.view_functions[endpoint]

        getaway_car = []
        dispatch_fn = catch_model_view(view_func.view_class.dispatch_request,
                                       getaway_car)
        view_func.view_class.dispatch_request = dispatch_fn

        with app.request_context(self.build_stub_environ(app)):
            view_func().json

        view = getaway_car[0]
        return view

    def build_stub_environ(self, app):
        kw = {'base_url': 'http://localhost'}
        builder = EnvironBuilder(self.app, **kw)
        try:
            environ = builder.get_environ()
        finally:
            builder.close()
        return environ
