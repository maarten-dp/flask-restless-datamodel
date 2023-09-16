import flask
import pytest
from requests_flask_adapter import Session


@pytest.fixture
def app():
    app = flask.Flask(__name__)
    app.config["DEBUG"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    with app.app_context():
        yield app


@pytest.fixture(scope="function")
def client_maker():
    def client(app):
        Session.register("http://app", app)
        return Session()

    return client
