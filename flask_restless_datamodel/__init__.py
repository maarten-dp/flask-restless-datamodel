import json
import flask
import flask_restless
from itertools import chain
from flask import current_app
from flask import abort, Response
from .helpers import run_object_method
from .render import DataModelRenderer, MethodDefinitionRenderer

from functools import wraps
import inspect


def catch_model_configuration(dispatch_request):
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
        def clean(columns):
            return columns or []
        include_columns = chain(clean(self.include_columns), clean(self.include_relations))
        exclude_columns = chain(clean(self.exclude_columns), clean(self.exclude_relations))
        # Putting back the old and original dispatch_request method to continue
        # normal operation from this point on.
        self.__class__.dispatch_request = dispatch_request
        return {
            'include': list(include_columns),
            'exclude': list(exclude_columns)
        }
    return wrapper


def inject_preprocessor(fn, data_model):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        model = args[0]
        app = kwargs.get('app', data_model.api_manager.app)
        if isinstance(model, DataModel):
            renderer = MethodDefinitionRenderer(app, data_model.options)
            data_model.method_renderer = renderer
            kwargs['preprocessors'] = data_model.processors
            data_model.register_method_urls()
            app.before_first_request(data_model.ensure_datamodel_is_initialized)
        blueprint = fn(*args, **kwargs)
        api_info = data_model.api_manager.created_apis_for[model]
        data_model.register_method_url(model, api_info.collection_name)
        return blueprint
    return wrapper


class DataModel(object):
    __tablename__ = 'restless-client-datamodel'

    def __init__(self, api_manager, **options):
        """
        In Flask-Restless, it is up to you to choose which models you would like
        to make available as an api. It should also be a choice to expose your
        datamodel, and preferably in the same intuitive way that you register
        your models.

        This object functions as a puppet model to give the user the feeling 
        like they are registering just another model they want to expose.
        """
        api_manager.create_api_blueprint = inject_preprocessor(
            api_manager.create_api_blueprint, self
        )
        self.api_manager = api_manager
        self.data_model = {}
        self.flag_for_inheritance = {}
        self.options = options
        self.model_methods = {}
        self.method_renderer = None

    @property
    def processors(self):
        return {
            'GET': [self.intercept_and_return_datamodel],
            'GET_MANY': [self.intercept_and_return_datamodel]
        }

    def ensure_datamodel_is_initialized(self):
        """
        A function that will be run before the first request handled by flask
        to ensure that everything is initialized correctly.

        This function is more or less the entry point for this library with
        regards to for execution flow after the DataModel has been initialized.

        We want to run this function as late as possible so that every
        SQLA model that needs to be exposed is registered on flask-restless
        side. And there's nothing later than a 'before_first_request', as at 
        this point we know the server is up and running.
        """
        models = {}
        db = self.api_manager.flask_sqlalchemy_db
        app = self.api_manager.app or current_app
        for model, api_info in self.api_manager.created_apis_for.items():
            if model is self:
                continue
            kwargs = self.get_restless_model_conf(model, api_info)
            kwargs['bp_name'] = api_info.blueprint_name
            models[model] = kwargs
        self.data_model = DataModelRenderer(app, db).render(
            models, self.method_renderer)

    
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
        abort(Response(json.dumps(self.data_model)))

    def get_restless_model_conf(self, model, api_info):
        """
        This method will try to find the corresponding view within the registered
        blueprints in flask-restless and momentarily replace it with a function
        that is able to distil the relevant infomation we need to construct a
        datamodel that is conform to what constraints were defined in 
        flask restless when registering models. 
        Afterwards it will replace the function handle back to its original
        function.
        """
        api_format = flask_restless.APIManager.APINAME_FORMAT
        endpoint = api_format.format('{1}.{0}'.format(*api_info))

        view_func = current_app.view_functions[endpoint]

        dispatch_fn = catch_model_configuration(view_func.view_class.dispatch_request)
        view_func.view_class.dispatch_request = dispatch_fn
        result = view_func().json
        return {
            'collection_name': api_info.collection_name,
            'included': result['include'],
            'excluded': result['exclude']
        }

    def register_method_urls(self):
        """
        retroactively create method urls in case any models were registered to
        flask-restless before the DataModel was registered.

        The reason we cannot do this at the same time as the model render
        (i.e. before first request) is that the method renderer also registers
        new URLs. If done before first request, the first request might fail
        as the method URLs are not defined at the time of making the request
        """
        for model, api_info in self.api_manager.created_apis_for.items():
            if model is self:
                continue
            self.method_renderer.render(model, api_info.collection_name)

    def register_method_url(self, model, collection_name):
        if model == self:
            return
        self.method_renderer.render(model, collection_name)
